"""Independent retained fact verification through the existing evidence table."""

from sqlalchemy import select
from sqlalchemy.engine import Connection

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.schema import commands, evidence, snapshots
from craftreport.adapters.storage.serialization import (
    decode_evidence,
    decode_object,
    validate_preparation,
)
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    EvidenceRef,
    EvidenceStatus,
    JsonObject,
    OperationKey,
    StageState,
)

STORAGE_FAILURES = (
    StorageUnavailable,
    ValueError,
    TypeError,
    KeyError,
    OverflowError,
    RecursionError,
)


def preparation_command(
    connection: Connection, journal: DurableJournal, reference: EvidenceRef
) -> ports.RetainedCommand:
    row = (
        connection.execute(
            select(commands).where(commands.c.operation_id == reference.operation_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ValueError("Preparation command missing")
    retained = journal.retained(connection, row)
    if not isinstance(retained, ports.RetainedCommand):
        raise ValueError("Preparation requires a retained command")
    resources = tuple(pin.resource for pin in reference.resource_versions)
    kinds = {resource.kind for resource in resources}
    packs = {
        resource.identity for resource in resources if resource.kind.startswith("report_pack_")
    }
    if (
        reference.operation != OperationKey("reports.prepare", "1")
        or retained.intent.retry_key.operation != reference.operation
        or retained.receipt.operation != reference.operation
        or len(resources) != 3
        or kinds != {"snapshot", "report_pack_source", "report_pack_artifact_scope"}
        or len(packs) != 1
        or set(resources) != set(retained.intent.resources)
        or set(resources) != set(retained.receipt.resources)
        or not set(retained.intent.expected_versions) <= set(reference.resource_versions)
    ):
        raise ValueError("Preparation original operation/pins differ")
    return retained


class DurableEvidence:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.journal = DurableJournal(database)

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        try:
            return await self.database.transaction(
                lambda c: tuple(self.inspect_one(c, ref) for ref in refs)
            )
        except STORAGE_FAILURES:
            return tuple(EvidenceStatus(ref, Availability.UNAVAILABLE) for ref in refs)

    def inspect_one(self, connection: Connection, reference: EvidenceRef) -> EvidenceStatus:
        try:
            row = (
                connection.execute(
                    select(evidence).where(evidence.c.identity == reference.identity)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return EvidenceStatus(reference, Availability.MISSING)
            stored = decode_evidence(row["reference_bytes"], row["reference_digest"])
            if stored != reference:
                return EvidenceStatus(reference, Availability.INACCESSIBLE)
            if (
                row["operation_id"] != reference.operation_id
                or row["fact_digest"] != reference.content_digest
            ):
                raise ValueError("Evidence linkage differs")
            fact = decode_object(row["fact_bytes"], row["fact_digest"])
            if reference.scope in ("prepared", "quality_evaluated"):
                preparation_command(connection, self.journal, reference)
                validate_preparation(fact, reference)
            elif reference.scope == "snapshot_persisted":
                self._snapshot_fact(connection, reference, fact)
            else:
                return EvidenceStatus(reference, Availability.UNAVAILABLE)
            return EvidenceStatus(reference, Availability.AVAILABLE, StageState.PASSED)
        except STORAGE_FAILURES:
            return EvidenceStatus(reference, Availability.UNAVAILABLE)

    def _snapshot_fact(
        self, connection: Connection, reference: EvidenceRef, fact: JsonObject
    ) -> None:
        if set(fact) != {"operation_id", "feed_id", "producer_version", "content_digest"}:
            raise ValueError("Invalid persisted snapshot fact")
        row = (
            connection.execute(
                select(commands).where(commands.c.operation_id == reference.operation_id)
            )
            .mappings()
            .one()
        )
        retained = self.journal.retained(connection, row)
        if (
            not isinstance(retained, ports.RetainedCommand)
            or reference.operation != OperationKey("snapshot.publish", "1")
            or retained.receipt.operation != reference.operation
        ):
            raise ValueError("Snapshot fact operation differs")
        stored = (
            connection.execute(
                select(snapshots).where(snapshots.c.operation_id == reference.operation_id)
            )
            .mappings()
            .one()
        )
        producer = decode_object(stored["producer_bytes"], stored["content_digest"])
        content = decode_object(stored["snapshot_bytes"], stored["snapshot_digest"])
        preconditions = retained.intent.expected_versions
        if len(preconditions) != 1 or preconditions[0].resource not in retained.intent.resources:
            raise ValueError("Snapshot original precondition differs")
        previous = preconditions[0].version
        revision = 1 if previous == "absent" else int(previous) + 1
        if (
            {
                key: value
                for key, value in content.items()
                if key not in ("received_at", "accepted_at", "content_digest")
            }
            != producer
            or fact
            != {
                "operation_id": reference.operation_id,
                "feed_id": stored["feed_id"],
                "producer_version": str(stored["producer_version"]),
                "content_digest": stored["content_digest"],
            }
            or content["content_digest"] != stored["content_digest"]
            or content["feed_id"] != stored["feed_id"]
            or content["producer_version"] != str(stored["producer_version"])
            or tuple(pin.resource for pin in reference.resource_versions)
            != retained.intent.resources
            or len(reference.resource_versions) != 1
            or reference.resource_versions[0].resource.kind != "feed"
            or reference.resource_versions[0].version != str(revision)
            or reference.resource_versions[0].resource.identity != stored["feed_id"]
        ):
            raise ValueError("Snapshot fact content/pins differ")
