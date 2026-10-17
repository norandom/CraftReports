"""Closed binding wire contracts derived from the runtime-owned values."""

from dataclasses import fields
from hashlib import sha256
from typing import Annotated, cast

from pydantic import Field, TypeAdapter

from craftreport.adapters.canonical import WireFailure, bounded_object, canonical_bytes
from craftreport.adapters.schema_embedding import close_schema
from craftreport.adapters.snapshot_models import (
    ConflictValue,
    MissingValue,
    ParameterWire,
    SnapshotRefWire,
    UnavailableValue,
    reference_object,
    reference_value,
)
from craftreport.adapters.snapshot_wire import decode_parameter, encode_parameter
from craftreport.adapters.validation import PydanticCodec, construct, model_shape
from craftreport.application.ports import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import JsonObject
from craftreport.contracts.values import freeze_object
from craftreport.data.requirements import InputRequirements
from craftreport.data.values import Scalar
from craftreport.runtime.values import (
    BindingSpec,
    BindingState,
    BindRequest,
    ControlRequest,
    EffectObservation,
    InspectRequest,
    RunPins,
)

Count = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,18})$")]
_requirements = TypeAdapter(InputRequirements)


def requirements_digest(value: InputRequirements) -> str:
    return sha256(
        canonical_bytes(cast(JsonObject, _requirements.dump_python(value, mode="json")))
    ).hexdigest()


def parameter_digest(value: tuple[tuple[str, Scalar], ...]) -> str:
    return sha256(
        canonical_bytes({"parameters": tuple((n, encode_parameter(v)) for n, v in value)})
    ).hexdigest()


def _members(
    value: (
        BindingSpec
        | BindingState
        | RunPins
        | BindRequest
        | ControlRequest
        | InspectRequest
        | EffectObservation
    ),
) -> JsonObject:
    return cast(JsonObject, {f.name: getattr(value, f.name) for f in fields(value)})


class SpecWire(
    model_shape(BindingSpec, {"resolved_parameters": tuple[tuple[str, ParameterWire], ...]})
):
    pass


class ObservationWire(model_shape(EffectObservation, {"binding_generation": Count})):
    pass


class StateWire(
    model_shape(
        BindingState,
        {
            "spec": SpecWire,
            "generation": Count,
            "revision": Count,
            "latest_complete_snapshot": SnapshotRefWire | None,
            "applied_snapshot": SnapshotRefWire | None,
            "observations": tuple[ObservationWire, ...],
        },
    )
):
    pass


class RunWire(
    model_shape(
        RunPins,
        {
            "snapshot": SnapshotRefWire,
            "binding_generation": Count,
            "resolved_parameters": tuple[tuple[str, ParameterWire], ...],
        },
    )
):
    pass


class BindWire(model_shape(BindRequest, {"spec": SpecWire, "expected_generation": Count})):
    pass


class ControlWire(model_shape(ControlRequest, {"expected_generation": Count})):
    pass


class InspectWire(model_shape(InspectRequest, {})):
    pass


def _parameters(value: SpecWire | RunWire) -> tuple[tuple[str, Scalar], ...]:
    return tuple(
        (n, decode_parameter(cast(JsonObject, p.model_dump(mode="json"))))
        for n, p in cast(
            tuple[tuple[str, ParameterWire], ...], getattr(value, "resolved_parameters")
        )
    )


def _spec_object(value: BindingSpec) -> JsonObject:
    if value.requirements_digest != requirements_digest(
        value.requirements
    ) or value.parameter_digest != parameter_digest(value.resolved_parameters):
        raise ValueError("Binding content digest differs")
    return {
        **_members(value),
        "resolved_parameters": tuple(
            (n, dict(encode_parameter(v))) for n, v in value.resolved_parameters
        ),
    }


def _spec(value: SpecWire) -> BindingSpec:
    result = construct(BindingSpec, value, {"resolved_parameters": _parameters(value)})
    _spec_object(result)
    return result


def _observation_object(value: EffectObservation) -> JsonObject:
    return {**_members(value), "binding_generation": str(value.binding_generation)}


def _observation(value: ObservationWire) -> EffectObservation:
    return construct(
        EffectObservation,
        value,
        {"binding_generation": int(getattr(value, "binding_generation"))},
    )


