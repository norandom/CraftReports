"""Typed scripted doubles prove port expressiveness, not provider/runtime guarantees."""

import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import cast

import pytest

from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CapabilityRequirement,
    CapabilityVersion,
    Catalog,
    CommandIntent,
    Diagnostic,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    InvocationEnvelope,
    InvocationResult,
    JsonObject,
    JsonValue,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    ResourceRef,
    ResultReadback,
    RetryKey,
    StageState,
)

KEY = OperationKey("fixture.set", "1")
RESOURCE = ResourceRef("fixture", "target")
PIN = ExpectedVersion(RESOURCE, "2")
PRINCIPAL = Principal("test-deployment", "alice", frozenset({"inspect", "change"}))
RETRY = RetryKey(PRINCIPAL.deployment_scope, PRINCIPAL.subject, KEY, "retry")
REF = EvidenceRef("proof", "synthetic", "operation", KEY, (PIN,))


def receipt(state: ReceiptState = ReceiptState.ACCEPTED) -> Receipt:
    return Receipt(
        "operation",
        KEY,
        "correlation",
        1,
        state,
        (),
        (RESOURCE,),
        (PIN,),
        None,
        None,
        (),
        (),
        (),
        "epoch",
        "temporary-no-eviction",
    )


def intent() -> CommandIntent:
    return CommandIntent(
        RETRY, "fingerprint", "normalization-v1", "correlation", (), (RESOURCE,), (PIN,)
    )


class JournalDouble:
    """Scripted responses; intentionally no simulated atomic storage implementation."""

    def __init__(self, admission: ports.Admission) -> None:
        self.admission = admission

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        if key != RETRY:
            return ports.Missing()
        if isinstance(self.admission, ports.Admitted):
            return ports.RetainedCommand(intent(), self.admission.receipt)
        raise ports.ServiceUnavailableError(ports.ServiceUnavailable("journal"))

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        return self.admission

    async def record(
        self, operation_id: str, expected_revision: int, update: ports.ReceiptUpdate
    ) -> ports.RecordResult:
        if isinstance(self.admission, ports.ServiceUnavailable):
            raise ports.ServiceUnavailableError(self.admission)
        if operation_id != "operation":
            raise ports.ReceiptMissingError(operation_id)
        if expected_revision != 1:
            return ports.RevisionConflict(1)
        return replace(receipt(), state=update.state, revision=2)

    async def read(self, operation_id: str) -> ports.ReceiptRead:
        if isinstance(self.admission, ports.ServiceUnavailable):
            raise ports.ServiceUnavailableError(self.admission)
        return receipt() if operation_id == "operation" else ports.Missing()

    async def record_query(self, observation: ports.QueryObservation) -> Receipt:
        if isinstance(self.admission, ports.ServiceUnavailable):
            raise ports.ServiceUnavailableError(self.admission)
        return replace(
            receipt(observation.update.state),
            operation=observation.operation,
            operation_id=observation.operation_id,
        )


class LeaseDouble:
    def __init__(self, check: ports.GuardCheck) -> None:
        self.check = check

    @property
    def authoritative_versions(self) -> tuple[ExpectedVersion, ...]:
        return (PIN,)

    async def assert_current(self) -> ports.GuardCheck:
        return self.check


class GuardDouble:
    def __init__(
        self, result: ports.GuardLease | ports.VersionConflict | ports.ServiceUnavailable
    ) -> None:
        self.result = result
        self.released = False

    @asynccontextmanager
    async def acquire(self, preconditions: ports.Preconditions) -> AsyncGenerator[ports.GuardLease]:
        try:
            if isinstance(self.result, (ports.VersionConflict, ports.ServiceUnavailable)):
                raise ports.GuardAcquisitionError(self.result)
            yield self.result
        finally:
            self.released = True


