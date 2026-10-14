"""Guard order, privacy and real query state preservation."""

import asyncio
from dataclasses import replace

import pytest
from fixture_dispatch import ALICE, BOB, KEY, DispatchFixture
from test_verification import MANIFEST, RECORD, resolve

from craftreport.application import ports
from craftreport.application.dispatch import Inspection, QueryDispatcher
from craftreport.application.dispatch_ports import WireFailure
from craftreport.application.guards import GuardedCall
from craftreport.application.registry import (
    BoundOperation,
    ImmutableOperationRegistry,
    PreparedCall,
)
from craftreport.contracts import (
    Availability,
    CapabilityManifest,
    CapabilityRequirement,
    CapabilityView,
    EvidencePolicy,
    EvidenceRef,
    EvidenceStatus,
    JsonObject,
    OperationKey,
    OperationLimits,
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
)


def query_dispatch(fixture: DispatchFixture) -> QueryDispatcher:
    return QueryDispatcher(
        fixture.guards, fixture.journal, fixture.reads, fixture.results, fixture.catalog
    )


def test_query_retains_actual_readback_and_preserves_canonical_state() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        before = await fixture.target.read(next(iter(fixture.access.grants[0].resources)))
        result = await query_dispatch(fixture).invoke(ALICE, fixture.request())
        assert isinstance(result, Receipt) and result.state is ReceiptState.COMPLETE
        assert result.result_ref is not None
        retained = await fixture.results.read(ALICE, result.operation_id, result.result_ref)
        assert retained.value == {"value": "retained"}
        assert await fixture.target.read(next(iter(fixture.access.grants[0].resources))) == before
        assert fixture.calls == 1 and fixture.target.effect_count == 0
        assert await fixture.journal.read(result.operation_id) == result
        foreign = await fixture.results.read(BOB, result.operation_id, result.result_ref)
        assert foreign.availability is Availability.INACCESSIBLE and foreign.value is None

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "availability", [Availability.MISSING, Availability.INACCESSIBLE, Availability.UNAVAILABLE]
)
def test_result_retention_failure_never_claims_complete(availability: Availability) -> None:
    fixture = DispatchFixture()
    fixture.results.read_availability = availability
    result = asyncio.run(query_dispatch(fixture).invoke(ALICE, fixture.request()))
    assert isinstance(result, Receipt) and result.state is ReceiptState.FAILED
    assert result.result_availability is availability
    assert any(d.code == f"result_{availability.value}" for d in result.diagnostics)


def test_catalog_and_receipt_inspection_do_not_create_query_records() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        inspection = Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        result = await query_dispatch(fixture).invoke(ALICE, fixture.request())
        assert isinstance(result, Receipt)
        owners = dict(fixture.journal.owners)
        assert (await inspection.catalog(ALICE)).operations == fixture.catalog.operations
        assert (await inspection.catalog(BOB)).operations == ()
        assert await inspection.inspect(ALICE, result.operation_id) == result
        denied = await inspection.inspect(BOB, result.operation_id)
        assert isinstance(denied, Rejection) and denied.diagnostic.code == "access_denied"
        assert fixture.journal.owners == owners and fixture.calls == 1

    asyncio.run(scenario())


def test_authorized_query_is_prepared_without_executing() -> None:
    fixture = DispatchFixture()
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, GuardedCall)
    assert fixture.calls == fixture.target.effect_count == 0


@pytest.mark.parametrize("payload", [{"secret_unknown": "credential"}, {"target": 42}])
def test_coarse_denial_precedes_private_validation(payload: dict[str, str | int]) -> None:
    fixture = DispatchFixture()
    result = asyncio.run(fixture.guards.prepare(BOB, fixture.request(payload=payload)))
    assert isinstance(result, Rejection)
    assert result.diagnostic.code == "access_denied"
    assert result.diagnostic.location == ()
    assert "secret" not in repr(result) and "credential" not in repr(result)
    assert fixture.calls == fixture.target.effect_count == 0
    assert fixture.health.checked == []


def test_authorized_invalid_input_has_safe_location() -> None:
    fixture = DispatchFixture()
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request(payload={"target": 42})))
    assert isinstance(result, Rejection)
    assert result.diagnostic.location == ("target",)
    assert result.correlation_id == "correlation"
    assert fixture.calls == 0


def test_resource_denial_before_health_or_query() -> None:
    fixture = DispatchFixture()
    result = asyncio.run(
        fixture.guards.prepare(ALICE, fixture.request(payload={"target": "foreign"}))
    )
    assert isinstance(result, Rejection) and result.diagnostic.code == "access_denied"
    assert fixture.health.checked == [] and fixture.calls == 0


@pytest.mark.parametrize("service", ["access", "journal", "capabilities", "resources", "results"])
def test_unavailable_required_provider_prevents_behavior(service: str) -> None:
    fixture = DispatchFixture()
    fixture.health.probes[service] = lambda: False
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    assert fixture.calls == fixture.target.effect_count == 0