def _state_object(value: BindingState) -> JsonObject:
    return {
        **_members(value),
        "spec": _spec_object(value.spec),
        "generation": str(value.generation),
        "revision": str(value.revision),
        "latest_complete_snapshot": (
            None
            if value.latest_complete_snapshot is None
            else reference_object(value.latest_complete_snapshot)
        ),
        "applied_snapshot": (
            None if value.applied_snapshot is None else reference_object(value.applied_snapshot)
        ),
        "observations": tuple(_observation_object(item) for item in value.observations),
    }


def _state(value: StateWire) -> BindingState:
    latest = cast(SnapshotRefWire | None, getattr(value, "latest_complete_snapshot"))
    applied = cast(SnapshotRefWire | None, getattr(value, "applied_snapshot"))
    observations = cast(tuple[ObservationWire, ...], getattr(value, "observations"))
    return construct(
        BindingState,
        value,
        {
            "spec": _spec(cast(SpecWire, getattr(value, "spec"))),
            "generation": int(getattr(value, "generation")),
            "revision": int(getattr(value, "revision")),
            "latest_complete_snapshot": None if latest is None else reference_value(latest),
            "applied_snapshot": None if applied is None else reference_value(applied),
            "observations": tuple(_observation(item) for item in observations),
        },
    )


def _run_object(value: RunPins) -> JsonObject:
    if value.parameter_digest != parameter_digest(value.resolved_parameters):
        raise ValueError("Run parameter digest differs")
    return {
        **_members(value),
        "snapshot": reference_object(value.snapshot),
        "binding_generation": str(value.binding_generation),
        "resolved_parameters": tuple(
            (n, dict(encode_parameter(v))) for n, v in value.resolved_parameters
        ),
    }


def _run(value: RunWire) -> RunPins:
    result = construct(
        RunPins,
        value,
        {
            "resolved_parameters": _parameters(value),
            "snapshot": reference_value(cast(SnapshotRefWire, getattr(value, "snapshot"))),
            "binding_generation": int(getattr(value, "binding_generation")),
        },
    )
    _run_object(result)
    return result


def bind_codec() -> PydanticCodec[BindRequest, BindWire]:
    return PydanticCodec(
        BindWire,
        lambda v: BindRequest(
            _spec(cast(SpecWire, getattr(v, "spec"))), int(getattr(v, "expected_generation"))
        ),
        lambda v: cast(
            JsonObject,
            BindWire(
                **{"spec": _spec_object(v.spec), "expected_generation": str(v.expected_generation)}
            ).model_dump(mode="json"),
        ),
        json_mode=True,
    ).for_input()


def control_codec() -> PydanticCodec[ControlRequest, ControlWire]:
    return PydanticCodec(
        ControlWire,
        lambda v: construct(
            ControlRequest, v, {"expected_generation": int(getattr(v, "expected_generation"))}
        ),
        lambda v: {**_members(v), "expected_generation": str(v.expected_generation)},
        json_mode=True,
    ).for_input()


def inspect_codec() -> PydanticCodec[InspectRequest, InspectWire]:
    return PydanticCodec(
        InspectWire, lambda v: construct(InspectRequest, v, {}), _members, json_mode=True
    ).for_input()


_results = TypeAdapter(StateWire | RunWire | MissingValue | UnavailableValue | ConflictValue)


class BindingResultCodec:
    def decode(
        self, value: JsonObject
    ) -> BindingState | RunPins | Missing | ServiceUnavailable | VersionConflict:
        try:
            result = _results.validate_json(
                canonical_bytes(bounded_object(value, 1_048_576)), strict=True, extra="forbid"
            )
            return (
                _state(result)
                if isinstance(result, StateWire)
                else _run(result)
                if isinstance(result, RunWire)
                else result
            )
        except ValueError:
            raise WireFailure("invalid_input") from None

    def encode(
        self, value: BindingState | RunPins | Missing | ServiceUnavailable | VersionConflict
    ) -> JsonObject:
        model = (
            StateWire(**_state_object(value))
            if isinstance(value, BindingState)
            else RunWire(**_run_object(value))
            if isinstance(value, RunPins)
            else value
        )
        raw = cast(JsonObject, _results.dump_python(model, mode="json", warnings="error"))
        self.decode(raw)
        return freeze_object(raw)

    def schema(self) -> JsonObject:
        return freeze_object(close_schema(_results.json_schema()))
