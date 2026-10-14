"""Shared strict conversion and registry effect preservation cases."""

import asyncio
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from pydantic import Field, field_serializer
from test_registry import EVIDENCE, KEY, RESOURCE, STAGE, contexts, descriptor

from craftreport.adapters.canonical import WireFailure, canonical_bytes, fingerprint
from craftreport.adapters.validation import PydanticCodec, StrictWireModel, decode_envelope
from craftreport.application.ports import CommandContext
from craftreport.application.registry import CommandBehavior, OperationBinding, PreparedCommand
from craftreport.contracts import EffectDisposition, JsonObject, OperationLimits, OutcomeProposal
from craftreport.contracts.values import JsonValue, freeze_object


@dataclass(frozen=True)
class Request:
    amount: Decimal
    count: int
    day: date
    items: tuple[int, ...]


class RequestWire(StrictWireModel):
    amount: str = Field(default="0", pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")
    count: int = 2
    day: str = "2026-10-14"
    items: list[int] = Field(default_factory=list[int])


def from_wire(value: RequestWire) -> Request:
    return Request(
        Decimal(value.amount), value.count, date.fromisoformat(value.day), tuple(value.items)
    )


def to_wire(value: Request) -> JsonObject:
    return {
        "amount": format(value.amount.normalize(), "f"),
        "count": value.count,
        "day": value.day.isoformat(),
        "items": list(value.items),
    }


def codec(limits: OperationLimits = OperationLimits()) -> PydanticCodec[Request, RequestWire]:
    return PydanticCodec(RequestWire, from_wire, to_wire, limits)


def envelope(payload: JsonObject | None = None) -> JsonObject:
    return {
        "operation": "fixture.set",
        "contract_version": "1",
        "payload": payload or {},
        "correlation_id": "request-a",
        "retry_key": "retry-a",
    }


def test_defaults_ordinary_domain_values_and_equivalent_normalization() -> None:
    conversion = codec()
    first = conversion.decode({"amount": "1.00"})
    second = conversion.decode({"items": [], "day": "2026-10-14", "count": 2, "amount": "1"})
    assert first == second == Request(Decimal("1"), 2, date(2026, 10, 14), ())
    assert conversion.encode(first) == conversion.encode(second)
    assert conversion.schema()["additionalProperties"] is False
    assert fingerprint(KEY, conversion.encode(first), (RESOURCE,), ()) == fingerprint(
        KEY, conversion.encode(second), (RESOURCE,), ()
    )
    assert conversion.decode({}).amount == Decimal(0)


@pytest.mark.parametrize(
    "payload",
    [
        {"count": True},
        {"count": "2"},
        {"count": 2.0},
        {"extra": "private"},
        {"amount": 1.25},
        {"amount": "NaN"},
        {"amount": "Infinity"},
        {"count": 2**53},
        {"day": "not-a-date"},
        {"items": [True]},
        {"count": None},
    ],
)
def test_strict_invalid_inputs(payload: JsonObject) -> None:
    with pytest.raises(WireFailure, match="invalid_input") as error:
        codec().decode(payload)
    assert "private" not in str(error.value)


def test_missing_field_alias_and_invalid_defaults() -> None:
    class Required(StrictWireModel):
        count: int

    required = PydanticCodec(Required, lambda model: model.count, lambda count: {"count": count})
    with pytest.raises(WireFailure) as error:
        required.decode({})
    assert error.value.location == ("count",)

    class Alias(StrictWireModel):
        count: int = Field(alias="other")

    with pytest.raises(ValueError, match="aliases"):
        PydanticCodec(Alias, lambda model: model.count, lambda count: {"count": count})

    class InvalidDefault(StrictWireModel):
        count: int = cast(int, cast(object, "2"))

    invalid = PydanticCodec(
        InvalidDefault, lambda model: model.count, lambda count: {"count": count}
    )
    with pytest.raises(WireFailure):
        invalid.decode({})


def test_envelope_defaults_versions_and_correlation_exclusion() -> None:
    raw = dict(envelope())
    raw["expected_versions"] = [
        {"resource": {"kind": "fixture", "identity": "target"}, "version": "9007199254740992"}
    ]
    first = decode_envelope(raw)
    second = decode_envelope({**raw, "correlation_id": "request-b", "retry_key": "retry-b"})
    assert first.expected_versions[0].version == "9007199254740992"
    assert fingerprint(
        first.operation,
        codec().encode(codec().decode(first.payload)),
        (RESOURCE,),
        first.expected_versions,
    ) == fingerprint(
        second.operation,
        codec().encode(codec().decode(second.payload)),
        (RESOURCE,),
        second.expected_versions,
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("authority", "admin"),
        ("contract_version", 1),
        ("payload", []),
        ("correlation_id", " "),
        ("operation", "INVALID"),
        ("retry_key", 1),
        (
            "expected_versions",
            [{"resource": {"kind": "fixture", "identity": "target"}, "version": 2}],
        ),
        (
            "expected_versions",
            [{"resource": {"kind": "fixture", "identity": "target", "x": 1}, "version": "1"}],
        ),
    ],
)
def test_invalid_envelope(field: str, value: JsonValue) -> None:
    with pytest.raises(WireFailure, match="invalid_input"):
        decode_envelope({**envelope(), field: value})


