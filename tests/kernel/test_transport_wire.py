"""Canonical output schema and transport adaptation regressions."""

import json
from dataclasses import replace
from typing import cast

import pytest
from pydantic import ValidationError

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.transport_models import InvocationWire
from craftreport.adapters.transport_wire import (
    canonical_status,
    encode_catalog,
    encode_invocation_result,
    envelope_schema,
    invocation_result_schema,
    result_is_error,
)
from craftreport.contracts import (
    Availability,
    CapabilityVersion,
    Catalog,
    Diagnostic,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    ResourceRef,
    StageResult,
    StageState,
)


def test_rejection_has_no_accepted_identity() -> None:
    result = Rejection(
        "correlation",
        Diagnostic(
            OperationKey("fixture.set", "1"),
            "input",
            "invalid_input",
            RecoveryDisposition.CORRECT_REQUEST,
            ("value", 0),
        ),
    )
    assert encode_invocation_result(result) == {
        "correlation_id": "correlation",
        "diagnostic": {
            "operation": {"name": "fixture.set", "contract_version": "1"},
            "stage": "input",
            "code": "invalid_input",
            "recovery": "correct_request",
            "location": ("value", 0),
        },
    }


def receipt(state: ReceiptState) -> Receipt:
    key = OperationKey("fixture.set", "1")
    resource = ResourceRef("fixture", "target")
    pin = ExpectedVersion(resource, "2")
    proof = EvidenceRef("proof", "synthetic", "operation", key, (pin,), "digest")
    return Receipt(
        "operation",
        key,
        "correlation",
        2,
        state,
        (CapabilityVersion("fixture", "1"),),
        (resource,),
        (pin,),
        "input",
        "result",
        (StageResult("readback", StageState.PASSED, "checked", (proof,)),),
        (),
        (proof,),
        "epoch",
        "temporary",
        Availability.AVAILABLE,
        "previous",
    )


@pytest.mark.parametrize("state", list(ReceiptState))
def test_all_receipt_states_and_nested_fields(state: ReceiptState) -> None:
    value = encode_invocation_result(receipt(state))
    parsed = InvocationWire.model_validate_json(canonical_bytes(value), strict=True).root
    assert parsed.model_dump(mode="json") == json.loads(canonical_bytes(value))
    assert value["state"] == state.value
    assert value["previous_operation_id"] == "previous"
    assert canonical_status(receipt(state)) == (
        202 if state in (ReceiptState.ACCEPTED, ReceiptState.PENDING) else 200
    )
    assert result_is_error(receipt(state)) == (
        state in (ReceiptState.FAILED, ReceiptState.PARTIAL, ReceiptState.AMBIGUOUS)
    )
    evidence = cast(tuple[JsonObject, ...], value["evidence"])[0]
    assert evidence["content_digest"] == "digest"
    with pytest.raises(TypeError):
        cast(dict[str, object], evidence)["scope"] = "changed"


@pytest.mark.parametrize(
    "code,status",
    [
        ("access_denied", 404),
        ("unsupported_operation", 404),
        ("receipt_missing", 404),
        ("unauthenticated", 401),
        ("forbidden", 403),
        ("invalid_input", 422),
        ("limit_exceeded", 413),
        ("retry_conflict", 409),
        ("version_conflict", 409),
        ("capacity", 429),
        ("service_unavailable", 503),
        ("unsupported_capability", 503),
        ("future_failure", 503),
    ],
)
def test_rejection_status_and_error_meaning(code: str, status: int) -> None:
    result = Rejection(
        "correlation",
        Diagnostic(OperationKey("fixture.set", "1"), "input", code, RecoveryDisposition.INSPECT),
    )
    assert canonical_status(result) == status
    assert result_is_error(result)


def test_complete_object_schema_and_bound_envelope() -> None:
    schema = invocation_result_schema()
    assert schema["type"] == "object"
    assert len(cast(tuple[object, ...], schema["anyOf"])) == 2
    definitions = cast(dict[str, JsonObject], schema["$defs"])
    assert set(cast(tuple[str, ...], definitions["ReceiptWire"]["required"])) == set(
        encode_invocation_result(receipt(ReceiptState.COMPLETE))
    )
    properties = cast(
        dict[str, JsonObject], envelope_schema(OperationKey("fixture.set", "1"))["properties"]
    )
    assert properties["operation"]["const"] == "fixture.set"
    assert properties["contract_version"]["const"] == "1"
    assert envelope_schema()["additionalProperties"] is False


def test_output_schema_rejects_missing_and_extra_fields() -> None:
    value = encode_invocation_result(receipt(ReceiptState.COMPLETE))

    decoded = json.loads(canonical_bytes(value))
    decoded["credential"] = "secret"
    with pytest.raises(ValidationError):
        InvocationWire.model_validate(decoded, strict=True)
    del decoded["credential"]
    del decoded["evidence"]
    with pytest.raises(ValidationError):
        InvocationWire.model_validate(decoded, strict=True)


def test_catalog_preserves_profile_and_immutable_output() -> None:
    result = encode_catalog(Catalog((), (), "epoch", "temporary"))
    assert result == {
        "operations": (),
        "capabilities": (),
        "deployment_epoch": "epoch",
        "retention_profile": "temporary",
        "core_contract_version": "1.0.0",
    }
    assert canonical_bytes(result)
    assert (
        encode_invocation_result(
            replace(
                receipt(ReceiptState.FAILED),
                result_ref=None,
                result_availability=Availability.MISSING,
            )
        )["result_ref"]
        is None
    )


def test_catalog_keeps_authorized_descriptors_and_verification_metadata() -> None:
    from craftreport.contracts import (
        CapabilityManifest,
        CapabilityRequirement,
        CapabilityView,
        EvidencePolicy,
        OperationDescriptor,
        OperationKind,
        OperationLimits,
        VerificationRecord,
        VerificationState,
    )

    operation = OperationDescriptor(
        OperationKey("fixture.set", "1"),
        OperationKind.COMMAND,
        {"type": "object"},
        {"type": "object"},
        True,
        True,
        ("fixture",),
        (CapabilityRequirement("fixture", ">=1", "synthetic"),),
        ("journal",),
        OperationLimits(100, 5, 200),
        EvidencePolicy(("readback",)),
    )
    manifest = CapabilityManifest(
        "fixture",
        "fixture-package",
        "1.0",
        ">=1",
        (CapabilityVersion("fixture", "1"),),
        (),
        {"type": "object"},
        (operation,),
        "digest",
    )
    record = VerificationRecord(
        "fixture-package",
        "1.0",
        "digest",
        "1.0.0",
        "synthetic-suite",
        (),
        VerificationState.PASSED,
        "synthetic",
        receipt(ReceiptState.COMPLETE).evidence,
    )
    catalog = Catalog(
        (operation,),
        (CapabilityView(manifest, VerificationState.PASSED, record),),
        "epoch",
        "temporary",
    )
    wire = encode_catalog(catalog)
    operations = cast(tuple[JsonObject, ...], wire["operations"])
    assert operations[0]["limits"] == {
        "max_input_bytes": 100,
        "max_nesting_depth": 5,
        "max_output_bytes": 200,
    }
    assert operations[0]["kind"] == "command"
    capabilities = cast(tuple[JsonObject, ...], wire["capabilities"])
    assert capabilities[0]["verification"] == "passed"
    published_record = cast(JsonObject, capabilities[0]["record"])
    assert published_record["scope"] == "synthetic"
    assert published_record["fixture_suite"] == "synthetic-suite"
    assert cast(JsonObject, capabilities[0]["manifest"])["operations"] == operations
