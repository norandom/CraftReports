"""Concrete snapshot resources, fenced local handoffs and bounded health reads."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from craftreport.adapters.storage.bindings import BindingStore
from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.evidence import (
    STORAGE_FAILURES,
    DurableEvidence,
)
from craftreport.adapters.storage.guard import DurableGuard, DurableLease
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import (
    Deployment,
    commands,
    deployment,
    evidence,
    handoffs,
    results,
    snapshots,
)
from craftreport.adapters.storage.serialization import (
    decode_evidence,
    decode_handoff,
    encode_handoff,
)
from craftreport.adapters.storage.snapshots import Fingerprint, Publication, SnapshotStore
from craftreport.application import ports
from craftreport.application.dispatch_ports import RecordedHandoff
from craftreport.application.registry import Codec
from craftreport.contracts import (
    Availability,
    EvidenceRef,
    JsonObject,
    Principal,
    ReceiptState,
    ResourceRef,
)
from craftreport.data.values import Snapshot
from craftreport.runtime.values import BindingState, BindRequest, RunPins


class DurableResources:
    def __init__(
        self,
        database: Database,
        codec: Codec[Snapshot],
        fingerprint: Fingerprint,
        policy: str,
    ) -> None:
        self.database = database
        self.store = SnapshotStore(database, codec, fingerprint, policy)
        self._bindings: BindingStore | None = None
        self.guard = DurableGuard(database, self.combined_read)

    def configure_bindings(
        self,
        request: Codec[BindRequest],
        result: Codec[
            BindingState
            | RunPins
            | ports.Missing
            | ports.ServiceUnavailable
            | ports.VersionConflict
        ],
    ) -> None:
        if self._bindings is not None:
            raise ValueError("Binding codecs already configured")
        self._bindings = BindingStore(self.database, self.store, request, result)

    @property
    def bindings(self) -> BindingStore:
        if self._bindings is None:
            raise ValueError("Binding services unavailable")
        return self._bindings

    def verify_binding(
        self, connection: Connection, reference: EvidenceRef, fact: JsonObject
    ) -> BindingState:
        return self.bindings.verify_fact(connection, reference, fact)

    def combined_read(
        self, connection: Connection, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing:
        return (
            self.bindings.read(connection, resource)
            if resource.kind in ("binding", "run")
            else self.store.read(connection, resource)
        )

    async def read(
        self, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing | ports.ServiceUnavailable:
        try:
            return await self.database.transaction(
                lambda connection: self.combined_read(connection, resource)
            )
        except (StorageUnavailable, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return ports.ServiceUnavailable("resources")

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        if (
            not isinstance(guard, DurableLease)
            or guard.owner is not self.guard
            or not self.guard.is_current(guard)
            or resource not in tuple(pin.resource for pin in self.guard.preconditions(guard))
        ):
            return ports.GuardLost()
        try:
            if resource.kind == "binding":
                return await self.database.transaction(
                    lambda c: self.bindings.commit(c, resource, change, guard)
                )
            publication = self.store.prepare(change)
            if resource != ResourceRef("feed", publication.snapshot.feed_id):
                raise ValueError("Publication resource mismatch")
            current = await guard.assert_current()
            if not isinstance(current, ports.GuardCurrent):
                return current
            return await self.database.transaction(
                lambda connection: self._commit(connection, publication, guard)
            )
        except (StorageUnavailable, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            return ports.ServiceUnavailable("effects")

    def _commit(
        self, connection: Connection, publication: Publication, guard: DurableLease
    ) -> ports.ResourceEffectResult:
        current = guard.check(connection)
        if not isinstance(current, ports.GuardCurrent):
            return current
        return self.store.commit(connection, publication, self.guard.preconditions(guard))


def _handoff_command(
    connection: Connection, journal: DurableJournal, handoff: RecordedHandoff
) -> ports.RetainedCommand:
    row = (
        connection.execute(select(commands).where(commands.c.operation_id == handoff.operation_id))
        .mappings()
        .one()
    )
    retained = journal.retained(connection, row)
    if (
        not isinstance(retained, ports.RetainedCommand)
        or (row["deployment_scope"], row["subject"], retained.intent.expected_versions)
        != (handoff.principal.deployment_scope, handoff.principal.subject, handoff.versions)
        or any(pin.resource not in retained.intent.resources for pin in handoff.versions)
    ):
        raise ValueError("Handoff command ownership/pins differ")
    return retained


class DurableHandoffs:
    def __init__(self, database: Database, guard: DurableGuard) -> None:
        if guard.database is not database:
            raise ValueError("Handoff guard belongs to another database")
        self.database, self.guard = database, guard
        self.journal = DurableJournal(database)
        self._authority: dict[tuple[str, str], tuple[RecordedHandoff, DurableLease]] = {}
        self._closed = False

    def close(self) -> None:
        self._closed = True
        self._authority.clear()

    async def record(self, handoff: RecordedHandoff) -> None:
        try:
            if self._closed:
                raise ValueError("Handoff lifetime closed")
            key = handoff.operation_id, handoff.reference
            lease = self.guard.capture(handoff.operation_id, handoff.versions)
            payload, digest = encode_handoff(handoff)
            created = False

            def write(connection: Connection) -> None:
                nonlocal created
                command = _handoff_command(connection, self.journal, handoff)
                prior = (
                    connection.execute(
                        select(handoffs).where(handoffs.c.operation_id == handoff.operation_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if prior is not None:
                    if (prior["reference"], prior["handoff_bytes"], prior["handoff_digest"]) != (
                        handoff.reference,
                        payload,
                        digest,
                    ) or self._authority.get(key) != (handoff, lease):
                        raise ValueError("Immutable original handoff differs")
                else:
                    if command.receipt.state is not ReceiptState.ACCEPTED:
                        raise ValueError("External handoff transfer unsupported")
                    created = True
                    connection.execute(
                        insert(handoffs).values(
                            operation_id=handoff.operation_id,
                            reference=handoff.reference,
                            handoff_bytes=payload,
                            handoff_digest=digest,
                        )
                    )
                saved = (
                    connection.execute(
                        select(handoffs).where(
                            handoffs.c.operation_id == handoff.operation_id,
                            handoffs.c.reference == handoff.reference,
                        )
                    )
                    .mappings()
                    .one()
                )
                if decode_handoff(saved["handoff_bytes"], saved["handoff_digest"]) != handoff:
                    raise ValueError("Handoff readback differs")

            try:
                await self.database.transaction(write)
            except StorageUnavailable:
                if not created and self._authority.get(key) != (handoff, lease):
                    raise
            await self._confirm(handoff, lease)
        except STORAGE_FAILURES as error:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("handoffs")) from error

    async def _confirm(self, handoff: RecordedHandoff, lease: DurableLease) -> None:
        if self._closed or not self.guard.is_current(lease):
            raise ValueError("Handoff authority expired")
        key = handoff.operation_id, handoff.reference
        self._authority[key] = handoff, lease
        if lease.task is not None:
            lease.task.add_done_callback(lambda _: self._authority.pop(key, None))
        if (
            await self.inspect(handoff.principal, handoff.operation_id, handoff.reference)
            != handoff
        ):
            raise StorageUnavailable("Exact handoff acknowledgement unavailable")

    async def inspect(
        self, principal: Principal, operation_id: str, reference: str
    ) -> RecordedHandoff | ports.Missing | ports.ServiceUnavailable:
        def read(connection: Connection) -> RecordedHandoff | ports.Missing:
            row = (
                connection.execute(
                    select(handoffs).where(
                        handoffs.c.operation_id == operation_id, handoffs.c.reference == reference
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return ports.Missing()
            handoff = decode_handoff(row["handoff_bytes"], row["handoff_digest"])
            if (
                handoff.operation_id,
                handoff.reference,
                handoff.principal.deployment_scope,
                handoff.principal.subject,
            ) != (operation_id, reference, principal.deployment_scope, principal.subject):
                raise ValueError("Handoff lookup differs")
            _handoff_command(connection, self.journal, handoff)
            return handoff

        try:
            if self._closed:
                raise ValueError("Handoff lifetime closed")
            found = await self.database.transaction(read)
            if self._closed:
                raise ValueError("Handoff lifetime closed")
            if isinstance(found, RecordedHandoff):
                authority = self._authority.get((operation_id, reference))
                if (
                    self._closed
                    or authority is None
                    or authority[0] != found
                    or not self.guard.is_active(authority[1])
                    or self.guard.preconditions(authority[1]) != found.versions
                ):
                    raise ValueError("Historical owner has no current authority")
            return found
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("handoffs")


type HealthProbe = Callable[[], Awaitable[ports.ServiceUnavailable | None]]
_STORAGE_SERVICES = frozenset(
    {"journal", "guard", "resources", "effects", "results", "evidence", "handoffs"}
)


@dataclass(frozen=True, slots=True)
class RetentionReport:
    deployment: Deployment
    retained_kinds: tuple[str, ...] = (
        "snapshots",
        "retry_identities",
        "receipts",
        "results",
        "bindings",
        "runs",
        "evidence",
    )
    removal: Literal["explicit-offline-only"] = "explicit-offline-only"


class DurableHealth:
    def __init__(
        self,
        database: Database,
        resources: DurableResources,
        owner_probes: Mapping[str, HealthProbe],
    ) -> None:
        if resources.database is not database or _STORAGE_SERVICES.intersection(owner_probes):
            raise ValueError("Storage health cannot be overridden")
        self.database, self.resources = database, resources
        self.probes = MappingProxyType(dict(owner_probes))
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def _deployment(self, connection: Connection) -> Deployment:
        row = connection.execute(select(deployment).limit(2)).mappings().one()
        actual = Deployment(
            row["identity"], row["epoch"], row["retention_profile"], row["configured_limits"]
        )
        if (
            row["singleton"] != 1
            or row["schema_version"] != 6
            or actual != self.database.deployment
        ):
            raise ValueError("Retained deployment changed")
        return actual

    async def retention(self) -> RetentionReport | ports.ServiceUnavailable:
        try:
            actual = await self.database.transaction(self._deployment)
            if self._closed:
                raise ValueError("Health lifetime closed")
            return RetentionReport(actual)
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("retention")

    def _probe(self, connection: Connection, name: str) -> None:
        self._deployment(connection)
        row = connection.execute(select(commands).limit(1)).mappings().one_or_none()
        if row is not None:
            DurableJournal(self.database).retained(connection, row)
        table = {
            "results": results,
            "evidence": evidence,
            "handoffs": handoffs,
            "resources": snapshots,
            "effects": snapshots,
        }.get(name)
        if table is None:
            return
        row = connection.execute(select(table).limit(1)).mappings().one_or_none()
        if row is None:
            return
        if name == "results":
            principal = Principal(row["deployment_scope"], row["subject"], frozenset())
            if DurableResults(self.database).read_retained(
                connection, principal, row["operation_id"], row["identity"]
            ).availability not in (Availability.AVAILABLE, Availability.MISSING):
                raise ValueError("Retained result ownership/link unavailable")
        elif name == "evidence":
            reference = decode_evidence(row["reference_bytes"], row["reference_digest"])
            if DurableEvidence(self.database).inspect_one(
                connection, reference
            ).availability not in (Availability.AVAILABLE, Availability.MISSING):
                raise ValueError("Retained evidence unavailable")
        elif name == "handoffs":
            record = decode_handoff(row["handoff_bytes"], row["handoff_digest"])
            if (record.operation_id, record.reference) != (row["operation_id"], row["reference"]):
                raise ValueError("Retained handoff key differs")
            _handoff_command(connection, DurableJournal(self.database), record)
        else:
            self.resources.store.read(
                connection, ResourceRef("snapshot", f"{row['feed_id']}:{row['producer_version']}")
            )

    async def check(self, required: tuple[str, ...]) -> ports.ServiceUnavailable | None:
        name = "health"
        try:
            if isinstance(await self.retention(), ports.ServiceUnavailable):
                return ports.ServiceUnavailable(name)
            for name in required:
                if name in _STORAGE_SERVICES:
                    await self.database.transaction(lambda c: self._probe(c, name))
                else:
                    probe = self.probes.get(name)
                    if probe is None or await probe() is not None:
                        return ports.ServiceUnavailable(name)
                if isinstance(await self.retention(), ports.ServiceUnavailable):
                    return ports.ServiceUnavailable(name)
            return None
        except Exception:
            return ports.ServiceUnavailable(name)
