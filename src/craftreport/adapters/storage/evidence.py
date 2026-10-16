"""Independent retained fact verification through the existing evidence table."""

import re

from sqlalchemy import func, select
from sqlalchemy.engine import Connection, RowMapping

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.schema import commands, evidence, feeds, snapshots
from craftreport.adapters.storage.serialization import (
    DecisionFact,
    decision_frame,
    decode_evidence,
    decode_object,
    decode_tombstone,
    validate_preparation,
)
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    ResourceRef,
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


def snapshot_row(connection: Connection, feed: str, version: int) -> RowMapping | None:
    selected = (snapshots.c.feed_id == feed, snapshots.c.producer_version == version)
    sizes = connection.execute(
        select(
            func.length(snapshots.c.producer_bytes), func.length(snapshots.c.snapshot_bytes)
        ).where(*selected)
    ).one_or_none()
    if sizes is None:
        return None
    if any(type(size) is not int or not 0 < size <= 1_048_576 for size in sizes):
        raise ValueError("Snapshot content exceeds retained bound")
    return connection.execute(select(snapshots).where(*selected)).mappings().one()


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
                if self._snapshot_fact(connection, reference, fact):
                    return EvidenceStatus(reference, Availability.MISSING)
            elif reference.scope == "publication_decided":
                validate_decision(connection, self.database, reference, fact)
            else:
                return EvidenceStatus(reference, Availability.UNAVAILABLE)
            return EvidenceStatus(reference, Availability.AVAILABLE, StageState.PASSED)
        except STORAGE_FAILURES:
            return EvidenceStatus(reference, Availability.UNAVAILABLE)

    def _snapshot_fact(
        self, connection: Connection, reference: EvidenceRef, fact: JsonObject
    ) -> bool:
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
        subject = connection.execute(
            select(feeds.c.subject).where(feeds.c.feed_id == stored["feed_id"])
        ).scalar_one()
        if subject != retained.intent.retry_key.subject:
            raise ValueError("Snapshot feed ownership differs")
        removed = decode_tombstone(
            stored["snapshot_bytes"],
            stored["snapshot_digest"],
            "snapshot",
            self.database.deployment,
            {**stored, "subject": subject},
        )
        preconditions = retained.intent.expected_versions
        if len(preconditions) != 1 or preconditions[0].resource not in retained.intent.resources:
            raise ValueError("Snapshot original precondition differs")
        previous = preconditions[0].version
        revision = 1 if previous == "absent" else int(previous) + 1
        if (
            fact
            != {
                "operation_id": reference.operation_id,
                "feed_id": stored["feed_id"],
                "producer_version": str(stored["producer_version"]),
                "content_digest": stored["content_digest"],
            }
            or tuple(pin.resource for pin in reference.resource_versions)
            != retained.intent.resources
            or len(reference.resource_versions) != 1
            or reference.resource_versions[0].resource.kind != "feed"
            or reference.resource_versions[0].version != str(revision)
            or reference.resource_versions[0].resource.identity != stored["feed_id"]
        ):
            raise ValueError("Snapshot fact content/pins differ")
        if removed:
            if stored["producer_bytes"] != stored["snapshot_bytes"]:
                raise ValueError("One-sided snapshot removal")
            return True
        producer = decode_object(stored["producer_bytes"], stored["content_digest"])
        content = decode_object(stored["snapshot_bytes"], stored["snapshot_digest"])
        if {
            key: value
            for key, value in content.items()
            if key not in ("received_at", "accepted_at", "content_digest")
        } != producer or (
            content["content_digest"],
            content["feed_id"],
            content["producer_version"],
        ) != (stored["content_digest"], stored["feed_id"], str(stored["producer_version"])):
            raise ValueError("Snapshot content differs")
        return False


def snapshot_evidence(
    connection: Connection, database: Database, operation_id: str
) -> EvidenceStatus:
    rows = (
        connection.execute(select(evidence).where(evidence.c.operation_id == operation_id).limit(3))
        .mappings()
        .all()
    )
    refs = tuple(decode_evidence(row["reference_bytes"], row["reference_digest"]) for row in rows)
    if any(
        ref.identity != row["identity"] or ref.operation_id != operation_id
        for ref, row in zip(refs, rows, strict=True)
    ):
        raise ValueError("Snapshot evidence identity differs")
    matches = tuple(ref for ref in refs if ref.scope == "snapshot_persisted")
    if len(matches) != 1:
        raise ValueError("Original snapshot evidence missing or duplicated")
    status = DurableEvidence(database).inspect_one(connection, matches[0])
    if status.availability not in (Availability.AVAILABLE, Availability.MISSING):
        raise ValueError("Original snapshot evidence unavailable")
    return status


