"""Frozen declarations for the bounded table and line-chart workflow."""

from __future__ import annotations

import json
import operator
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, get_args

from craftreport.contracts.identity import CapabilityRequirement
from craftreport.contracts.values import require_immutable
from craftreport.data.requirements import FieldRequirement, MetricRequirement
from craftreport.data.values import Scalar, ScalarKind
from craftreport.policies.values import ExternalStatement, ReleasePolicy
from craftreport.themes.values import SemanticRole, ValueFormat

type Location = tuple[str | int, ...]
type DefinitionCode = Literal[
    "invalid_type",
    "required",
    "range",
    "choice",
    "reference",
    "duplicate",
    "unsupported",
    "limit",
    "template_mismatch",
    "constraint_conflict",
]
type EmptyBehavior = Literal["headers_and_note"]


@dataclass(frozen=True, slots=True)
class DefinitionIssue:
    location: Location
    code: DefinitionCode


class DefinitionError(ValueError):
    def __init__(self, code: DefinitionCode, location: Location) -> None:
        self.issue = DefinitionIssue(location, code)
        super().__init__(f"{code} at {location}")


def require(condition: bool, code: DefinitionCode, location: Location) -> None:
    if not condition:
        raise DefinitionError(code, location)


def text(value: object, location: Location, maximum: int = 128, *, empty: bool = False) -> None:
    require(type(value) is str and (empty or bool(value.strip())), "invalid_type", location)
    require(len(json.dumps(value, ensure_ascii=False).encode()) <= maximum, "limit", location)


def frozen(value: object, location: Location) -> None:
    try:
        require_immutable(value)
    except TypeError:
        raise DefinitionError("invalid_type", location) from None


@dataclass(frozen=True, slots=True)
class ParameterRef:
    name: str

    def __post_init__(self) -> None:
        text(self.name, ("reference",))


@dataclass(frozen=True, slots=True)
class ParameterValue:
    name: str
    value: Scalar

    def __post_init__(self) -> None:
        text(self.name, ("parameters",))
        frozen(self.value, ("parameters", self.name))


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    name: str
    kind: ScalarKind
    required: bool
    default: Scalar = None
    choices: tuple[Scalar, ...] = ()
    minimum: Scalar = None
    maximum: Scalar = None

    def __post_init__(self) -> None:
        location = ("parameters", self.name)
        frozen(self, location)
        text(self.name, location)
        require(
            type(self.kind) is str and self.kind in get_args(ScalarKind.__value__),
            "invalid_type",
            location,
        )
        require(
            type(self.required) is bool and type(self.choices) is tuple, "invalid_type", location
        )
        require(
            self.minimum is None
            and self.maximum is None
            or self.kind in ("int64", "decimal", "date", "datetime"),
            "range",
            location,
        )
        for value in (self.minimum, self.maximum):
            if value is not None:
                check_parameter(self, value, bounds=False)
        if self.minimum is not None and self.maximum is not None:
            require(not operator.gt(self.minimum, self.maximum), "range", location)
        for value in (*self.choices, *((self.default,) if self.default is not None else ())):
            check_parameter(self, value)


def check_parameter(
    parameter: ParameterDefinition, value: Scalar, *, bounds: bool = True
) -> Scalar:
    location = ("parameters", parameter.name)
    expected = {
        "text": str,
        "bool": bool,
        "int64": int,
        "decimal": Decimal,
        "date": date,
        "datetime": datetime,
    }
    require(type(value) is expected[parameter.kind], "invalid_type", location)
    assert value is not None
    if type(value) is str:
        text(value, location, 512, empty=True)
    if type(value) is int:
        require(-(2**63) <= value < 2**63, "range", location)
    if type(value) is Decimal:
        require(value.is_finite(), "range", location)
    if type(value) is datetime:
        require(value.utcoffset() is not None, "invalid_type", location)
    if bounds:
        require(
            parameter.minimum is None or not operator.lt(value, parameter.minimum),
            "range",
            location,
        )
        require(
            parameter.maximum is None or not operator.gt(value, parameter.maximum),
            "range",
            location,
        )
        require(not parameter.choices or value in parameter.choices, "choice", location)
    return value