class InspectionDouble:
    def __init__(self, decision: ports.CapabilityDecision | None = None) -> None:
        self.decision = decision or ports.CapabilitiesSupported(
            (CapabilityVersion("fixture", "1"),)
        )

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        return tuple(
            EvidenceStatus(ref, state) for ref, state in zip(refs, Availability, strict=True)
        )

    async def check(
        self, requirements: tuple[CapabilityRequirement, ...], resources: tuple[ResourceRef, ...]
    ) -> ports.CapabilityDecision:
        return self.decision

    async def read(
        self, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing | ports.ServiceUnavailable:
        return ports.ResourceSnapshot(PIN, {"value": 2})


class EffectDouble:
    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        return ports.ResourceEffect(EffectDisposition.APPLIED, (PIN,), (REF,))


class AccessDouble:
    def __init__(self, decision: ports.AccessDecision | None = None) -> None:
        self.decision = decision

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        if self.decision is not None:
            return self.decision
        return ports.AccessAllowed() if principal == PRINCIPAL else ports.AccessDenied()


class FacadeDouble:
    async def invoke(self, principal: Principal, request: InvocationEnvelope) -> InvocationResult:
        return receipt()

    async def catalog(self, principal: Principal) -> Catalog:
        if principal != PRINCIPAL:
            raise ports.CatalogRejected(
                Rejection(
                    "catalog", Diagnostic(KEY, "access", "denied", RecoveryDisposition.DO_NOT_RETRY)
                )
            )
        return Catalog((), (), "epoch", "temporary")

    async def inspect(self, principal: Principal, operation_id: str) -> Receipt | Rejection:
        return receipt()

    async def read_result(
        self, principal: Principal, operation_id: str
    ) -> ResultReadback | Rejection:
        return Rejection(
            "readback", Diagnostic(KEY, "result", "result_missing", RecoveryDisposition.INSPECT)
        )


def test_admission_is_discriminated_and_retains_identity() -> None:
    retained = ports.RetainedCommand(intent(), receipt())
    outcomes: tuple[ports.Admission, ...] = (
        ports.Admitted(receipt()),
        ports.Existing(retained),
        ports.AdmissionConflict(),
        ports.ServiceUnavailable("journal"),
    )
    observed: list[str] = []
    for outcome in outcomes:
        journal: ports.OperationJournal = JournalDouble(outcome)
        result = asyncio.run(journal.admit(intent()))
        observed.append(result.kind)
        if result.kind == "admitted":
            assert result.receipt.operation_id == "operation"
        elif result.kind == "existing":
            assert result.command.intent.fingerprint == "fingerprint"
            assert result.command.receipt.operation_id == "operation"
    assert observed == ["admitted", "existing", "conflict", "unavailable"]


def test_journal_missing_unavailability_and_conditional_updates() -> None:
    journal: ports.OperationJournal = JournalDouble(ports.Admitted(receipt()))
    assert isinstance(asyncio.run(journal.find(RETRY)), ports.RetainedCommand)
    other = replace(RETRY, subject="bob")
    assert isinstance(asyncio.run(journal.find(other)), ports.Missing)
    unavailable: ports.OperationJournal = JournalDouble(ports.ServiceUnavailable("journal"))
    with pytest.raises(ports.ServiceUnavailableError) as failed_lookup:
        asyncio.run(unavailable.find(RETRY))
    assert failed_lookup.value.reason.kind == "unavailable"
    assert isinstance(asyncio.run(journal.read("unknown")), ports.Missing)
    update = ports.ReceiptUpdate(ReceiptState.FAILED)
    conflict = asyncio.run(journal.record("operation", 99, update))
    assert isinstance(conflict, ports.RevisionConflict) and conflict.current_revision == 1
    result = asyncio.run(journal.record("operation", 1, update))
    assert isinstance(result, Receipt) and result.revision == 2
    query = ports.QueryObservation(
        "query", PRINCIPAL, KEY, "request", (), (RESOURCE,), (PIN,), update
    )
    observed = asyncio.run(journal.record_query(query))
    assert observed.state is ReceiptState.FAILED
    assert observed.operation_id == "query"
    with pytest.raises(ports.ServiceUnavailableError):
        asyncio.run(unavailable.read("operation"))
    with pytest.raises(ports.ServiceUnavailableError):
        asyncio.run(unavailable.record("operation", 1, update))
    with pytest.raises(ports.ServiceUnavailableError):
        asyncio.run(unavailable.record_query(query))
    with pytest.raises(ports.ReceiptMissingError) as missing:
        asyncio.run(journal.record("unknown", 1, update))
    assert missing.value.reason.kind == "missing"


def test_guard_exposes_authoritative_versions_loss_and_unavailability() -> None:
    checks: tuple[ports.GuardCheck, ...] = (
        ports.GuardCurrent(),
        ports.GuardLost(),
        ports.ServiceUnavailable("versions"),
        ports.VersionConflict((PIN,), (replace(PIN, version="3"),)),
    )
    for check in checks:
        lease: ports.GuardLease = LeaseDouble(check)
        assert lease.authoritative_versions == (PIN,)
        assert asyncio.run(lease.assert_current()) == check

    async def acquire(
        result: ports.GuardLease | ports.VersionConflict | ports.ServiceUnavailable,
    ) -> None:
        double = GuardDouble(result)
        guard: ports.ExecutionGuard = double
        if isinstance(result, (ports.VersionConflict, ports.ServiceUnavailable)):
            with pytest.raises(ports.GuardAcquisitionError) as caught:
                async with guard.acquire((PIN,)):
                    pytest.fail("Failed acquisition must not grant a lease")
            assert caught.value.reason == result
        else:
            async with guard.acquire((PIN,)) as observed:
                assert observed is result
        assert double.released

    for result in (LeaseDouble(ports.GuardCurrent()), checks[2], checks[3]):
        asyncio.run(acquire(result))


def test_read_services_report_every_evidence_state_and_access_decision() -> None:
    double = InspectionDouble()
    services = ports.ReadServices(double, double, double)
    statuses = asyncio.run(services.evidence.inspect((REF,) * 4))
    assert tuple(status.availability for status in statuses) == tuple(Availability)
    assert all(status.verification is StageState.PENDING for status in statuses)
    supported = asyncio.run(services.capabilities.check((), (RESOURCE,)))
    assert isinstance(supported, ports.CapabilitiesSupported)
    policy: ports.AccessPolicy = AccessDouble()
    action = ports.OperationAccess(KEY, (RESOURCE,))
    assert isinstance(asyncio.run(policy.authorize(PRINCIPAL, action)), ports.AccessAllowed)
    assert isinstance(
        asyncio.run(policy.authorize(replace(PRINCIPAL, subject="bob"), action)), ports.AccessDenied
    )
    facade: ports.Facade = FacadeDouble()
    assert isinstance(asyncio.run(facade.catalog(PRINCIPAL)), Catalog)
    assert isinstance(asyncio.run(facade.inspect(PRINCIPAL, "operation")), Receipt)
    with pytest.raises(ports.CatalogRejected) as denied:
        asyncio.run(facade.catalog(replace(PRINCIPAL, subject="bob")))
    assert denied.value.rejection.diagnostic.code == "denied"


def test_contexts_and_owned_snapshots_have_narrow_immutable_surfaces() -> None:
    double = InspectionDouble()
    reads = ports.ReadServices(double, double, double)
    commands = ports.CommandServices(reads, EffectDouble())
    query = ports.ReadContext("query", PRINCIPAL, reads)
    command = ports.CommandContext(
        "command", PRINCIPAL, LeaseDouble(ports.GuardCurrent()), commands
    )
    assert command.services.reads == query.services
    assert not hasattr(query.services, "effects")
    for context in (query, command):
        assert not hasattr(context, "journal") and not hasattr(context, "registry")
        with pytest.raises(FrozenInstanceError):
            setattr(context, "operation_id", "other")
    items: list[JsonValue] = [1, 2]
    source: JsonObject = {"nested": items}
    snapshot = ports.ResourceSnapshot(PIN, source)
    items.append(3)
    assert snapshot.content["nested"] == (1, 2)
    effect = asyncio.run(command.services.effects.apply(RESOURCE, {}, command.guard))
    assert isinstance(effect, ports.ResourceEffect) and effect.effect is EffectDisposition.APPLIED


def test_unavailable_access_and_unsupported_target_modes_remain_explicit() -> None:
    policy: ports.AccessPolicy = AccessDouble(ports.ServiceUnavailable("access"))
    for action in (
        ports.CatalogAccess(),
        ports.ReceiptAccess("operation"),
        ports.OperationAccess(KEY),
    ):
        assert isinstance(
            asyncio.run(policy.authorize(PRINCIPAL, action)), ports.ServiceUnavailable
        )
    required = (CapabilityRequirement("fixture", ">=1", "browser"),)
    outcomes: tuple[ports.CapabilityDecision, ...] = (
        ports.CapabilitiesUnsupported(required),
        ports.ServiceUnavailable("capabilities"),
    )
    for outcome in outcomes:
        resolver: ports.CapabilityResolver = InspectionDouble(outcome)
        result = asyncio.run(resolver.check(required, (RESOURCE,)))
        assert result == outcome
        if result.kind == "unsupported":
            assert result.requirements[0].target_mode == "browser"


def test_port_values_reject_inconsistent_identity_and_availability() -> None:
    with pytest.raises(ValueError):
        ports.Admitted(receipt(ReceiptState.COMPLETE))
    with pytest.raises(ValueError):
        ports.RetainedCommand(intent(), replace(receipt(), operation=OperationKey("other", "1")))
    with pytest.raises(ValueError):
        ports.ReceiptUpdate(ReceiptState.COMPLETE, result_availability=Availability.AVAILABLE)
    with pytest.raises(ValueError):
        ports.RevisionConflict(0)
    double = InspectionDouble()
    command_services = ports.CommandServices(
        ports.ReadServices(double, double, double), EffectDouble()
    )
    with pytest.raises(TypeError):
        ports.ReadContext(
            "query", PRINCIPAL, cast(ports.ReadServices, cast(object, command_services))
        )


def test_strict_typing_rejects_command_services_and_completion_in_query(tmp_path: Path) -> None:
    fixture = tmp_path / "query_boundary.py"
    fixture.write_text(
        """from craftreport.application.ports import CommandContext, ReadContext, ReadServices
def query(context: ReadContext) -> ReadServices:
    return context.services
def invalid(command: CommandContext) -> None:
    query(command)
    ReadContext(command.operation_id, command.principal, command.services)
def forbidden(query: ReadContext) -> None:
    query.services.effects
    query.journal
    query.registry
""",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyright",
            "--project",
            "pyproject.toml",
            "--outputjson",
            str(fixture),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(completed.stdout)
    fixture.with_suffix(".json").write_text(completed.stdout, encoding="utf-8")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    diagnostics = report["generalDiagnostics"]
    messages = [entry["message"] for entry in diagnostics]
    for text in ("CommandContext", "CommandServices", "effects", "journal", "registry"):
        assert any(text in message for message in messages), messages
    assert all(entry["rule"] != "reportMissingImports" for entry in diagnostics), messages
