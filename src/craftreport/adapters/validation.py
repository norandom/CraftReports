"""Strict shared decoded-object validation with explicit domain serializers."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Self, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from craftreport.adapters.canonical import WireFailure, bounded_object
from craftreport.contracts import (
    ExpectedVersion,
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    OperationLimits,
    ResourceRef,
)
from craftreport.contracts.identity import check_preconditions
from craftreport.contracts.values import JsonValue, freeze_object, require_immutable


class StrictWireModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        validate_default=True,
        allow_inf_nan=False,
        validate_by_alias=False,
        validate_by_name=True,
    )


def _reject_numeric_coercion(before: JsonValue, after: object) -> None:
    """Pydantic strict floats still accept ints; preserve wire numeric kinds."""
    if type(before) in (bool, int, float) and type(before) is not type(after):
        raise WireFailure("invalid_input")
    if isinstance(before, Mapping):
        for key, value in before.items():
            _reject_numeric_coercion(value, _member(after, key))
    elif isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        for value, validated in zip(
            before, cast(list[object] | tuple[object, ...], after), strict=True
        ):
            _reject_numeric_coercion(value, validated)


def _member(value: object, key: str) -> object:
    if isinstance(value, BaseModel):
        return getattr(value, key)
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)[key]
    raise WireFailure("invalid_input")


@dataclass(frozen=True, slots=True)
class PydanticCodec[T, M: StrictWireModel]:
    """Authors declare wire fields and both directions; no implicit domain coercion.

    Serializers return JSON primitives explicitly, including string representations
    for Decimal/date domain fields. Their output is revalidated before exposure.
    """

    model: type[M]
    from_wire: Callable[[M], T]
    to_wire: Callable[[T], JsonObject]
    limits: OperationLimits = OperationLimits()

    def __post_init__(self) -> None:
        if any(
            field.alias or field.validation_alias or field.serialization_alias
            for field in self.model.model_fields.values()
        ):
            raise ValueError("Wire aliases require a separate versioned field contract")

    def for_input(self) -> Self:
        """Use on input bindings: encode normalizes requests under the input cap.

        Result bindings retain the advertised output cap. Registry's Codec
        protocol uses encode for both roles, so their budgets must be distinct.
        """
        return replace(
            self, limits=replace(self.limits, max_output_bytes=self.limits.max_input_bytes)
        )

    def decode(self, value: JsonObject) -> T:
        checked = bounded_object(value, self.limits.max_input_bytes, self.limits.max_nesting_depth)
        try:
            model = self.model.model_validate(
                checked, strict=True, extra="forbid", by_alias=False, by_name=True
            )
            _reject_numeric_coercion(checked, model)
            result = self.from_wire(model)
            require_immutable(result)
            return result
        except ValidationError as error:
            location = error.errors(include_input=False, include_context=False)[0]["loc"]
            safe = tuple(
                part if isinstance(part, int) or part in self.model.model_fields else "<field>"
                for part in location
            )
            raise WireFailure("invalid_input", location=safe) from None
        except WireFailure:
            raise
        except (ValueError, TypeError):
            raise WireFailure("invalid_input") from None

    def encode(self, value: T) -> JsonObject:
        try:
            require_immutable(value)
            output = bounded_object(
                self.to_wire(value), self.limits.max_output_bytes, self.limits.max_nesting_depth
            )
            model = self.model.model_validate(
                output, strict=True, extra="forbid", by_alias=False, by_name=True
            )
            _reject_numeric_coercion(output, model)
            resolved = bounded_object(
                model.model_dump(mode="python", by_alias=False),
                self.limits.max_output_bytes,
                self.limits.max_nesting_depth,
            )
            serialized = self.model.model_validate(
                resolved, strict=True, extra="forbid", by_alias=False, by_name=True
            )
            _reject_numeric_coercion(resolved, serialized)
            return freeze_object(resolved)
        except WireFailure as error:
            limit = "max_output_bytes" if error.limit == "max_input_bytes" else error.limit
            raise WireFailure("result_contract_failure", limit=limit) from None
        except Exception:
            raise WireFailure("result_contract_failure") from None

    def schema(self) -> JsonObject:
        return freeze_object(self.model.model_json_schema(by_alias=False))


class _ResourceWire(StrictWireModel):
    kind: str = Field(min_length=1, pattern=r"\S")
    identity: str = Field(min_length=1, pattern=r"\S")


class _ExpectedWire(StrictWireModel):
    resource: _ResourceWire
    version: str = Field(min_length=1, pattern=r"\S")


class _EnvelopeWire(StrictWireModel):
    operation: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,47}$")
    contract_version: str = Field(pattern=r"^[1-9][0-9]*$")
    payload: dict[str, object]
    correlation_id: str = Field(min_length=1, pattern=r"\S")
    retry_key: str | None = Field(default=None, min_length=1, pattern=r"\S")
    expected_versions: list[_ExpectedWire] = Field(default_factory=list[_ExpectedWire])


def _envelope_location(location: tuple[str | int, ...]) -> tuple[str | int, ...]:
    """Disclose only paths from the public envelope; never arbitrary input keys."""
    children: dict[tuple[str | int, ...], set[str]] = {
        (): set(_EnvelopeWire.model_fields),
        ("expected_versions", -1): set(_ExpectedWire.model_fields),
        ("expected_versions", -1, "resource"): set(_ResourceWire.model_fields),
    }
    safe: list[str | int] = []
    for part in location:
        path = tuple(-1 if isinstance(item, int) else item for item in safe)
        if type(part) is int and part >= 0 and path == ("expected_versions",):
            safe.append(part)
        elif isinstance(part, str) and part in children.get(path, set()):
            safe.append(part)
        else:
            safe.append("field")
            break
    return tuple(safe)


def _decode_versions(values: list[_ExpectedWire]) -> tuple[ExpectedVersion, ...]:
    result = tuple(
        ExpectedVersion(ResourceRef(pin.resource.kind, pin.resource.identity), pin.version)
        for pin in values
    )
    try:
        check_preconditions(result)
    except ValueError:
        raise WireFailure("invalid_input", location=("expected_versions",)) from None
    return result


def decode_envelope(
    value: JsonObject, limits: OperationLimits = OperationLimits()
) -> InvocationEnvelope:
    """Enforce decoded whole-envelope limits before model or payload processing.

    Depth counts containers including the root object. Bytes count compact sorted
    UTF-8 JSON, excluding transport framing/whitespace. REST also caps raw bytes.
    """
    checked = bounded_object(value, limits.max_input_bytes, limits.max_nesting_depth)
    try:
        model = _EnvelopeWire.model_validate(
            checked, strict=True, extra="forbid", by_alias=False, by_name=True
        )
        payload = checked["payload"]
        if not isinstance(payload, dict):
            raise WireFailure("invalid_input")
        return InvocationEnvelope(
            OperationKey(model.operation, model.contract_version),
            payload,
            model.correlation_id,
            model.retry_key,
            _decode_versions(model.expected_versions),
        )
    except ValidationError as error:
        location = error.errors(include_input=False, include_context=False)[0]["loc"]
        raise WireFailure("invalid_input", location=_envelope_location(location)) from None
    except WireFailure:
        raise
    except (ValueError, TypeError):
        raise WireFailure("invalid_input") from None


class DecodedInvocationLimits:
    """Fixed shared limit check after operation authorization, before preparation."""

    def check(self, request: InvocationEnvelope, limits: OperationLimits) -> None:
        value: JsonObject = {
            "operation": request.operation.name,
            "contract_version": request.operation.contract_version,
            "payload": request.payload,
            "correlation_id": request.correlation_id,
            "retry_key": request.retry_key,
            "expected_versions": [
                {
                    "resource": {"kind": pin.resource.kind, "identity": pin.resource.identity},
                    "version": pin.version,
                }
                for pin in request.expected_versions
            ],
        }
        bounded_object(value, limits.max_input_bytes, limits.max_nesting_depth)

    def check_result(self, value: JsonObject, limits: OperationLimits) -> None:
        bounded_object(value, limits.max_output_bytes, limits.max_nesting_depth)