def test_full_envelope_exact_size_and_depth_limits() -> None:
    raw = envelope({"items": [{"text": "\u00e9"}]})
    length = len(canonical_bytes(raw))
    assert canonical_bytes(
        decode_envelope(raw, OperationLimits(length, 4)).payload
    ) == canonical_bytes({"items": [{"text": "\u00e9"}]})
    for limits, limit in [
        (OperationLimits(length - 1, 4), "max_input_bytes"),
        (OperationLimits(length, 3), "max_nesting_depth"),
    ]:
        with pytest.raises(WireFailure) as error:
            decode_envelope(raw, limits)
        assert error.value.limit == limit


def test_exact_default_megabyte_and_32_container_boundaries() -> None:
    raw = envelope({"text": ""})
    padding = 1_048_576 - len(canonical_bytes(raw))
    assert decode_envelope(envelope({"text": "x" * padding}))
    with pytest.raises(WireFailure, match="limit_exceeded"):
        decode_envelope(envelope({"text": "x" * (padding + 1)}))
    nested: JsonValue = "leaf"
    for _ in range(30):
        nested = [nested]
    assert decode_envelope(envelope({"value": nested}))
    with pytest.raises(WireFailure, match="limit_exceeded"):
        decode_envelope(envelope({"value": [nested]}))


def test_result_contract_and_exact_output_cap() -> None:
    value = codec().decode({"amount": "1.25"})
    size = len(canonical_bytes(to_wire(value)))
    assert canonical_bytes(
        codec(OperationLimits(max_output_bytes=size)).encode(value)
    ) == canonical_bytes(to_wire(value))
    for result, limit in [
        (value, size - 1),
        (replace(value, count=True), size),
        (replace(value, amount=Decimal("NaN")), size),
    ]:
        with pytest.raises(WireFailure, match="result_contract_failure"):
            codec(OperationLimits(max_output_bytes=limit)).encode(result)


def binding(effects: list[int], effect: EffectDisposition) -> OperationBinding[Request, Request]:
    async def handler(request: Request, context: CommandContext) -> OutcomeProposal[Request]:
        effects.append(request.count)
        return OutcomeProposal(request, effect, (STAGE,), (EVIDENCE,))

    inputs = codec()
    outputs = codec(OperationLimits(max_output_bytes=2))
    desc = replace(
        descriptor(),
        input_schema=inputs.schema(),
        result_schema=outputs.schema(),
        limits=outputs.limits,
    )
    return OperationBinding(desc, inputs, outputs, CommandBehavior(handler), lambda _: (RESOURCE,))


@pytest.mark.parametrize("effect", list(EffectDisposition))
def test_registry_oversized_result_preserves_all_observations(effect: EffectDisposition) -> None:
    effects: list[int] = []
    call = binding(effects, effect).bind().prepare({"count": 7})
    assert isinstance(call, PreparedCommand)
    observed = asyncio.run(call.invoke(contexts()[1]))
    with pytest.raises(WireFailure, match="result_contract_failure"):
        observed.encode_result()
    assert effects == [7]
    assert observed.effect is effect
    assert observed.stages == (STAGE,)
    assert observed.evidence == (EVIDENCE,)


def test_invalid_or_overdepth_registry_input_never_invokes_behavior() -> None:
    effects: list[int] = []
    operation = binding(effects, EffectDisposition.APPLIED).bind()
    nested: JsonValue = []
    for _ in range(32):
        nested = [nested]
    for payload in ({"count": "7"}, {"items": nested}):
        with pytest.raises(WireFailure):
            operation.prepare(payload)
    assert not effects


