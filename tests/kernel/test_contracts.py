"""Behavioral fixtures for the immutable, framework-free kernel boundary."""

from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import cast

import pytest

from craftreport.contracts.capabilities import (
    CORE_CONTRACT_VERSION,
    CapabilityManifest,
    CapabilityView,
    VerificationRecord,
    VerificationState,
)
from craftreport.contracts.identity import (
    CapabilityRequirement,
    CapabilityVersion,
    ExpectedVersion,
    OperationKey,
    Principal,
    ResourceRef,
    RetryKey,
)
from craftreport.contracts.operations import (
    CommandIntent,
    EvidencePolicy,
    InvocationEnvelope,
    OperationDescriptor,
    OperationKind,
    OperationLimits,
)
from craftreport.contracts.outcomes import (
    Availability,
    Diagnostic,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    OutcomeProposal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    StageResult,
    StageState,
)
from craftreport.contracts.values import JsonObject, JsonValue, freeze_object

KEY = OperationKey("fixture.set", "1")
RESOURCE = ResourceRef("fixture", "target-a")
PIN = ExpectedVersion(RESOURCE, "3")


def descriptor(kind: OperationKind = OperationKind.COMMAND) -> OperationDescriptor:
    return OperationDescriptor(
        key=KEY,
        kind=kind,
        input_schema={"type": "object"},
        result_schema={"type": "object"},
        starts_business_work=kind is OperationKind.COMMAND,
        changes_business_state=kind is OperationKind.COMMAND,
        resources=("fixture",),
        required_capabilities=(CapabilityRequirement("fixture", ">=1"),),
        required_services=("evidence",),
        limits=OperationLimits(),
        completion_evidence=EvidencePolicy(("target-readback",)),
    )


def evidence() -> EvidenceRef:
    return EvidenceRef("evidence-1", "synthetic", "op-1", KEY, (PIN,), "sha256:abc")


def receipt(state: ReceiptState = ReceiptState.ACCEPTED) -> Receipt:
    return Receipt(
        operation_id="op-1",
        operation=KEY,
        correlation_id="request-1",
        revision=1,
        state=state,
        capability_versions=(CapabilityVersion("fixture", "1.2.0"),),
        resources=(RESOURCE,),
        expected_versions=(PIN,),
        input_ref="input-1",
        result_ref=None,
        stages=(),
        diagnostics=(),
        evidence=(),
        deployment_epoch="epoch-1",
        retention_profile="temporary-no-eviction",
    )


def test_principal_keeps_server_scope_immutable() -> None:
    principal = Principal("deployment-a", "subject-a", frozenset({"inspect"}))
    assert principal.deployment_scope == "deployment-a"
    assert principal.subject == "subject-a"
    assert principal.permitted_scopes == frozenset({"inspect"})
    with pytest.raises(FrozenInstanceError):
        setattr(principal, "subject", "subject-b")


@pytest.mark.parametrize("name", ["", "Fixture.set", "a/b", "x" * 49, "a\n"])
def test_invalid_operation_names_are_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        OperationKey(name, "1")


@pytest.mark.parametrize("version", ["", "0", "-1", "01", "1.0", "1\n"])
def test_contract_versions_are_positive_integer_strings(version: str) -> None:
    with pytest.raises(ValueError):
        OperationKey("fixture.set", version)


def test_nested_payload_and_schemas_are_owned_immutable_snapshots() -> None:
    values: list[JsonValue] = ["original", {"nested": True}]
    source: JsonObject = {"values": values}
    envelope = InvocationEnvelope(KEY, source, "request-1", "retry-1", (PIN,))
    values.append("changed")
    cast(dict[str, JsonValue], values[1])["nested"] = False
    assert envelope.payload["values"] == ("original", {"nested": True})
    with pytest.raises(TypeError):
        cast(dict[str, JsonValue], envelope.payload)["added"] = "changed"
    schema: dict[str, JsonValue] = {"required": ["value"]}
    declared = replace(descriptor(), input_schema=schema)
    schema["required"] = []
    assert declared.input_schema["required"] == ("value",)