def source_name(value: str | ParameterRef, location: Location) -> None:
    if type(value) is not ParameterRef:
        text(value, location)


@dataclass(frozen=True, slots=True)
class DatasetRef:
    name: str | ParameterRef
    fields: tuple[FieldRequirement, ...]

    def __post_init__(self) -> None:
        frozen(self, ("source",))
        source_name(self.name, ("source", "name"))
        require(
            type(self.fields) is tuple and 1 <= len(self.fields) <= 64,
            "limit",
            ("source", "fields"),
        )
        require(
            all(type(field) is FieldRequirement for field in self.fields),
            "invalid_type",
            ("source", "fields"),
        )
        names = tuple(field.name for field in self.fields)
        require(len(set(names)) == len(names), "duplicate", ("source", "fields"))
        for name in names:
            text(name, ("source", "fields"))


@dataclass(frozen=True, slots=True)
class MetricRef:
    identity: str | ParameterRef
    unit: str | None = None
    kinds: tuple[ScalarKind, ...] = ()
    shape: Literal["scalar", "series"] | None = None
    nullable: bool = True

    def __post_init__(self) -> None:
        frozen(self, ("source",))
        source_name(self.identity, ("source", "identity"))
        try:
            MetricRequirement("declared", self.unit, self.kinds, self.shape, self.nullable)
        except ValueError:
            raise DefinitionError("invalid_type", ("source",)) from None


def selection(value: ColumnSelection | SeriesSelection) -> None:
    text(value.field, ("field",))
    require(
        type(value.role) is SemanticRole and type(value.format) is ValueFormat,
        "invalid_type",
        ("format",),
    )
    label = value.display_label if isinstance(value, ColumnSelection) else value.label
    if label is not None:
        text(label, ("label",), 512)
    require(
        len(json.dumps(asdict(value), ensure_ascii=False, separators=(",", ":")).encode()) <= 1024,
        "limit",
        ("format",),
    )


@dataclass(frozen=True, slots=True)
class ColumnSelection:
    field: str
    role: SemanticRole
    format: ValueFormat
    display_label: str | None = None

    def __post_init__(self) -> None:
        selection(self)


@dataclass(frozen=True, slots=True)
class SeriesSelection:
    identity: str
    label: str
    field: str
    role: SemanticRole
    format: ValueFormat

    def __post_init__(self) -> None:
        text(self.identity, ("series", "identity"))
        selection(self)


def projection(source: DatasetRef | MetricRef, fields: tuple[str, ...], location: Location) -> None:
    require(type(source) in (DatasetRef, MetricRef), "unsupported", (*location, "source"))
    require(1 <= len(fields) <= 64, "limit", location)
    require(len(set(fields)) == len(fields), "duplicate", location)
    names = (
        tuple(field.name for field in source.fields)
        if isinstance(source, DatasetRef)
        else ("label", "value")
    )
    require(all(field in names for field in fields), "reference", location)


@dataclass(frozen=True, slots=True)
class TableDefinition:
    identity: str
    source: DatasetRef | MetricRef
    columns: tuple[ColumnSelection, ...]
    empty_behavior: EmptyBehavior = "headers_and_note"
    null_text: str = "—"
    long_labels: Literal["wrap"] = "wrap"

    def __post_init__(self) -> None:
        frozen(self, ("table",))
        text(self.identity, ("table", "identity"))
        text(self.null_text, ("table", "null_text"), 128)
        require(
            type(self.columns) is tuple and all(type(c) is ColumnSelection for c in self.columns),
            "invalid_type",
            ("table", "columns"),
        )
        require(
            self.empty_behavior == "headers_and_note" and self.long_labels == "wrap",
            "unsupported",
            ("table",),
        )
        projection(self.source, tuple(c.field for c in self.columns), ("table", "columns"))


