"""Strict app issue boundary; upstream prepared/policy codecs stay authoritative."""

import json
from dataclasses import asdict
from importlib.resources import files
from typing import Literal, cast

from pydantic import TypeAdapter

from craftreport.adapters.binding_codecs import BindingResultCodec, RunWire, parameter_digest
from craftreport.adapters.report_codecs import prepared_identifier, validation_scope_identifier
from craftreport.adapters.validation import PydanticCodec, StrictWireModel, construct, model_shape
from craftreport.contracts import OperationLimits
from craftreport.contracts.values import JsonObject, freeze_object
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins
from craftreport_gridcraft.app_values import (
    AppSettings,
    ArtifactRef,
    BrowserTarget,
    SavedCandidate,
    TargetObservation,
)
from craftreport_gridcraft.values import DECLARATION, PROFILE, AppIssue, OwnedLayout

_LIMITS = OperationLimits(max_input_bytes=65536, max_output_bytes=262144)


class IssueWire(StrictWireModel):
    code: Literal["unsupported", "untested", "limit", "conflict", "unavailable"]
    location: tuple[str | int, ...]
    stage: Literal["admit", "bootstrap"]
    effect: Literal["none"]


def issue_codec() -> PydanticCodec[AppIssue, IssueWire]:
    return PydanticCodec(
        IssueWire,
        lambda w: AppIssue(w.code, w.location, w.stage, w.effect),
        lambda v: {"code": v.code, "location": v.location, "stage": v.stage, "effect": v.effect},
        json_mode=True,
        limits=_LIMITS,
    )


def mapping_pins_match(prepared: PreparedReport, quality: QualityEvaluation, run: RunPins) -> bool:
    return (
        run.resolved_parameters == prepared.resolved_parameters
        and run.parameter_digest == parameter_digest(prepared.resolved_parameters)
        and run.validation_scope == validation_scope_identifier(prepared.release_policy)
        and all(f.scope.validation_scope_digest == run.validation_scope for f in quality.findings)
    )


def prepared_content_matches(prepared: PreparedReport) -> bool:
    return prepared_identifier(prepared) == prepared.content_digest


class SettingsWire(model_shape(AppSettings, {})):
    pass


class TargetWire(model_shape(BrowserTarget, {})):
    pass


class ObservationWire(model_shape(TargetObservation, {"run": RunWire})):
    pass


class CandidateWire(model_shape(SavedCandidate, {"run": RunWire})):
    pass


class ArtifactWire(model_shape(ArtifactRef, {"candidate": CandidateWire})):
    pass


class LayoutWire(model_shape(OwnedLayout, {"run": RunWire})):
    pass


def _run(value: StrictWireModel) -> RunPins:
    run = cast(RunWire, getattr(value, "run"))
    result = BindingResultCodec().decode(cast(JsonObject, run.model_dump(mode="json")))
    if type(result) is not RunPins:
        raise ValueError("Exact runtime run required")
    return result


def _candidate(value: CandidateWire) -> SavedCandidate:
    return construct(SavedCandidate, value, {"run": _run(value)})


def _candidate_object(value: SavedCandidate) -> JsonObject:
    return {**cast(JsonObject, asdict(value)), "run": BindingResultCodec().encode(value.run)}


def _observation_object(value: TargetObservation) -> JsonObject:
    result = cast(JsonObject, TypeAdapter(TargetObservation).dump_python(value, mode="json"))
    return {**result, "run": BindingResultCodec().encode(value.run)}


def settings_codec() -> PydanticCodec[AppSettings, SettingsWire]:
    return PydanticCodec(
        SettingsWire,
        lambda v: construct(AppSettings, v, {}),
        lambda v: cast(JsonObject, asdict(v)),
        json_mode=True,
        limits=_LIMITS,
    ).for_input()


def target_codec() -> PydanticCodec[BrowserTarget, TargetWire]:
    return PydanticCodec(
        TargetWire,
        lambda v: construct(BrowserTarget, v, {}),
        lambda v: cast(JsonObject, asdict(v)),
        json_mode=True,
        limits=_LIMITS,
    )


def observation_codec() -> PydanticCodec[TargetObservation, ObservationWire]:
    return PydanticCodec(
        ObservationWire,
        lambda v: construct(TargetObservation, v, {"run": _run(v)}),
        _observation_object,
        json_mode=True,
        limits=_LIMITS,
    )


def candidate_codec() -> PydanticCodec[SavedCandidate, CandidateWire]:
    return PydanticCodec(
        CandidateWire, _candidate, _candidate_object, json_mode=True, limits=_LIMITS
    )


def artifact_codec() -> PydanticCodec[ArtifactRef, ArtifactWire]:
    return PydanticCodec(
        ArtifactWire,
        lambda v: construct(
            ArtifactRef, v, {"candidate": _candidate(cast(CandidateWire, getattr(v, "candidate")))}
        ),
        lambda v: {**cast(JsonObject, asdict(v)), "candidate": _candidate_object(v.candidate)},
        json_mode=True,
        limits=_LIMITS,
    )


def layout_codec() -> PydanticCodec[OwnedLayout, LayoutWire]:
    return PydanticCodec(
        LayoutWire,
        lambda v: construct(OwnedLayout, v, {"run": _run(v)}),
        lambda v: {**cast(JsonObject, asdict(v)), "run": BindingResultCodec().encode(v.run)},
        json_mode=True,
        limits=_LIMITS,
    )


def support_descriptor() -> JsonObject:
    """Installed release/profile disclosure; no runtime operation is activated here."""
    resource = cast(
        JsonObject,
        json.loads(
            files("craftreport_gridcraft")
            .joinpath("resources/support.json")
            .read_text(encoding="utf-8")
        ),
    )
    return freeze_object(
        {
            **resource,
            "profile_pin": cast(JsonObject, asdict(PROFILE.pin)),
            "declaration": cast(JsonObject, json.loads(DECLARATION)),
        }
    )
