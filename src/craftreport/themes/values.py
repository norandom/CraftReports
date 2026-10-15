"""Immutable semantic presentation values; no target mapping or resolution."""

import json
import math
import re
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_enum, require_immutable, require_unique

type FormatKind = Literal["text", "bool", "int64", "decimal", "date", "datetime"]
type StyleProperty = Literal[
    "font_family", "size_pt", "bold", "italic", "color", "fill", "alignment", "wrap"
]
STYLE_PROPERTIES = frozenset(
    {"font_family", "size_pt", "bold", "italic", "color", "fill", "alignment", "wrap"}
)


class SemanticRole(StrEnum):
    TITLE = "title"
    HEADER = "header"
    ROW_LABEL = "row_label"
    SOURCE = "source"
    INPUT = "input"
    CONSTANT = "constant"
    EXTERNAL_RESULT = "external_result"
    OUTPUT = "output"
    KEY_RESULT = "key_result"
    NOTE = "note"
    CHECK_PASS = "check_pass"
    CHECK_WARN = "check_warn"
    CHECK_FAIL = "check_fail"
    DRAFT = "draft"


def _text(value: str, maximum: int) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty bounded text")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > maximum:
        raise ValueError("Text exceeds serialized UTF-8 limit")


def _color(value: str) -> None:
    if type(value) is not str or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is None:
        raise ValueError("Expected six-digit hex color")


def _number(value: float, maximum: int) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise ValueError("Presentation size must be finite and within bounds")


def _booleans(*values: bool) -> None:
    if any(type(value) is not bool for value in values):
        raise ValueError("Expected boolean presentation flags")


def _version_pin(value: VersionPin) -> None:
    if type(value) is not VersionPin:
        raise ValueError("Expected the shared VersionPin")
    _text(value.identity, 128)
    _text(value.version, 128)


@dataclass(frozen=True, slots=True)
class TextStyle:
    font_family: str
    size_pt: float
    bold: bool
    italic: bool
    color: str
    fill: str | None
    alignment: Literal["left", "center", "right"]
    wrap: bool

    def __post_init__(self) -> None:
        require_immutable(self)
        _text(self.font_family, 128)
        _number(self.size_pt, 144)
        _booleans(self.bold, self.italic, self.wrap)
        _color(self.color)
        if self.fill is not None:
            _color(self.fill)
        if self.alignment not in ("left", "center", "right"):
            raise ValueError("Unsupported text alignment")


@dataclass(frozen=True, slots=True)
class ValueFormat:
    kind: FormatKind
    decimal_places: int | None = None
    date_pattern: str | None = None
    negative_style: Literal["leading_minus"] = "leading_minus"

    def __post_init__(self) -> None:
        require_immutable(self)
        if self.kind not in ("text", "bool", "int64", "decimal", "date", "datetime"):
            raise ValueError("Unsupported format kind")
        if self.negative_style != "leading_minus":
            raise ValueError("Only leading-minus formatting is supported")
        if self.decimal_places is not None and (
            self.kind not in ("int64", "decimal")
            or type(self.decimal_places) is not int
            or not 0 <= self.decimal_places <= 38
        ):
            raise ValueError("Invalid decimal places for format kind")
        if self.date_pattern is not None:
            if self.kind not in ("date", "datetime"):
                raise ValueError("Date pattern requires a date/datetime format")
            _text(self.date_pattern, 128)


@dataclass(frozen=True, slots=True)
class ChartStyle:
    series_colors: tuple[str, ...]
    line_width: float
    legend: bool
    grid: bool

    def __post_init__(self) -> None:
        require_immutable(self.series_colors)
        if type(self.series_colors) is not tuple or not 1 <= len(self.series_colors) <= 32:
            raise ValueError("Chart requires one to 32 immutable series colors")
        for color in self.series_colors:
            _color(color)
        _number(self.line_width, 20)
        _booleans(self.legend, self.grid)


@dataclass(frozen=True, slots=True)
class GridStyle:
    show_gridlines: bool
    header_height: float
    column_width: float

    def __post_init__(self) -> None:
        _booleans(self.show_gridlines)
        _number(self.header_height, 4096)
        _number(self.column_width, 4096)


def _presentation(value: "ResolvedTheme | Theme") -> None:
    require_immutable(value)
    _version_pin(value.version_pin)
    if type(value.styles) is not tuple or len(value.styles) != len(SemanticRole):
        raise ValueError("Theme must style every semantic role exactly once")
    for role, style in value.styles:
        require_enum(role, SemanticRole)
        if type(style) is not TextStyle:
            raise ValueError("Expected TextStyle")
    require_unique(tuple(role for role, _ in value.styles), "semantic roles")
    if type(value.formats) is not tuple or not 1 <= len(value.formats) <= 6:
        raise ValueError("Theme requires one to six formats")
    if any(type(item) is not ValueFormat for item in value.formats):
        raise ValueError("Expected ValueFormat")
    require_unique(tuple(item.kind for item in value.formats), "format kinds")
    if type(value.chart) is not ChartStyle or type(value.grid) is not GridStyle:
        raise ValueError("Expected chart and grid styles")
    _text(value.null_marker, 128)
    _text(value.empty_note, 512)
    # Size validation only; public wire conversion belongs to adapters.
    if len(json.dumps(asdict(value), ensure_ascii=False, separators=(",", ":")).encode()) > 32768:
        raise ValueError("Theme exceeds 32 KiB serialized bound")


@dataclass(frozen=True, slots=True)
class ResolvedTheme:
    version_pin: VersionPin
    styles: tuple[tuple[SemanticRole, TextStyle], ...]
    formats: tuple[ValueFormat, ...]
    chart: ChartStyle
    grid: GridStyle
    null_marker: str = "—"
    empty_note: str = "No data"

    def __post_init__(self) -> None:
        _presentation(self)


@dataclass(frozen=True, slots=True)
class Theme:
    version_pin: VersionPin
    styles: tuple[tuple[SemanticRole, TextStyle], ...]
    formats: tuple[ValueFormat, ...]
    chart: ChartStyle
    grid: GridStyle
    permitted_overrides: tuple[tuple[SemanticRole, StyleProperty], ...] = ()
    null_marker: str = "—"
    empty_note: str = "No data"

    def __post_init__(self) -> None:
        _presentation(self)
        if type(self.permitted_overrides) is not tuple:
            raise ValueError("Expected immutable override declarations")
        require_unique(self.permitted_overrides, "permitted overrides")
        for role, property_name in self.permitted_overrides:
            require_enum(role, SemanticRole)
            if property_name not in STYLE_PROPERTIES:
                raise ValueError("Unsupported role style property")


@dataclass(frozen=True, slots=True)
class StyleOverride:
    role: SemanticRole
    property_name: StyleProperty
    value: str | float | bool | None

    def __post_init__(self) -> None:
        require_immutable(self)
        require_enum(self.role, SemanticRole)
        if self.property_name not in STYLE_PROPERTIES:
            raise ValueError("Unsupported role style property")
        # Reuse the closed style contract to validate only the selected field.
        from dataclasses import replace

        replace(
            TextStyle("Arial", 11, False, False, "#000000", None, "left", True),
            **{self.property_name: self.value},
        )


@dataclass(frozen=True, slots=True)
class PackPin:
    version_pin: VersionPin
    attribution: str
    artifact_visibility_scope: str

    def __post_init__(self) -> None:
        _version_pin(self.version_pin)
        _text(self.attribution, 512)
        _text(self.artifact_visibility_scope, 128)