@dataclass(frozen=True, slots=True)
class LineChartDefinition:
    identity: str
    source: DatasetRef | MetricRef
    category_field: str
    series: tuple[SeriesSelection, ...]
    null_behavior: Literal["gap"] = "gap"

    def __post_init__(self) -> None:
        frozen(self, ("chart",))
        text(self.identity, ("chart", "identity"))
        require(
            type(self.series) is tuple and all(type(s) is SeriesSelection for s in self.series),
            "invalid_type",
            ("chart", "series"),
        )
        projection(
            self.source, (self.category_field, *(s.field for s in self.series)), ("chart", "series")
        )
        require(
            bool(self.series) and len({s.identity for s in self.series}) == len(self.series),
            "duplicate",
            ("chart", "series"),
        )
        require(self.null_behavior == "gap", "unsupported", ("chart", "null_behavior"))
        if isinstance(self.source, DatasetRef):
            fields = {field.name: field for field in self.source.fields}
            category = fields[self.category_field]
            require(
                not category.nullable and category.kind in ("text", "date", "datetime", "int64"),
                "invalid_type",
                ("chart", "category_field"),
            )
            require(
                all(fields[s.field].kind in ("int64", "decimal") for s in self.series),
                "invalid_type",
                ("chart", "series"),
            )
        else:
            require(
                self.category_field == "label"
                and self.source.shape == "series"
                and bool(self.source.kinds)
                and all(k in ("int64", "decimal") for k in self.source.kinds),
                "invalid_type",
                ("chart", "source"),
            )


@dataclass(frozen=True, slots=True)
class ReportDefinition:
    schema_version: Literal["1"]
    report_id: str
    version: str
    title: str | ParameterRef
    parameters: tuple[ParameterDefinition, ...]
    table: TableDefinition
    chart: LineChartDefinition
    release_policy: ReleasePolicy
    compliance_statement: ExternalStatement | None = None

    def __post_init__(self) -> None:
        frozen(self, ())
        text(self.report_id, ("report_id",))
        text(self.version, ("version",))
        require(self.schema_version == "1", "unsupported", ("schema_version",))
        require(
            type(self.table) is TableDefinition and type(self.chart) is LineChartDefinition,
            "unsupported",
            (),
        )
        require(
            type(self.release_policy) is ReleasePolicy
            and (
                self.compliance_statement is None
                or type(self.compliance_statement) is ExternalStatement
            ),
            "invalid_type",
            ("release_policy",),
        )
        require(
            type(self.parameters) is tuple
            and len(self.parameters) <= 16
            and all(type(p) is ParameterDefinition for p in self.parameters),
            "limit",
            ("parameters",),
        )
        parameters = {p.name: p for p in self.parameters}
        require(len(parameters) == len(self.parameters), "duplicate", ("parameters",))
        require(
            len(self.table.columns) + len(self.chart.series) + 1 <= 64, "limit", ("selections",)
        )
        sources = (self.table.source, self.chart.source)
        references = (
            (self.title, ("title",)),
            *(
                (s.name if isinstance(s, DatasetRef) else s.identity, (name, "source"))
                for name, s in zip(("table", "chart"), sources)
            ),
        )
        for value, location in references:
            if type(value) is ParameterRef:
                require(
                    value.name in parameters and parameters[value.name].kind == "text",
                    "reference",
                    location,
                )
            else:
                text(value, location, 512 if location == ("title",) else 128)

    @property
    def required_capabilities(self) -> tuple[CapabilityRequirement, ...]:
        return tuple(
            CapabilityRequirement(name, ">=1,<2")
            for name in (
                "report.table",
                "report.line_chart",
                "report.semantic_style",
            )
        )
