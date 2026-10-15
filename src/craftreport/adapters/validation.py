"""Strict shared decoded-object validation with explicit domain serializers."""

from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, fields, is_dataclass, replace
from typing import Self, cast, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model

from craftreport.adapters.canonical import WireFailure, bounded_object, canonical_bytes
from craftreport.adapters.schema_embedding import close_schema
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


def model_shape[T](
    cls: type[T],
    overrides: dict[str, object],
    omit: tuple[str, ...] = (),
    defaults: dict[str, object] | None = None,
) -> type[StrictWireModel]:
    """Project fixed dataclass fields; callers explicitly declare wire differences."""
    assert is_dataclass(cls)
    hints = get_type_hints(cls)
    definitions = {
        f.name: (hints[f.name], ... if f.default is MISSING else f.default)
        for f in fields(cls)
        if f.name not in omit
    }
    definitions.update(
        {name: (annotation, definitions[name][1]) for name, annotation in overrides.items()}
    )
    definitions.update(
        {name: (definitions[name][0], value) for name, value in (defaults or {}).items()}
    )
    factory = cast(Callable[..., type[StrictWireModel]], create_model)
    return factory(cls.__name__ + "Boundary", __base__=StrictWireModel, **definitions)


def construct[T](cls: type[T], model: StrictWireModel, replacements: dict[str, object]) -> T:
    assert is_dataclass(cls)
    values: dict[str, object] = {f.name: getattr(model, f.name) for f in fields(cls)}
    values.update(replacements)
    return cls(**values)


def _reject_numeric_coercion(before: JsonValue, after: object, json_mode: bool = False) -> None:
    """Pydantic strict floats still accept ints; preserve wire numeric kinds."""
    if type(before) in (bool, int, float) and type(before) is not type(after):
        if not (json_mode and type(before) is int and type(after) is float):
            raise WireFailure("invalid_input")
    if isinstance(before, Mapping):
        for key, value in before.items():
            _reject_numeric_coercion(value, _member(after, key), json_mode)
    elif isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        for value, validated in zip(
            before, cast(list[object] | tuple[object, ...], after), strict=True
        ):
            _reject_numeric_coercion(value, validated, json_mode)


def _member(value: object, key: str) -> object:
    if isinstance(value, BaseModel) or is_dataclass(value) and not isinstance(value, type):
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
    json_mode: bool = False

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

    def _validate(self, value: JsonObject) -> M:
        if self.json_mode:
            model = self.model.model_validate_json(
                canonical_bytes(value), strict=True, extra="forbid", by_alias=False, by_name=True
            )
        else:
            model = self.model.model_validate(
                value, strict=True, extra="forbid", by_alias=False, by_name=True
            )
        _reject_numeric_coercion(value, model, self.json_mode)
        return model

    def decode(self, value: JsonObject) -> T:
        checked = bounded_object(value, self.limits.max_input_bytes, self.limits.max_nesting_depth)
        try:
            model = self._validate(checked)
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
            model = self._validate(output)
            resolved = bounded_object(
                model.model_dump(mode="json" if self.json_mode else "python", by_alias=False),
                self.limits.max_output_bytes,
                self.limits.max_nesting_depth,
            )
            self._validate(resolved)
            return freeze_object(resolved)
        except WireFailure as error:
            limit = "max_output_bytes" if error.limit == "max_input_bytes" else error.limit
            raise WireFailure("result_contract_failure", limit=limit) from None
        except Exception:
            raise WireFailure("result_contract_failure") from None

    def schema(self) -> JsonObject:
        schema = self.model.model_json_schema(by_alias=False)
        return freeze_object(close_schema(schema) if self.json_mode else schema)


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
