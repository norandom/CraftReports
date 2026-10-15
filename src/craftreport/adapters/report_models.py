"""Thin asset envelopes borrowing existing immutable declaration contracts."""

from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, JsonValue
from pydantic.json_schema import SkipJsonSchema

from craftreport.adapters.snapshot_models import ParameterWire
from craftreport.adapters.validation import StrictWireModel
from craftreport.contracts.identity import CapabilityRequirement
from craftreport.data.values import ScalarKind
from craftreport.policies.values import ExternalStatement, ReleasePolicy
from craftreport.reporting.definitions import LineChartDefinition, ParameterRef, TableDefinition
from craftreport.themes.values import SemanticRole, StyleProperty


def _present(value: object) -> object:
    if value is None:
        raise ValueError("Present scalar requires a tag")
    return value


def _omit_default(schema: dict[str, JsonValue]) -> None:
    schema.pop("default", None)


type OptionalParameter = Annotated[
    ParameterWire | SkipJsonSchema[None],
    BeforeValidator(_present),
]


class ParameterDeclarationWire(StrictWireModel):
    name: str
    kind: ScalarKind
    required: bool
    default: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default
    )
    choices: tuple[ParameterWire, ...] = ()
    minimum: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default
    )
    maximum: OptionalParameter = Field(
        default=None, validate_default=False, json_schema_extra=_omit_default
    )


class DefinitionWire(StrictWireModel):
    schema_version: Literal["1"]
    report_id: str
    version: str
    title: str | ParameterRef
    parameters: tuple[ParameterDeclarationWire, ...]
    table: TableDefinition
    chart: LineChartDefinition
    release_policy: ReleasePolicy
    compliance_statement: ExternalStatement | None = None


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
