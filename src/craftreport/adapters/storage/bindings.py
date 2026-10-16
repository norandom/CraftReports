"""Concrete atomic bindings and immutable runs in the owned SQLite deployment."""

from dataclasses import replace
from typing import cast
from uuid import uuid4

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import STORAGE_FAILURES, DurableEvidence
from craftreport.adapters.storage.guard import DurableLease
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import bindings, commands, evidence, feeds, runs
from craftreport.adapters.storage.serialization import decode_object, encode_evidence, encode_object
from craftreport.adapters.storage.snapshots import SnapshotStore
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Principal,
    ReceiptState,
    ResourceRef,
    StageState,
)
from craftreport.data.requirements import check_completeness
from craftreport.runtime.values import BindingState, BindRequest, InspectRequest, RunPins

_KEY = OperationKey("runtime.bind", "1")


def transition(before: BindingState | None, request: BindRequest) -> BindingState:
    if before is None:
        return BindingState(request.spec, 1, 1)
    return (
        before
        if before.spec == request.spec
        else BindingState(request.spec, before.generation + 1, before.revision + 1)
    )


def validate_fact(
    connection: Connection,
    store: SnapshotStore,
    reference: EvidenceRef,
    fact: JsonObject,
    request_codec: Codec[BindRequest],
    result_codec: Codec[
        BindingState | RunPins | ports.Missing | ports.ServiceUnavailable | ports.VersionConflict
    ],
) -> BindingState:
    if set(fact) != {"schema_version", "before", "after"} or fact["schema_version"] != "1":
        raise ValueError("Invalid binding fact")
    encode_object(fact, max_bytes=2_097_152)
    before = (
        None if fact["before"] is None else result_codec.decode(cast(JsonObject, fact["before"]))
    )
    after = result_codec.decode(cast(JsonObject, fact["after"]))
    if (
        not isinstance(after, BindingState)
        or before is not None
        and not isinstance(before, BindingState)
    ):
        raise ValueError("Invalid binding fact states")
    request = BindRequest(after.spec, 0 if before is None else before.generation)
    row = (
        connection.execute(
            select(commands).where(commands.c.operation_id == reference.operation_id)
        )
        .mappings()
        .one()
    )
    retained = store.journal.retained(connection, row)
    if not isinstance(retained, ports.RetainedCommand):
        raise ValueError("Binding requires retained command")
    intent = retained.intent
    resource = ResourceRef("binding", after.spec.binding_id)
    feed = ResourceRef("feed", after.spec.feed_id)
    versions = intent.expected_versions
    expected = {resource: "absent" if before is None else str(before.revision)}
    owner = connection.execute(
        select(feeds.c.subject).where(feeds.c.feed_id == feed.identity)
    ).scalar_one()
    if (
        reference.operation != _KEY
        or retained.receipt.operation != _KEY
        or intent.retry_key.operation != _KEY
        or intent.retry_key.subject != owner
        or intent.retry_key.deployment_scope != store.database.deployment.identity
        or intent.resources != (resource, feed)
        or retained.receipt.resources != intent.resources
        or retained.receipt.expected_versions != versions
        or len(versions) != 2
        or tuple(p.resource for p in versions) != (resource, feed)
        or any(p.version != expected[p.resource] for p in versions if p.resource in expected)
        or intent.normalization_policy != store.policy
        or intent.fingerprint
        != store.fingerprint(_KEY, request_codec.encode(request), intent.resources, versions)
        or transition(before, request) != after
        or before is not None
        and before.spec.binding_id != after.spec.binding_id
        or reference.resource_versions
        != (ExpectedVersion(resource, str(after.revision)), versions[1])
    ):
        raise ValueError("Binding fact admission or transition differs")
    return after


