"""Exact runtime-owned seam cannot depend on report compiler values."""

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from craftreport.application.ports import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import ExpectedVersion, JsonObject, ResourceRef
from craftreport.contracts.pins import VersionPin
from craftreport.data.requirements import InputRequirements
from craftreport.runtime.values import BindingSpec, BindRequest, TargetIdentity


@pytest.mark.parametrize(
    "value",
    [
        Missing(),
        ServiceUnavailable("bindings"),
        VersionConflict(
            (ExpectedVersion(ResourceRef("binding", "one"), "1"),),
            (ExpectedVersion(ResourceRef("binding", "one"), "2"),),
        ),
    ],
)
def test_failure_result_roundtrip(value: Missing | ServiceUnavailable | VersionConflict) -> None:
    from craftreport.adapters.binding_codecs import BindingResultCodec

    codec = BindingResultCodec()
    wire = codec.encode(value)
    assert codec.decode(wire) == value
    assert wire["kind"] == value.kind
    for mutation in (
        {**wire, "extra": "field"},
        {**wire, "kind": "unknown"},
        {k: v for k, v in wire.items() if k != "kind"},
    ):
        with pytest.raises(ValueError):
            codec.decode(mutation)


@pytest.mark.parametrize(
    "wire",
    [
        {"kind": "missing", "service": "bindings"},
        {"kind": "unavailable"},
        {"kind": "unavailable", "service": 1},
        {"kind": "conflict", "expected": [], "authoritative": []},
        {
            "kind": "version_conflict",
            "expected": [{"resource": {"kind": "binding", "identity": "one"}, "version": 1}],
            "authoritative": [],
        },
    ],
)
def test_malformed_failure_result_rejected(wire: JsonObject) -> None:
    from craftreport.adapters.binding_codecs import BindingResultCodec

    with pytest.raises(ValueError):
        BindingResultCodec().decode(wire)


def test_supported_target_identity() -> None:
    assert TargetIdentity("gridcraft", "browser", "session", "document").document_id == "document"


def binding_spec() -> BindingSpec:
    from craftreport.adapters.binding_codecs import parameter_digest, requirements_digest

    requirements = InputRequirements((), ())
    parameters = (("integer", 2**60), ("decimal", Decimal("2.50")), ("text", "2.50"))
    pin = VersionPin("public/test", "house-blue", "a" * 64)
    return BindingSpec(
        "binding",
        "feed-a",
        requirements,
        requirements_digest(requirements),
        pin,
        pin,
        pin,
        pin,
        parameters,
        parameter_digest(parameters),
        "b" * 64,
        TargetIdentity("gridcraft", "browser", "session", "document"),
    )


def test_exact_wire_and_digest_validation() -> None:
    from craftreport.adapters.binding_codecs import bind_codec

    value = BindRequest(binding_spec(), 0)
    codec = bind_codec()
    raw = codec.encode(value)
    assert raw["expected_generation"] == "0"
    assert codec.decode(raw) == value
    with pytest.raises(ValueError):
        codec.decode({**raw, "expected_generation": 0})
    with pytest.raises(ValueError):
        codec.encode(replace(value, spec=replace(value.spec, parameter_digest="c" * 64)))
    with pytest.raises(FrozenInstanceError):
        value.spec.target.document_id = "other"  # pyright: ignore[reportAttributeAccessIssue]


def test_run_wire_preserves_exact_historical_pins() -> None:
    from craftreport.adapters.binding_codecs import BindingResultCodec
    from craftreport.data.values import SnapshotRef
    from craftreport.runtime.values import RunPins

    spec = binding_spec()
    run = RunPins(
        "run",
        spec.binding_id,
        2,
        SnapshotRef(spec.feed_id, 2**60, "f" * 64),
        spec.definition,
        spec.template,
        spec.theme,
        spec.pack,
        spec.resolved_parameters,
        spec.parameter_digest,
        spec.validation_scope,
        "prepare",
        "result",
        "e" * 64,
        spec.target,
    )
    codec = BindingResultCodec()
    raw = codec.encode(run)
    assert raw["binding_generation"] == "2"
    assert codec.decode(raw) == run
    assert codec.decode(codec.encode(replace(run, prepared_digest="d" * 64))) != run
    for mutation in (
        {"binding_generation": True},
        {"run_id": ""},
        {"prepared_digest": "bad"},
        {"extra": "field"},
    ):
        with pytest.raises(ValueError):
            codec.decode({**raw, **mutation})
