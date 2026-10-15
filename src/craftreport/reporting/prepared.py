"""Frozen target-neutral content and validated pack selections."""

import re
from collections.abc import Callable
from dataclasses import InitVar, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from craftreport.contracts.identity import CapabilityRequirement
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.data.requirements import BindingIssue
from craftreport.data.validation import validate_scalar
from craftreport.data.values import Field, ImportedMetric, Scalar, SnapshotRef
from craftreport.policies.values import ExternalStatement, ReleasePolicy
from craftreport.reporting.definitions import DefinitionIssue, ReportDefinition, require, text
from craftreport.themes.values import PackPin, ResolvedTheme, SemanticRole, Theme, ValueFormat


@dataclass(frozen=True, slots=True)
class ResolvedPack:
    pin: PackPin
    definition: ReportDefinition
    definition_pin: VersionPin
    template: VersionPin
    theme: Theme

    def __post_init__(self) -> None:
        require_immutable(self)
        require(type(self.pin) is PackPin and type(self.theme) is Theme, "invalid_type", ("pack",))
        require(
            type(self.definition) is ReportDefinition
            and type(self.definition_pin) is VersionPin
            and type(self.template) is VersionPin,
            "invalid_type",
            ("template",),
        )
        require(
            self.definition_pin == self.template
            and (self.definition.report_id, self.definition.version)
            == (self.template.identity, self.template.version),
            "template_mismatch",
            ("template",),
        )


@dataclass(frozen=True, slots=True)
class PreparedColumn:
    field: Field
    display_label: str
    role: SemanticRole
    format: ValueFormat

    def __post_init__(self) -> None:
        require_immutable(self)
        require(
            type(self.field) is Field
            and type(self.role) is SemanticRole
            and type(self.format) is ValueFormat,
            "invalid_type",
            ("column",),
        )
        require(type(self.display_label) is str, "invalid_type", ("display_label",))