class BindingStore:
    def __init__(
        self,
        database: Database,
        snapshots: SnapshotStore,
        request_codec: Codec[BindRequest],
        result_codec: Codec[
            BindingState
            | RunPins
            | ports.Missing
            | ports.ServiceUnavailable
            | ports.VersionConflict
        ],
    ) -> None:
        self.database, self.snapshots = database, snapshots
        self.request_codec, self.result_codec = request_codec, result_codec

    def verify_fact(
        self, connection: Connection, reference: EvidenceRef, fact: JsonObject
    ) -> BindingState:
        return validate_fact(
            connection, self.snapshots, reference, fact, self.request_codec, self.result_codec
        )

    def read(
        self, connection: Connection, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing:
        table, key, prefix = (
            (bindings, bindings.c.binding_id, "binding")
            if resource.kind == "binding"
            else (runs, runs.c.run_id, "run")
        )
        row = (
            connection.execute(select(table).where(key == resource.identity))
            .mappings()
            .one_or_none()
        )
        if row is None:
            return ports.Missing()
        value = self.result_codec.decode(
            decode_object(row[prefix + "_bytes"], row[prefix + "_digest"])
        )
        if isinstance(value, BindingState):
            command = (
                connection.execute(
                    select(commands).where(commands.c.operation_id == row["operation_id"])
                )
                .mappings()
                .one()
            )
            original = self.snapshots.journal.retained(connection, command)
            if (
                not isinstance(original, ports.RetainedCommand)
                or (command["subject"], command["deployment_scope"], original.receipt.operation)
                != (row["subject"], self.database.deployment.identity, _KEY)
                or ResourceRef("binding", value.spec.binding_id) not in original.intent.resources
            ):
                raise ValueError("Binding command owner or identity differs")
            if (value.spec.binding_id, value.generation, value.revision) != (
                row["binding_id"],
                row["generation"],
                row["revision"],
            ):
                raise ValueError("Binding columns differ")
            if value.selected_run_id is not None:
                selected = (
                    connection.execute(select(runs).where(runs.c.run_id == value.selected_run_id))
                    .mappings()
                    .one()
                )
                if (selected["binding_id"], selected["binding_generation"]) != (
                    value.spec.binding_id,
                    value.generation,
                ):
                    raise ValueError("Selected run differs")
            token = str(value.revision)
        elif isinstance(value, RunPins):
            if (
                value.run_id,
                value.binding_id,
                value.binding_generation,
                value.snapshot.feed_id,
                value.snapshot.producer_version,
            ) != (
                row["run_id"],
                row["binding_id"],
                row["binding_generation"],
                row["feed_id"],
                row["producer_version"],
            ):
                raise ValueError("Run columns differ")
            token = row["run_digest"]
        else:
            raise ValueError("Invalid retained binding value")
        return ports.ResourceSnapshot(
            ExpectedVersion(resource, token), self.result_codec.encode(value)
        )

    def _owned(
        self, connection: Connection, principal: Principal, request: InspectRequest
    ) -> BindingState | RunPins | ports.Missing:
        query = (
            select(bindings.c.subject).where(bindings.c.binding_id == request.identity)
            if request.kind == "binding"
            else select(bindings.c.subject).join(runs).where(runs.c.run_id == request.identity)
        )
        subject = connection.execute(query).scalar_one_or_none()
        if (
            principal.deployment_scope != self.database.deployment.identity
            or subject is not None
            and subject != principal.subject
        ):
            raise ValueError("Binding owner differs")
        observed = self.read(connection, ResourceRef(request.kind, request.identity))
        if isinstance(observed, ports.Missing):
            return observed
        value = self.result_codec.decode(observed.content)
        if not isinstance(value, (BindingState, RunPins)):
            raise ValueError("Invalid retained content")
        if isinstance(value, RunPins):
            self._prepared(connection, principal, value)
        return value

    async def inspect(
        self, principal: Principal, request: InspectRequest
    ) -> BindingState | RunPins | ports.Missing | ports.ServiceUnavailable:
        try:
            return await self.database.transaction(lambda c: self._owned(c, principal, request))
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("bindings")

    def commit(
        self, connection: Connection, resource: ResourceRef, change: JsonObject, guard: DurableLease
    ) -> ports.ResourceEffectResult:
        checked = guard.check(connection)
        if not isinstance(checked, ports.GuardCurrent):
            return checked
        if set(change) != {"operation_id", "request"}:
            raise ValueError("Invalid binding effect")
        request = self.request_codec.decode(cast(JsonObject, change["request"]))
        if resource != ResourceRef("binding", request.spec.binding_id):
            raise ValueError("Binding resource differs")
        operation_id = cast(str, change["operation_id"])
        command = (
            connection.execute(select(commands).where(commands.c.operation_id == operation_id))
            .mappings()
            .one()
        )
        retained = self.snapshots.journal.retained(connection, command)
        if not isinstance(retained, ports.RetainedCommand) or retained.receipt.state not in (
            ReceiptState.ACCEPTED,
            ReceiptState.PENDING,
        ):
            raise ValueError("Binding command is not admitted")
        principal = Principal(command["deployment_scope"], command["subject"], frozenset())
        old = self._owned(connection, principal, InspectRequest("binding", request.spec.binding_id))
        before = old if isinstance(old, BindingState) else None
        if request.expected_generation != (0 if before is None else before.generation):
            return ports.VersionConflict(
                guard.owner.preconditions(guard), guard.owner.preconditions(guard)
            )
        after = transition(before, request)
        pins = (ExpectedVersion(resource, str(after.revision)), guard.owner.preconditions(guard)[1])
        fact: JsonObject = {
            "schema_version": "1",
            "before": None if before is None else self.result_codec.encode(before),
            "after": self.result_codec.encode(after),
        }
        payload, digest = encode_object(fact, max_bytes=2_097_152)
        ref = EvidenceRef(uuid4().hex, "binding_persisted", operation_id, _KEY, pins, digest)
        self.verify_fact(connection, ref, fact)
        self._write(connection, after, principal.subject, operation_id, before is None)
        ref_bytes, ref_digest = encode_evidence(ref)
        connection.execute(
            insert(evidence).values(
                identity=ref.identity,
                operation_id=operation_id,
                reference_bytes=ref_bytes,
                reference_digest=ref_digest,
                fact_bytes=payload,
                fact_digest=digest,
            )
        )
        if (
            self._owned(connection, principal, InspectRequest("binding", request.spec.binding_id))
            != after
            or DurableEvidence(self.database, self.verify_fact)
            .inspect_one(connection, ref)
            .availability
            is not Availability.AVAILABLE
        ):
            raise ValueError("Binding readback differs")
        return ports.ResourceEffect(
            EffectDisposition.APPLIED if before != after else EffectDisposition.NONE, pins, (ref,)
        )

    def _write(
        self,
        connection: Connection,
        state: BindingState,
        subject: str,
        operation_id: str,
        create: bool = False,
    ) -> None:
        payload, digest = encode_object(self.result_codec.encode(state))
        values = dict(
            subject=subject,
            generation=state.generation,
            revision=state.revision,
            operation_id=operation_id,
            binding_bytes=payload,
            binding_digest=digest,
        )
        statement = (
            insert(bindings).values(binding_id=state.spec.binding_id, **values)
            if create
            else update(bindings)
            .where(bindings.c.binding_id == state.spec.binding_id)
            .values(**values)
        )
        connection.execute(statement)

    def _prepared(self, connection: Connection, principal: Principal, pins: RunPins) -> None:
        row = (
            connection.execute(
                select(commands).where(commands.c.operation_id == pins.prepared_operation_id)
            )
            .mappings()
            .one()
        )
        retained = DurableJournal(self.database).retained(connection, row)
        if not isinstance(retained, ports.RetainedCommand):
            raise ValueError("Preparation requires an original command")
        receipt = retained.receipt
        result = DurableResults(self.database).read_retained(
            connection, principal, pins.prepared_operation_id, pins.prepared_result_ref
        )
        if (
            receipt.result_ref != pins.prepared_result_ref
            or result.availability is not Availability.AVAILABLE
            or receipt.state in (ReceiptState.ACCEPTED, ReceiptState.PENDING)
        ):
            raise ValueError("Retained preparation unavailable")
        prepared = tuple(stage for stage in receipt.stages if stage.stage == "prepared")
        if (
            len(prepared) != 1
            or prepared[0].state is not StageState.PASSED
            or not prepared[0].evidence
        ):
            raise ValueError("Retained preparation stage unavailable")
        for reference in prepared[0].evidence:
            status = DurableEvidence(self.database).inspect_one(connection, reference)
            if (
                reference.operation_id != pins.prepared_operation_id
                or status.availability is not Availability.AVAILABLE
                or status.verification is not StageState.PASSED
            ):
                raise ValueError("Retained preparation evidence unavailable")

    async def select_run(
        self, principal: Principal, expected: BindingState, pins: RunPins
    ) -> RunPins | ports.VersionConflict | ports.ServiceUnavailable:
        try:
            return await self.database.transaction(
                lambda c: self._select(c, principal, expected, pins)
            )
        except STORAGE_FAILURES:
            return ports.ServiceUnavailable("run_selection")

    def _select(
        self, connection: Connection, principal: Principal, expected: BindingState, pins: RunPins
    ) -> RunPins | ports.VersionConflict:
        current = self._owned(
            connection, principal, InspectRequest("binding", expected.spec.binding_id)
        )
        if current != expected:
            return ports.VersionConflict((), ())
        if not isinstance(current, BindingState):
            raise ValueError("Missing binding")
        shared = (
            "definition",
            "template",
            "theme",
            "pack",
            "resolved_parameters",
            "parameter_digest",
            "validation_scope",
            "target",
        )
        if (pins.binding_id, pins.binding_generation, pins.snapshot.feed_id) != (
            current.spec.binding_id,
            current.generation,
            current.spec.feed_id,
        ) or any(getattr(pins, n) != getattr(current.spec, n) for n in shared):
            raise ValueError("Selected pins differ")
        snapshot = self.snapshots.read(
            connection,
            ResourceRef("snapshot", f"{pins.snapshot.feed_id}:{pins.snapshot.producer_version}"),
        )
        if (
            not isinstance(snapshot, ports.ResourceSnapshot)
            or snapshot.version.version != pins.snapshot.content_digest
            or check_completeness(
                self.snapshots.codec.decode(snapshot.content), current.spec.requirements
            )
        ):
            raise ValueError("Selected snapshot unavailable or incomplete")
        self._prepared(connection, principal, pins)
        existing = self.read(connection, ResourceRef("run", pins.run_id))
        if not isinstance(existing, ports.Missing):
            if self.result_codec.decode(existing.content) != pins:
                raise ValueError("Immutable run differs")
            return pins
        payload, digest = encode_object(self.result_codec.encode(pins))
        connection.execute(
            insert(runs).values(
                run_id=pins.run_id,
                binding_id=pins.binding_id,
                binding_generation=pins.binding_generation,
                feed_id=pins.snapshot.feed_id,
                producer_version=pins.snapshot.producer_version,
                run_bytes=payload,
                run_digest=digest,
            )
        )
        owner = (
            connection.execute(select(bindings).where(bindings.c.binding_id == pins.binding_id))
            .mappings()
            .one()
        )
        self._write(
            connection,
            replace(current, revision=current.revision + 1, selected_run_id=pins.run_id),
            principal.subject,
            owner["operation_id"],
        )
        if self._owned(connection, principal, InspectRequest("run", pins.run_id)) != pins:
            raise ValueError("Run readback differs")
        return pins