def test_missing_required_provider_fails_closed() -> None:
    fixture = DispatchFixture()
    del fixture.health.probes["journal"]
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"


def test_exact_version_resolution_never_substitutes() -> None:
    fixture = DispatchFixture()
    unknown = OperationKey(KEY.name, "2")
    fixture.access.operation_scopes[unknown] = "read"
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request(operation=unknown)))
    assert isinstance(result, Rejection) and result.diagnostic.code == "unsupported_operation"
    assert fixture.calls == 0


def test_envelope_limit_is_enforced_after_access() -> None:
    fixture = DispatchFixture(replace(OperationLimits(), max_input_bytes=25))
    result = asyncio.run(fixture.guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, Rejection)
    assert result.diagnostic.location == ("max_input_bytes",)
    assert fixture.calls == 0


def test_unsupported_target_capability_prevents_query() -> None:
    fixture = DispatchFixture()
    descriptor = replace(
        fixture.binding.descriptor,
        required_capabilities=(CapabilityRequirement("unsupported", ">=1", "native"),),
    )
    binding = replace(fixture.binding, descriptor=descriptor)
    guards = replace(fixture.guards, registry=ImmutableOperationRegistry((binding.bind(),)))
    result = asyncio.run(guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "unsupported_capability"
    assert fixture.calls == fixture.target.effect_count == 0


def test_required_evidence_service_and_stage_cannot_be_omitted() -> None:
    fixture = DispatchFixture()
    descriptor = replace(
        fixture.binding.descriptor, completion_evidence=EvidencePolicy(("readback",))
    )
    binding = replace(fixture.binding, descriptor=descriptor)
    guards = replace(fixture.guards, registry=ImmutableOperationRegistry((binding.bind(),)))
    fixture.evidence.available = False
    result = asyncio.run(guards.prepare(ALICE, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    fixture.evidence.available = True
    dispatcher = replace(query_dispatch(fixture), guards=guards)
    observed = asyncio.run(dispatcher.invoke(ALICE, fixture.request()))
    assert isinstance(observed, Receipt) and observed.state is ReceiptState.FAILED
    assert any(d.code == "evidence_missing" for d in observed.diagnostics)


def test_raw_and_structured_codec_errors_cannot_disclose_secrets() -> None:
    fixture = DispatchFixture()
    for failure in (
        ValueError("credential-secret"),
        WireFailure("credential-secret", location=("credential_secret",)),
    ):

        def prepare(payload: JsonObject) -> PreparedCall:
            raise failure

        bound = BoundOperation(fixture.binding.descriptor, prepare)
        guards = replace(fixture.guards, registry=ImmutableOperationRegistry((bound,)))
        result = asyncio.run(guards.prepare(ALICE, fixture.request()))
        assert isinstance(result, Rejection) and result.diagnostic.code == "invalid_input"
        assert result.diagnostic.location == () and "credential" not in repr(result)


def test_invalid_query_result_does_not_manufacture_result_reference() -> None:
    fixture = DispatchFixture(replace(OperationLimits(), max_output_bytes=5))
    result = asyncio.run(query_dispatch(fixture).invoke(ALICE, fixture.request()))
    assert isinstance(result, Receipt) and result.state is ReceiptState.FAILED
    assert result.result_ref is None and fixture.results.values == {}
    assert any(d.code == "result_invalid" for d in result.diagnostics)


def test_catalog_filters_embedded_private_schemas_and_settings() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        hidden = replace(
            fixture.binding.descriptor,
            key=OperationKey("private.read", "1"),
            input_schema={"private_schema": "credential"},
        )
        manifest = CapabilityManifest(
            "fixture",
            "fixture-package",
            "1",
            ">=1",
            (),
            (),
            {"private_settings": "credential"},
            (fixture.binding.descriptor, hidden),
            "digest",
        )
        snapshot = replace(
            fixture.catalog,
            operations=(*fixture.catalog.operations, hidden),
            capabilities=(CapabilityView(manifest),),
        )
        inspection = Inspection(
            snapshot, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        catalog = await inspection.catalog(ALICE)
        assert catalog.operations == fixture.catalog.operations
        assert catalog.capabilities[0].manifest.operations == fixture.catalog.operations
        assert catalog.capabilities[0].manifest.settings_schema == {}
        assert "credential" not in repr(catalog) and "private.read" not in repr(catalog)
        assert (await inspection.catalog(BOB)).capabilities == ()
        assert fixture.journal.owners == {} and fixture.calls == 0

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "availability", [Availability.MISSING, Availability.INACCESSIBLE, Availability.UNAVAILABLE]
)
def test_inspection_reports_lost_retained_result(availability: Availability) -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        receipt = await query_dispatch(fixture).invoke(ALICE, fixture.request())
        assert isinstance(receipt, Receipt)
        fixture.results.read_availability = availability
        inspection = Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        result = await inspection.inspect(ALICE, receipt.operation_id)
        assert (
            isinstance(result, Rejection)
            and result.diagnostic.code == f"result_{availability.value}"
        )
        assert await fixture.journal.read(receipt.operation_id) == receipt

    asyncio.run(scenario())


def test_receipt_denial_precedes_journal_read() -> None:
    class JournalBomb:
        async def read(self, operation_id: str) -> ports.ReceiptRead:
            raise AssertionError("foreign journal read")

    async def scenario() -> None:
        fixture = DispatchFixture()
        receipt = await query_dispatch(fixture).invoke(ALICE, fixture.request())
        assert isinstance(receipt, Receipt)
        # The authorized facade provider read must never run for a foreign identity.
        original_read = fixture.journal.read
        fixture.journal.read = JournalBomb().read
        inspection = Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        result = await inspection.inspect(BOB, receipt.operation_id)
        fixture.journal.read = original_read
        assert isinstance(result, Rejection) and result.diagnostic.code == "access_denied"

    asyncio.run(scenario())


def test_unauthorized_input_never_reaches_private_preparation() -> None:
    fixture = DispatchFixture()
    calls: list[str] = []

    def prepare(payload: JsonObject) -> PreparedCall:
        calls.append("private validation")
        raise ValueError("secret")

    bound = BoundOperation(fixture.binding.descriptor, prepare)
    guards = replace(fixture.guards, registry=ImmutableOperationRegistry((bound,)))
    result = asyncio.run(guards.prepare(BOB, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "access_denied"
    assert calls == []


def test_raw_health_failure_is_safe_and_blocks_query() -> None:
    fixture = DispatchFixture()

    def probe() -> bool:
        raise RuntimeError("credential-secret")

    fixture.health.probes["journal"] = probe
    result = asyncio.run(query_dispatch(fixture).invoke(ALICE, fixture.request()))
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    assert "credential" not in repr(result) and fixture.calls == 0


def test_query_result_readback_must_match_retained_content() -> None:
    fixture = DispatchFixture()
    original_write = fixture.results.write

    async def corrupt(principal: Principal, operation_id: str, value: JsonObject) -> str:
        return await original_write(principal, operation_id, {"value": "wrong"})

    fixture.results.write = corrupt
    result = asyncio.run(query_dispatch(fixture).invoke(ALICE, fixture.request()))
    assert isinstance(result, Receipt) and result.state is ReceiptState.FAILED
    assert result.result_availability is Availability.UNAVAILABLE


@pytest.mark.parametrize(
    "availability", [Availability.MISSING, Availability.INACCESSIBLE, Availability.UNAVAILABLE]
)
def test_inspection_reports_evidence_loss_without_changing_record(
    availability: Availability,
) -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        ref = EvidenceRef("readback", "synthetic", "evidence-query", KEY)
        receipt = await fixture.journal.record_query(
            ports.QueryObservation(
                "evidence-query",
                ALICE,
                KEY,
                "correlation",
                (),
                (),
                (),
                ports.ReceiptUpdate(ReceiptState.FAILED, evidence=(ref,)),
            )
        )
        fixture.evidence.retain(EvidenceStatus(ref, availability))
        inspection = Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        result = await inspection.inspect(ALICE, receipt.operation_id)
        assert (
            isinstance(result, Rejection)
            and result.diagnostic.code == f"evidence_{availability.value}"
        )
        assert await fixture.journal.read(receipt.operation_id) == receipt

    asyncio.run(scenario())


def test_advertised_result_limit_cannot_be_bypassed_by_codec_configuration() -> None:
    fixture = DispatchFixture()
    descriptor = replace(fixture.binding.descriptor, limits=OperationLimits(max_output_bytes=5))
    binding = replace(fixture.binding, descriptor=descriptor)
    guards = replace(fixture.guards, registry=ImmutableOperationRegistry((binding.bind(),)))
    result = asyncio.run(
        replace(query_dispatch(fixture), guards=guards).invoke(ALICE, fixture.request())
    )
    assert isinstance(result, Receipt) and result.state is ReceiptState.FAILED
    assert fixture.results.values == {} and any(
        d.code == "result_invalid" for d in result.diagnostics
    )


def test_inspection_with_no_result_or_evidence_does_not_require_those_providers() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        receipt = await fixture.journal.record_query(
            ports.QueryObservation(
                "pending",
                ALICE,
                KEY,
                "correlation",
                (),
                (),
                (),
                ports.ReceiptUpdate(ReceiptState.PENDING),
            )
        )
        fixture.evidence.available = fixture.results.available = False
        inspection = Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        assert await inspection.inspect(ALICE, receipt.operation_id) == receipt

    asyncio.run(scenario())


def test_catalog_keeps_verified_identity_without_disclosing_foreign_evidence() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        manifest = replace(MANIFEST, operations=fixture.catalog.operations)
        verified = resolve(RECORD, manifest)
        catalog = replace(fixture.catalog, capabilities=(verified,))
        inspection = Inspection(
            catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        )
        filtered = (await inspection.catalog(ALICE)).capabilities[0]
        assert filtered.verification is verified.verification
        assert filtered.record == replace(RECORD, evidence=())
        assert filtered.manifest.implementation_digest == manifest.implementation_digest

    asyncio.run(scenario())