def test_live_handles_cannot_enter_json_values() -> None:
    with pytest.raises(TypeError):
        InvocationEnvelope(KEY, {"handle": cast(JsonValue, object())}, "request-1")


def test_collections_are_detached_from_mutable_constructor_inputs() -> None:
    scopes = {"inspect"}
    principal = Principal("deployment-a", "subject-a", cast(frozenset[str], scopes))
    scopes.add("mutate")
    assert principal.permitted_scopes == frozenset({"inspect"})
    requirements = [CapabilityRequirement("fixture", ">=1")]
    declared = replace(
        descriptor(), required_capabilities=cast(tuple[CapabilityRequirement, ...], requirements)
    )
    requirements.clear()
    assert len(declared.required_capabilities) == 1


def test_query_cannot_declare_work_or_state_change() -> None:
    query = descriptor(OperationKind.QUERY)
    assert query.kind is OperationKind.QUERY
    for field in ("starts_business_work", "changes_business_state"):
        with pytest.raises(ValueError):
            replace(query, **{field: True})


def test_duplicate_resource_preconditions_are_rejected() -> None:
    with pytest.raises(ValueError):
        InvocationEnvelope(KEY, {}, "request-1", "retry-1", (PIN, PIN))


@pytest.mark.parametrize("limit", [0, -1, True])
def test_limits_require_positive_integers(limit: int) -> None:
    with pytest.raises(ValueError):
        OperationLimits(max_input_bytes=limit)


def test_rejection_has_correlation_and_diagnostic_but_no_accepted_identity() -> None:
    diagnostic = Diagnostic(KEY, "access", "forbidden", RecoveryDisposition.DO_NOT_RETRY)
    rejected = Rejection("request-1", diagnostic)
    assert rejected.correlation_id == "request-1"
    assert rejected.diagnostic.code == "forbidden"
    assert not hasattr(rejected, "operation_id")
    assert not hasattr(rejected, "state")


@pytest.mark.parametrize("state", tuple(ReceiptState))
def test_every_accepted_state_retains_versions_and_references(state: ReceiptState) -> None:
    value = replace(receipt(state), evidence=(evidence(),))
    assert value.state is state
    assert value.evidence[0].resource_versions == (PIN,)
    assert value.operation == KEY
    assert value.capability_versions[0].version == "1.2.0"
    assert value.deployment_epoch == "epoch-1"


def test_accepted_identity_and_revision_must_exist() -> None:
    with pytest.raises(ValueError):
        replace(receipt(), operation_id="")
    with pytest.raises(ValueError):
        replace(receipt(), revision=0)


@pytest.mark.parametrize("state", tuple(StageState))
def test_stages_never_infer_success(state: StageState) -> None:
    stage = StageResult("readback", state, "observed", (evidence(),))
    assert stage.state is state


@pytest.mark.parametrize("availability", tuple(Availability))
def test_evidence_availability_is_distinct_from_verification(availability: Availability) -> None:
    status = EvidenceStatus(evidence(), availability)
    assert status.availability is availability
    assert status.verification is StageState.PENDING
    if availability is not Availability.AVAILABLE:
        with pytest.raises(ValueError):
            EvidenceStatus(evidence(), availability, StageState.PASSED)


@pytest.mark.parametrize("identity", ["/tmp/evidence", "C:\\private\\secret", "../private"])
def test_evidence_identity_is_opaque_not_a_filesystem_path(identity: str) -> None:
    with pytest.raises(ValueError):
        replace(evidence(), identity=identity)


def test_safe_diagnostics_have_only_structured_fields() -> None:
    diagnostic = Diagnostic(KEY, "result", "result_contract", RecoveryDisposition.RECONCILE)
    assert diagnostic.operation == KEY
    assert not hasattr(diagnostic, "message")
    with pytest.raises(ValueError):
        replace(diagnostic, code="password=secret\nraw exception")
    with pytest.raises(ValueError):
        replace(diagnostic, stage="/private/path")