def decision_identity(
    connection: Connection, database: Database, feed: str, version: str, digest: str
) -> str:
    row = snapshot_row(connection, feed, int(version))
    if row is None or row["content_digest"] != digest:
        raise ValueError("Decision retained identity differs")
    snapshot_evidence(connection, database, row["operation_id"])
    return row["operation_id"]


def validate_decision(
    connection: Connection, database: Database, reference: EvidenceRef, fact: JsonObject
) -> DecisionFact:
    item = decision_frame(fact)
    row = (
        connection.execute(select(commands).where(commands.c.operation_id == item.operation_id))
        .mappings()
        .one()
    )
    command = DurableJournal(database).retained(connection, row)
    resource = ResourceRef("feed", item.feed_id)
    pins = (ExpectedVersion(resource, item.feed_revision),)
    subject = connection.execute(
        select(feeds.c.subject).where(feeds.c.feed_id == item.feed_id)
    ).scalar_one()
    if (
        not isinstance(command, ports.RetainedCommand)
        or reference.operation_id != item.operation_id
        or reference.operation != OperationKey("snapshot.publish", "1")
        or command.receipt.operation != reference.operation
        or command.intent.retry_key.operation != reference.operation
        or command.intent.retry_key.subject != subject
        or command.intent.retry_key.deployment_scope != database.deployment.identity
        or command.intent.resources != (resource,)
        or command.receipt.resources != (resource,)
        or command.receipt.expected_versions != command.intent.expected_versions
        or len(command.intent.expected_versions) != 1
        or command.intent.expected_versions[0].resource != resource
        or reference.resource_versions != pins
    ):
        raise ValueError("Decision command linkage differs")
    previous = command.intent.expected_versions[0].version
    if previous != "absent" and (
        re.fullmatch(r"[1-9][0-9]*", previous) is None or int(previous) >= 2**63
    ):
        raise ValueError("Invalid original feed revision")
    revision = 0 if previous == "absent" else int(previous)
    if int(item.feed_revision) != revision + (item.status == "accepted") or (
        revision == 0 and item.status != "accepted"
    ):
        raise ValueError("Decision revision differs")
    decision_identity(connection, database, item.feed_id, item.high_water, item.high_water_digest)
    validate_decision_status(connection, database, item)
    return item


def validate_decision_status(
    connection: Connection, database: Database, item: DecisionFact
) -> None:
    requested = (item.requested_version, item.requested_digest)
    retained = (item.retained_version, item.retained_digest)
    if item.status == "stale_version":
        exists = connection.execute(
            select(snapshots.c.operation_id).where(
                snapshots.c.feed_id == item.feed_id,
                snapshots.c.producer_version == int(item.requested_version),
            )
        ).first()
        if (
            retained != (None, None)
            or int(item.requested_version) >= int(item.high_water)
            or exists
        ):
            raise ValueError("Invalid stale decision")
        return
    if item.retained_version is None or item.retained_digest is None:
        raise ValueError("Missing decision retained identity")
    owner = decision_identity(
        connection, database, item.feed_id, item.retained_version, item.retained_digest
    )
    if int(item.retained_version) > int(item.high_water):
        raise ValueError("Decision exceeds high water")
    if item.status == "version_conflict":
        if requested[0] != retained[0] or requested[1] == retained[1]:
            raise ValueError("Invalid conflict decision")
    elif requested != retained:
        raise ValueError("Invalid retained decision")
    if item.status == "accepted":
        support = snapshot_evidence(connection, database, item.operation_id)
        pins = (ExpectedVersion(ResourceRef("feed", item.feed_id), item.feed_revision),)
        if (
            owner != item.operation_id
            or requested != (item.high_water, item.high_water_digest)
            or support.availability is not Availability.AVAILABLE
            or support.reference.resource_versions != pins
        ):
            raise ValueError("Accepted decision lacks exact persistence support")
