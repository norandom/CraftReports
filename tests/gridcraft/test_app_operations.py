"""Strict app operation registration, preparation-scope validation, and caller tests."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import pytest
from craftreport_gridcraft.app_values import (
    AppSettings,
    BrowserTarget,
)
from craftreport_gridcraft.browser import BrowserDriver
from craftreport_gridcraft.capability import gridcraft_factory
from craftreport_gridcraft.codecs import (
    observation_fact_codec,
)
from craftreport_gridcraft.facts import AppFacts
from craftreport_gridcraft.integration import (
    AppRunPreparer,
    GridCraftOperationCaller,
)
from craftreport_gridcraft.operations import (
    AppOperations,
    app_descriptors,
    app_diagnostic_policy,
)
from craftreport_gridcraft.values import (
    PROFILE,
    AppInspectRequest,
    AppIssue,
    ApplyRequest,
    AppObservationFact,
    CurrentObservationPointer,
    DiscoverRequest,
    OpenReportRequest,
    TargetRecovery,
    VerifyRequest,
)

from craftreport.adapters.binding_codecs import parameter_digest, requirements_digest
from craftreport.adapters.report_codecs import (
    prepared_codec,
    quality_codec,
    validation_scope_identifier,
)
from craftreport.application.ports import (
    CommandContext,
    CommandServices,
    GuardLease,
    ReadContext,
    ReadServices,
)
from craftreport.application.service_values import (
    GuardCurrent,
    GuardLost,
    Missing,
    ServiceUnavailable,
)
from craftreport.contracts import (
    Availability,
    CapabilityManifest,
    Diagnostic,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    InvocationEnvelope,
    InvocationResult,
    JsonObject,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    ResourceRef,
    ResultReadback,
    StageResult,
    StageState,
)
from craftreport.data.requirements import InputRequirements
from craftreport.policies.values import (
    QualityEvaluation,
)
from craftreport.reporting.ports import PreparationResult, ReportFailure
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import (
    BindingSpec,
    EffectObservation,
    PreparationIssue,
    PreparedRunInputs,
    RunPins,
    TargetIdentity,
)


class DummyLease:
    authoritative_versions = ()

    async def assert_current(self) -> GuardCurrent | GuardLost:
        return GuardCurrent()


class DummyFacade:
    def __init__(
        self,
        receipt: Receipt | None = None,
        readback: ResultReadback | None = None,
    ) -> None:
        self._receipt = receipt
        self._readback = readback
        self.invocations: list[tuple[Principal, OperationKey, JsonObject, str | None]] = []

    async def invoke(
        self,
        principal: Principal,
        request: InvocationEnvelope,
    ) -> InvocationResult:
        self.invocations.append((principal, request.operation, request.payload, request.retry_key))
        if self._receipt is not None:
            return self._receipt
        return Rejection(
            "invoke",
            Diagnostic(request.operation, "invoke", "missing", RecoveryDisposition.RETRY),
        )

    async def inspect(self, principal: Principal, operation_id: str) -> Receipt | Rejection:
        if self._receipt is not None:
            return self._receipt
        return Rejection(
            "inspect",
            Diagnostic(
                OperationKey("reports.prepare", "1"),
                "receipt",
                "missing",
                RecoveryDisposition.INSPECT,
            ),
        )

    async def read_result(
        self, principal: Principal, operation_id: str
    ) -> ResultReadback | Rejection:
        if self._readback is not None:
            return self._readback
        return Rejection(
            "read_result",
            Diagnostic(
                OperationKey("reports.prepare", "1"),
                "read_result",
                "missing",
                RecoveryDisposition.INSPECT,
            ),
        )


def _make_receipt(
    op_id: str,
    key: OperationKey,
    result_ref: str | None = None,
    prepared_digest: str = "",
    pack_identity: str = "",
    pack_version: str = "",
    feed_id: str = "",
    producer_version: str = "",
    snapshot_digest: str = "",
    state: ReceiptState = ReceiptState.COMPLETE,
    result_avail: Availability = Availability.AVAILABLE,
) -> Receipt:
    pack_id = f"{pack_identity}@{pack_version}" if pack_identity else ""
    expected_resources = (
        (
            ResourceRef("report_pack_source", pack_id),
            ResourceRef("report_pack_artifact_scope", pack_id),
            ResourceRef("snapshot", f"{feed_id}:{producer_version}"),
        )
        if pack_id
        else ()
    )
    ev = (
        EvidenceRef(
            "ev-prep",
            "prep",
            op_id,
            key,
            (
                ExpectedVersion(
                    ResourceRef("snapshot", f"{feed_id}:{producer_version}"), snapshot_digest
                ),
                ExpectedVersion(ResourceRef("report_pack_source", pack_id), "source-1"),
                ExpectedVersion(ResourceRef("report_pack_artifact_scope", pack_id), "scope-1"),
            )
            if pack_id
            else (),
            prepared_digest,
        )
        if prepared_digest
        else None
    )
    stages = (
        (StageResult("prepared", StageState.PASSED, "prepared", (ev,) if ev else ()),) if ev else ()
    )
    return Receipt(
        op_id,
        key,
        "corr-1",
        1,
        state,
        (),
        expected_resources,
        (),
        "input-1",
        result_ref,
        stages,
        (),
        (ev,) if ev else (),
        "epoch-1",
        "retention-1",
        result_avail,
    )


@pytest.fixture
def principal() -> Principal:
    return Principal("deployment-1", "user-1", frozenset({"inspect", "change"}))


@pytest.fixture
def cmd_context(principal: Principal) -> CommandContext:
    class DummyEv:
        async def inspect(self, refs: Any) -> Any:
            return ()

    class DummyRes:
        async def read(self, r: Any) -> Any:
            return Missing()

    class DummyCap:
        async def check(self, req: Any, res: Any) -> Any:
            return None

    class DummyEff:
        async def apply(self, res: Any, chg: Any, g: Any) -> Any:
            return None

    reads = ReadServices(cast(Any, DummyEv()), cast(Any, DummyCap()), cast(Any, DummyRes()))
    services = CommandServices(reads, cast(Any, DummyEff()))
    return CommandContext("op-123", principal, cast(GuardLease, DummyLease()), services)


@pytest.fixture
def read_context(principal: Principal) -> ReadContext:
    class DummyEv:
        async def inspect(self, refs: Any) -> Any:
            return ()

    class DummyRes:
        async def read(self, r: Any) -> Any:
            return Missing()

    class DummyCap:
        async def check(self, req: Any, res: Any) -> Any:
            return None

    reads = ReadServices(cast(Any, DummyEv()), cast(Any, DummyCap()), cast(Any, DummyRes()))
    return ReadContext("op-read-123", principal, reads)


@pytest.fixture
def settings(browser_target: BrowserTarget) -> AppSettings:
    return AppSettings(
        origin=browser_target.origin,
        deployment_id=browser_target.deployment_id,
        context_id=browser_target.context_id,
        principal_id="principal-1",
        artifact_root="D:/artifacts",
        destination_ids=("dest-1",),
        archive_digest=browser_target.archive_digest,
        javascript_digest=browser_target.javascript_digest,
        wasm_digest=browser_target.wasm_digest,
        profile_pin=browser_target.profile_pin,
    )


@pytest.fixture
def facts(tmp_path: Path) -> AppFacts:
    return AppFacts(tmp_path)


@pytest.fixture
def decode_prep(prepared: PreparedReport, quality: QualityEvaluation) -> Any:
    def _decoder(val: JsonObject) -> PreparationResult | ReportFailure:
        return PreparationResult(prepared, quality)

    return _decoder


def test_discover_operation(
    settings: AppSettings,
    browser_target: BrowserTarget,
    facts: AppFacts,
    read_context: ReadContext,
) -> None:
    driver = BrowserDriver(settings)
    facade = DummyFacade()
    ops = AppOperations(settings, driver, facts, cast(Any, facade), lambda _: cast(Any, None))
    discovered = asyncio.run(ops.discover(DiscoverRequest(), read_context))

    assert discovered["schema_version"] == "1"
    assert discovered["deployment_id"] == settings.deployment_id
    assert discovered["context_id"] == settings.context_id
    assert discovered["origin"] == settings.origin
    assert discovered["profile_pin"] == asdict(PROFILE.pin)

    op_map = cast(dict[str, str], discovered["operations"])
    assert op_map["gridcraft.discover"] == "supported"
    assert op_map["gridcraft.open_report"] == "supported"
    assert op_map["gridcraft.apply"] == "supported"
    assert op_map["gridcraft.verify"] == "supported"
    assert op_map["gridcraft.inspect"] == "supported"
    assert op_map["gridcraft.export"] == "unavailable"


def test_inspect_recovery_status(
    settings: AppSettings,
    facts: AppFacts,
    read_context: ReadContext,
) -> None:
    driver = BrowserDriver(settings)
    facade = DummyFacade()
    ops = AppOperations(settings, driver, facts, cast(Any, facade), lambda _: cast(Any, None))
    recovery = asyncio.run(ops.inspect(AppInspectRequest("doc-inspect-1"), read_context))
    assert isinstance(recovery, TargetRecovery)
    assert recovery.document_id == "doc-inspect-1"
    assert recovery.status == "missing"
    assert recovery.recovery_required is False


def test_open_report_validations_and_failures(
    settings: AppSettings,
    browser_target: BrowserTarget,
    run: RunPins,
    facts: AppFacts,
    prepared: PreparedReport,
    quality: QualityEvaluation,
    cmd_context: CommandContext,
    decode_prep: Any,
) -> None:
    driver = BrowserDriver(settings)
    # 1. Preparation receipt missing
    facade_missing = DummyFacade(receipt=None)
    ops = AppOperations(settings, driver, facts, cast(Any, facade_missing), decode_prep)
    res1 = asyncio.run(ops.open_report(OpenReportRequest(run, browser_target), cmd_context))
    assert isinstance(res1.result, AppIssue)
    assert res1.result.code == "conflict"
    assert res1.result.location == ("preparation", "receipt")

    # 2. Preparation receipt valid, but browser page is None
    receipt = _make_receipt(
        run.prepared_operation_id,
        OperationKey("reports.prepare", "1"),
        run.prepared_result_ref,
        run.prepared_digest,
        run.pack.identity,
        run.pack.version,
        run.snapshot.feed_id,
        str(run.snapshot.producer_version),
        run.snapshot.content_digest,
    )
    res_val: JsonObject = {
        "prepared": prepared_codec().encode(prepared),
        "quality": quality_codec().encode(quality),
    }
    readback = ResultReadback(receipt, res_val)
    facade_valid = DummyFacade(receipt=receipt, readback=readback)
    ops_nopage = AppOperations(settings, driver, facts, cast(Any, facade_valid), decode_prep)
    res2 = asyncio.run(ops_nopage.open_report(OpenReportRequest(run, browser_target), cmd_context))
    assert isinstance(res2.result, AppIssue)
    assert res2.result.code == "unavailable"
    assert res2.result.location == ("browser",)

    # 3. Document already exists in index -> conflict
    facts.update_current_index(
        CurrentObservationPointer(
            browser_target.identity.document_id,
            "prior-op",
            browser_target,
            run,
            1,
            "complete",
            "a" * 64,
        )
    )
    res3 = asyncio.run(ops_nopage.open_report(OpenReportRequest(run, browser_target), cmd_context))
    assert isinstance(res3.result, AppIssue)
    assert res3.result.code == "conflict"
    assert res3.result.location == ("document",)


def test_apply_and_verify_validations(
    settings: AppSettings,
    browser_target: BrowserTarget,
    run: RunPins,
    facts: AppFacts,
    cmd_context: CommandContext,
    decode_prep: Any,
) -> None:
    driver = BrowserDriver(settings)
    facade = DummyFacade()
    ops = AppOperations(settings, driver, facts, cast(Any, facade), decode_prep)

    # 1. Apply without current document pointer -> conflict
    res1 = asyncio.run(ops.apply(ApplyRequest(run, 1), cmd_context))
    assert isinstance(res1.result, AppIssue)
    assert res1.result.code == "conflict"
    assert res1.result.location == ("revision",)

    # 2. Verify without current document pointer -> conflict
    res2 = asyncio.run(ops.verify(VerifyRequest(run, 1), cmd_context))
    assert isinstance(res2.result, AppIssue)
    assert res2.result.code == "conflict"
    assert res2.result.location == ("revision",)


def test_app_run_preparer(
    prepared: PreparedReport,
    quality: QualityEvaluation,
    principal: Principal,
    decode_prep: Any,
) -> None:
    reqs = InputRequirements((), ())
    binding = BindingSpec(
        "b-1",
        prepared.snapshot.feed_id,
        reqs,
        requirements_digest(reqs),
        prepared.definition,
        prepared.template,
        prepared.theme,
        prepared.pack.version_pin,
        prepared.resolved_parameters,
        parameter_digest(prepared.resolved_parameters),
        validation_scope_identifier(prepared.release_policy),
        TargetIdentity("gridcraft", "browser", "context", "document"),
    )
    snapshot = prepared.snapshot

    # Case 1: Facade unavailable
    facade_fail = DummyFacade(receipt=None)
    preparer_fail = AppRunPreparer(cast(Any, facade_fail), principal, decode_prep)
    res_unavail = asyncio.run(preparer_fail.prepare(binding, snapshot))
    assert isinstance(res_unavail, ServiceUnavailable)
    assert res_unavail.service == "reports.prepare"

    # Case 2: Incomplete receipt
    bad_receipt = _make_receipt(
        "prep-op-1",
        OperationKey("reports.prepare", "1"),
        "ref-1",
        state=ReceiptState.PENDING,
        result_avail=Availability.MISSING,
    )
    facade_bad = DummyFacade(receipt=bad_receipt)
    preparer_bad = AppRunPreparer(cast(Any, facade_bad), principal, decode_prep)
    res_bad = asyncio.run(preparer_bad.prepare(binding, snapshot))
    assert isinstance(res_bad, PreparationIssue)
    assert res_bad.code == "preparation_unavailable"

    # Case 3: Complete and valid
    receipt = _make_receipt(
        "prep-op-1",
        OperationKey("reports.prepare", "1"),
        "result-ref-1",
        prepared.content_digest,
        prepared.pack.version_pin.identity,
        prepared.pack.version_pin.version,
        snapshot.feed_id,
        str(snapshot.producer_version),
        snapshot.content_digest,
    )
    readback = ResultReadback(receipt, {})
    facade_ok = DummyFacade(receipt=receipt, readback=readback)
    preparer_ok = AppRunPreparer(cast(Any, facade_ok), principal, decode_prep)
    res_ok = asyncio.run(preparer_ok.prepare(binding, snapshot))
    assert isinstance(res_ok, PreparedRunInputs)
    assert res_ok.prepared_operation_id == "prep-op-1"
    assert res_ok.prepared_result_ref == "result-ref-1"
    assert res_ok.prepared_digest == prepared.content_digest


def test_gridcraft_operation_caller(
    principal: Principal,
    facts: AppFacts,
    run: RunPins,
    browser_target: BrowserTarget,
) -> None:
    receipt = _make_receipt(
        "apply-op-1",
        OperationKey("gridcraft.apply", "1"),
        "ref-1",
    )
    obs_fact = AppObservationFact(
        "apply-op-1",
        "gridcraft.apply",
        browser_target.deployment_id,
        browser_target,
        run,
        2,
        "complete",
    )
    readback = ResultReadback(receipt, observation_fact_codec().encode(obs_fact))
    facade = DummyFacade(receipt=receipt, readback=readback)

    caller = GridCraftOperationCaller(cast(Any, facade), principal, facts)
    op_id = asyncio.run(caller.start(run))
    assert op_id == "apply-op-1"

    eff_obs = asyncio.run(caller.inspect("apply-op-1"))
    assert isinstance(eff_obs, EffectObservation)
    assert eff_obs.run_id == run.run_id
    assert eff_obs.effect is EffectDisposition.APPLIED
    assert eff_obs.verified_complete is True


def test_gridcraft_factory_and_descriptors(
    settings: AppSettings, facts: AppFacts, monkeypatch: pytest.MonkeyPatch
) -> None:
    def mock_dist(_pkg: str) -> object:
        return type("D", (), {"version": "0.7.0"})()

    monkeypatch.setattr("craftreport_gridcraft.capability.distribution", mock_dist)
    factory = gridcraft_factory()
    manifest = factory.describe()
    assert isinstance(manifest, CapabilityManifest)
    assert manifest.identity == "gridcraft.web_reports"
    assert manifest.package == "craftreport-gridcraft"

    descriptors = app_descriptors()
    keys = {d.key.name for d in descriptors}
    assert keys == {
        "gridcraft.discover",
        "gridcraft.open_report",
        "gridcraft.apply",
        "gridcraft.verify",
        "gridcraft.inspect",
    }

    # Verify diagnostic policy
    policy = app_diagnostic_policy()
    assert ("bootstrap", "unavailable", RecoveryDisposition.RETRY) in policy.allowed
    assert ("admit", "conflict", RecoveryDisposition.CORRECT_REQUEST) in policy.allowed