def test_serializer_exception_is_safe_result_contract_failure() -> None:
    def broken(value: Request) -> JsonObject:
        raise RuntimeError("credential-private-value")

    conversion = PydanticCodec(RequestWire, from_wire, broken)
    with pytest.raises(WireFailure, match="result_contract_failure") as error:
        conversion.encode(codec().decode({}))
    assert "credential" not in str(error.value)


def test_result_defaults_are_materialized_before_output_cap() -> None:
    conversion = PydanticCodec(
        RequestWire, from_wire, lambda value: {}, OperationLimits(max_output_bytes=2)
    )
    with pytest.raises(WireFailure, match="result_contract_failure") as error:
        conversion.encode(codec().decode({}))
    assert error.value.limit == "max_output_bytes"


def test_domain_decimal_cannot_escape_as_implicit_wire_number() -> None:
    def unsafe(value: Request) -> JsonObject:
        return {"amount": cast(JsonValue, cast(object, value.amount))}

    conversion = PydanticCodec(RequestWire, from_wire, unsafe)
    with pytest.raises(WireFailure, match="result_contract_failure"):
        conversion.encode(codec().decode({}))


def test_declared_model_serializer_cannot_emit_a_schema_violation() -> None:
    class InvalidSerialized(StrictWireModel):
        count: int

        @field_serializer("count")
        def invalid_count(self, value: int) -> str:
            return str(value)

    conversion = PydanticCodec(
        InvalidSerialized, lambda model: model.count, lambda count: {"count": count}
    )
    with pytest.raises(WireFailure, match="result_contract_failure"):
        conversion.encode(2)


@pytest.mark.parametrize("depth", [32, 33])
def test_valid_normalized_defaults_remain_fingerprintable(depth: int) -> None:
    nested: JsonValue = "leaf"
    for _ in range(depth - 2):
        nested = [nested]
    default: dict[str, JsonValue] = {"nested": nested}

    class DeepWire(StrictWireModel):
        data: dict[str, JsonValue] = Field(default_factory=lambda: default)

    limits = OperationLimits(max_nesting_depth=depth)
    conversion = PydanticCodec(
        DeepWire, lambda value: freeze_object(value.data), lambda value: {"data": value}, limits
    )
    request = decode_envelope(envelope(), limits)
    canonical = conversion.encode(conversion.decode(request.payload))
    assert len(fingerprint(request.operation, canonical, (), ())) == 64
    assert canonical == conversion.encode(conversion.decode(canonical))


@pytest.mark.parametrize("kind", ["top", "nested", "list", "mapping"])
def test_float_fields_reject_implicit_integer_conversion_both_directions(kind: str) -> None:
    class Nested(StrictWireModel):
        value: float

    class Floats(StrictWireModel):
        top: float = 0.0
        nested: Nested = Field(default_factory=lambda: Nested(value=0.0))
        items: list[float] = Field(default_factory=list[float])
        mapping: dict[str, float] = Field(default_factory=dict[str, float])

    values: dict[str, JsonObject] = {
        "top": {"top": 1},
        "nested": {"nested": {"value": 1}},
        "list": {"items": [1]},
        "mapping": {"mapping": {"key": 1}},
    }
    conversion = PydanticCodec(Floats, lambda model: 0, lambda value: values[kind])
    with pytest.raises(WireFailure, match="invalid_input"):
        conversion.decode(values[kind])
    with pytest.raises(WireFailure, match="result_contract_failure"):
        conversion.encode(0)
    assert (
        conversion.decode(
            {"top": 1.0, "nested": {"value": 1.0}, "items": [1.0], "mapping": {"key": 1.0}}
        )
        == 0
    )


def test_input_normalization_does_not_apply_smaller_result_budget() -> None:
    limits = OperationLimits(max_input_bytes=1_000, max_output_bytes=2)
    inputs = codec(limits).for_input()
    outputs = codec(limits)
    original = binding([], EffectDisposition.APPLIED)
    desc = replace(original.descriptor, limits=limits)
    operation = replace(original, descriptor=desc, input_codec=inputs, result_codec=outputs).bind()
    prepared = operation.prepare({"count": 7})
    assert isinstance(prepared, PreparedCommand)
    assert prepared.canonical_content["count"] == 7
    observed = asyncio.run(prepared.invoke(contexts()[1]))
    with pytest.raises(WireFailure, match="result_contract_failure"):
        observed.encode_result()
    assert observed.effect is EffectDisposition.APPLIED