@pytest.mark.parametrize("effect", tuple(EffectDisposition))
def test_proposals_record_effect_without_claiming_canonical_completion(
    effect: EffectDisposition,
) -> None:
    proposal = OutcomeProposal(result="typed-result", effect=effect, stages=(), evidence=())
    assert proposal.result == "typed-result"
    assert proposal.effect is effect
    assert not hasattr(proposal, "state")


def test_capability_manifest_retains_versions_without_claiming_verification() -> None:
    manifest = CapabilityManifest(
        identity="fixture",
        package="craftreport-fixture",
        version="1.2.0",
        core_contract_range=">=1,<2",
        provided=(CapabilityVersion("fixture", "1.2.0"),),
        required=(),
        settings_schema={"type": "object"},
        operations=(descriptor(),),
        implementation_digest="sha256:abc",
    )
    view = CapabilityView(manifest)
    assert CORE_CONTRACT_VERSION == "1.0.0"
    assert view.verification is VerificationState.PENDING
    assert view.record is None
    with pytest.raises(ValueError):
        replace(view, verification=VerificationState.PASSED)
    record = VerificationRecord(
        package=manifest.package,
        package_version=manifest.version,
        implementation_digest=manifest.implementation_digest,
        core_contract_version=CORE_CONTRACT_VERSION,
        fixture_suite="kernel-suite-v1",
        dependency_versions=manifest.provided,
        state=VerificationState.FAILED,
        scope="synthetic-in-process",
        evidence=(evidence(),),
    )
    assert replace(view, verification=VerificationState.FAILED, record=record).record == record
    with pytest.raises(ValueError):
        replace(view, verification=VerificationState.PASSED, record=record)
    passed = replace(record, state=VerificationState.PASSED)
    assert replace(view, verification=VerificationState.PASSED, record=passed).record == passed


@dataclass(frozen=True)
class DeclaredResult:
    quantity: Decimal
    on_date: date


def test_generic_result_retains_declared_immutable_types_without_coercion() -> None:
    result = DeclaredResult(Decimal("1.2300"), date(2026, 10, 13))
    proposal = OutcomeProposal(result, EffectDisposition.APPLIED, (), ())
    assert proposal.result is result
    assert proposal.result is not None
    assert proposal.result.quantity.as_tuple().exponent == -4


def test_generic_result_rejects_nested_mutability() -> None:
    @dataclass(frozen=True)
    class MutableResult:
        values: list[str]

    with pytest.raises(TypeError):
        OutcomeProposal(MutableResult(["mutable"]), EffectDisposition.NONE, (), ())


def test_result_owns_json_snapshot_but_rejects_views_of_mutable_backing_maps() -> None:
    source: dict[str, JsonValue] = {"value": [1]}
    with pytest.raises(TypeError):
        OutcomeProposal(MappingProxyType(source), EffectDisposition.NONE, (), ())
    result = freeze_object(source)
    proposal = OutcomeProposal(result, EffectDisposition.NONE, (), ())
    source["value"] = "changed"
    assert proposal.result == {"value": (1,)}


def test_retry_identity_is_partitioned_by_principal_scope_and_exact_operation() -> None:
    key = RetryKey("deployment-a", "subject-a", KEY, "retry-1")
    assert key != replace(key, subject="subject-b")
    assert key != replace(key, deployment_scope="deployment-b")
    assert key != replace(key, operation=OperationKey(KEY.name, "2"))


def test_command_intent_preserves_metadata_and_rejects_unrelated_preconditions() -> None:
    key = RetryKey("deployment-a", "subject-a", KEY, "retry-1")
    intent = CommandIntent(
        key,
        "sha256:normalized-content",
        "v1",
        "request-1",
        (CapabilityVersion("fixture", "1.2.0"),),
        (RESOURCE,),
        (PIN,),
    )
    assert intent.retry_key.operation == KEY
    assert intent.normalization_policy == "v1"
    assert intent.expected_versions == (PIN,)
    with pytest.raises(ValueError):
        replace(intent, resources=())