@dataclass(frozen=True, slots=True)
class PreparedTable:
    identity: str
    columns: tuple[PreparedColumn, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    empty_note: str | None
    null_text: str = "—"
    long_labels: Literal["wrap"] = "wrap"

    def __post_init__(self) -> None:
        require_immutable(self)
        text(self.identity, ("table", "identity"))
        text(self.null_text, ("table", "null_text"))
        require(
            type(self.columns) is tuple
            and bool(self.columns)
            and all(type(c) is PreparedColumn for c in self.columns),
            "invalid_type",
            ("table", "columns"),
        )
        require(type(self.rows) is tuple and self.long_labels == "wrap", "invalid_type", ("table",))
        require(bool(self.rows) == (self.empty_note is None), "invalid_type", ("empty_note",))
        if self.empty_note is not None:
            text(self.empty_note, ("table", "empty_note"), 512)
        for index, row in enumerate(self.rows):
            require(
                type(row) is tuple and len(row) == len(self.columns),
                "invalid_type",
                ("table", "rows", index),
            )
            for column, value in zip(self.columns, row, strict=True):
                validate_scalar(value, column.field, ("table", "rows", index, column.field.name))


@dataclass(frozen=True, slots=True)
class PreparedSeries:
    identity: str
    label: str
    field: Field
    values: tuple[Scalar, ...]
    role: SemanticRole
    format: ValueFormat

    def __post_init__(self) -> None:
        require_immutable(self)
        text(self.identity, ("series", "identity"))
        text(self.label, ("series", "label"), 512)
        require(
            type(self.field) is Field
            and type(self.role) is SemanticRole
            and type(self.format) is ValueFormat
            and type(self.values) is tuple
            and self.field.kind in ("int64", "decimal"),
            "invalid_type",
            ("series",),
        )
        for index, value in enumerate(self.values):
            validate_scalar(value, self.field, ("series", self.identity, index))


@dataclass(frozen=True, slots=True)
class PreparedLineChart:
    identity: str
    category_schema: Field
    categories: tuple[Scalar, ...]
    series: tuple[PreparedSeries, ...]
    null_behavior: Literal["gap"]

    def __post_init__(self) -> None:
        require_immutable(self)
        text(self.identity, ("chart", "identity"))
        require(
            type(self.category_schema) is Field
            and not self.category_schema.nullable
            and self.category_schema.kind in ("text", "date", "datetime", "int64"),
            "invalid_type",
            ("chart", "category_schema"),
        )
        require(
            type(self.categories) is tuple
            and type(self.series) is tuple
            and bool(self.series)
            and self.null_behavior == "gap",
            "invalid_type",
            ("chart",),
        )
        require(
            all(
                type(s) is PreparedSeries and len(s.values) == len(self.categories)
                for s in self.series
            ),
            "invalid_type",
            ("chart", "series"),
        )
        for index, value in enumerate(self.categories):
            validate_scalar(value, self.category_schema, ("chart", "categories", index))


@dataclass(frozen=True, slots=True)
class PreparedReport:
    schema_version: Literal["1"]
    report_id: str
    title: str
    definition: VersionPin
    template: VersionPin
    theme: VersionPin
    pack: PackPin
    snapshot: SnapshotRef
    resolved_parameters: tuple[tuple[str, Scalar], ...]
    tables: tuple[PreparedTable, ...]
    charts: tuple[PreparedLineChart, ...]
    presentation: ResolvedTheme
    required_capabilities: tuple[CapabilityRequirement, ...]
    metric_provenance: tuple[ImportedMetric, ...]
    compliance_statement: ExternalStatement | None
    release_policy: ReleasePolicy
    content_digest: str
    _identify: InitVar[Callable[["PreparedReport"], str] | None] = None

    def __post_init__(self, _identify: Callable[["PreparedReport"], str] | None) -> None:
        require_immutable(self)
        text(self.report_id, ("report_id",))
        text(self.title, ("title",), 512)
        require(self.schema_version == "1" and type(self.content_digest) is str, "invalid_type", ())
        require(
            all(type(pin) is VersionPin for pin in (self.definition, self.template, self.theme))
            and type(self.pack) is PackPin
            and type(self.snapshot) is SnapshotRef
            and type(self.presentation) is ResolvedTheme
            and type(self.release_policy) is ReleasePolicy
            and (
                self.compliance_statement is None
                or type(self.compliance_statement) is ExternalStatement
            ),
            "invalid_type",
            (),
        )
        require(
            self.definition == self.template
            and self.report_id == self.definition.identity
            and self.theme == self.presentation.version_pin,
            "template_mismatch",
            (),
        )
        require(
            type(self.tables) is tuple
            and len(self.tables) == 1
            and type(self.tables[0]) is PreparedTable
            and type(self.charts) is tuple
            and len(self.charts) == 1
            and type(self.charts[0]) is PreparedLineChart,
            "invalid_type",
            ("content",),
        )
        require(
            type(self.required_capabilities) is tuple
            and all(type(c) is CapabilityRequirement for c in self.required_capabilities)
            and type(self.metric_provenance) is tuple
            and all(type(m) is ImportedMetric for m in self.metric_provenance),
            "invalid_type",
            ("provenance",),
        )
        require(
            type(self.resolved_parameters) is tuple
            and all(
                type(pair) is tuple
                and len(pair) == 2
                and type(pair[0]) is str
                and type(pair[1]) in (str, bool, int, Decimal, date, datetime, type(None))
                for pair in self.resolved_parameters
            ),
            "invalid_type",
            ("parameters",),
        )
        require(
            len({name for name, _ in self.resolved_parameters}) == len(self.resolved_parameters)
            and len({m.identity for m in self.metric_provenance}) == len(self.metric_provenance),
            "duplicate",
            ("provenance",),
        )
        if self.content_digest == "" and _identify is not None:
            object.__setattr__(self, "content_digest", _identify(self))
        require(
            type(self.content_digest) is str
            and bool(re.fullmatch("[0-9a-f]{64}", self.content_digest)),
            "invalid_type",
            ("content_digest",),
        )


@dataclass(frozen=True, slots=True)
class PreparationFailure:
    code: Literal["invalid_definition", "invalid_parameter", "incomplete_binding"]
    issues: tuple[DefinitionIssue | BindingIssue, ...]

    def __post_init__(self) -> None:
        require_immutable(self)
        require(
            self.code in ("invalid_definition", "invalid_parameter", "incomplete_binding")
            and type(self.issues) is tuple
            and bool(self.issues)
            and all(type(i) in (DefinitionIssue, BindingIssue) for i in self.issues),
            "invalid_type",
            ("failure",),
        )
