"""Thin asset envelopes borrowing existing immutable declaration contracts."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, JsonValue
from pydantic.json_schema import SkipJsonSchema

from craftreport.adapters.snapshot_models import (
    MetricWire,
    ParameterWire,
    ScalarWire,
    SnapshotRefWire,
)
from craftreport.adapters.validation import StrictWireModel, model_shape
from craftreport.contracts.identity import CapabilityRequirement
from craftreport.data.values import ScalarKind
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.definitions import ParameterValue, ReportDefinition
from craftreport.reporting.ports import (
    DiscoveryResult,
    EmptyRequest,
    PreparationResult,
    PrepareRequest,
    ValidateRequest,
    ValidationResult,
)
from craftreport.reporting.prepared import (
    PreparedLineChart,
    PreparedReport,
    PreparedSeries,
    PreparedTable,
)
from craftreport.themes.values import SemanticRole, StyleProperty


def _present(value: object) -> object:
    if value is None:
        raise ValueError("Present scalar requires a tag")
    return value


def _omit_default(schema: dict[str, JsonValue]) -> None:
    schema.pop("default", None)


def _absent(value: object) -> bool:
    return value is None


type OptionalParameter = Annotated[
    ParameterWire | SkipJsonSchema[None],
    BeforeValidator(_present),
]


class ParameterDeclarationWire(StrictWireModel):
    name: str
    kind: ScalarKind
    required: bool
    default: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default, exclude_if=_absent
    )
    choices: tuple[ParameterWire, ...] = ()
    minimum: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default, exclude_if=_absent
    )
    maximum: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default, exclude_if=_absent
    )


class DefinitionWire(
    model_shape(ReportDefinition, {"parameters": tuple[ParameterDeclarationWire, ...]})
):
    pass


class AssetReference(StrictWireModel):
    path: str
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PackManifest(StrictWireModel):
    schema_version: Literal["1"]
    namespace: str
    name: str
    version: str
    engine_version_range: str
    definition: AssetReference
    template: AssetReference
    theme: AssetReference
    required_capabilities: tuple[CapabilityRequirement, ...]
    permitted_overrides: tuple[tuple[SemanticRole, StyleProperty], ...]
    source_visibility_scope: str
    artifact_visibility_scope: str
    attribution: str


class ParameterValueWire(model_shape(ParameterValue, {"value": ParameterWire})):
    pass


class TableWire(model_shape(PreparedTable, {"rows": tuple[tuple[ScalarWire, ...], ...]})):
    pass


class SeriesWire(model_shape(PreparedSeries, {"values": tuple[ScalarWire, ...]})):
    pass


class ChartWire(
    model_shape(
        PreparedLineChart, {"categories": tuple[ScalarWire, ...], "series": tuple[SeriesWire, ...]}
    )
):
    pass


class PreparedContentWire(
    model_shape(
        PreparedReport,
        {
            "snapshot": SnapshotRefWire,
            "resolved_parameters": tuple[tuple[str, ParameterWire], ...],
            "tables": tuple[TableWire, ...],
            "charts": tuple[ChartWire, ...],
            "metric_provenance": tuple[MetricWire, ...],
        },
        ("content_digest",),
    )
):
    pass


class PreparedWire(PreparedContentWire):
    content_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ValidateWire(
    model_shape(
        ValidateRequest,
        {
            "definition": DefinitionWire | None,
            "parameters": Annotated[tuple[ParameterValueWire, ...], Field(max_length=16)],
        },
    )
):
    pass


class PrepareWire(
    model_shape(
        PrepareRequest,
        {
            "definition": DefinitionWire | None,
            "parameters": Annotated[tuple[ParameterValueWire, ...], Field(max_length=16)],
            "snapshot": SnapshotRefWire,
        },
    )
):
    pass


class ValidationWire(
    model_shape(ValidationResult, {"resolved_parameters": tuple[tuple[str, ParameterWire], ...]})
):
    pass


class DiscoveryWire(model_shape(DiscoveryResult, {})):
    pass


class EmptyWire(model_shape(EmptyRequest, {})):
    pass


class PreparationWire(model_shape(PreparationResult, {"prepared": PreparedWire})):
    pass


class QualityWire(model_shape(QualityEvaluation, {})):
    pass
