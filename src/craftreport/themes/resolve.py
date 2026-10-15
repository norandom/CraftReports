"""Pure presentation resolution; support declarations are never app evidence."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast, get_args

from craftreport.contracts.identity import CapabilityRequirement, CapabilityVersion
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable, require_unique
from craftreport.themes.values import ResolvedTheme, StyleOverride, Theme

type MappingStatus = Literal["supported", "unsupported", "untested"]
type SupportProperty = Literal[
    "text.font_family",
    "text.size_pt",
    "text.bold",
    "text.italic",
    "text.color",
    "text.fill",
    "text.alignment",
    "text.wrap",
    "format.kind",
    "format.decimal_places",
    "format.date_pattern",
    "format.negative_style",
    "grid.show_gridlines",
    "grid.header_height",
    "grid.column_width",
    "chart.series_colors",
    "chart.line_width",
    "chart.legend",
    "chart.grid",
    "chart.null_gaps",
    "table.typed_null",
    "table.null_marker",
    "table.empty_headers",
    "table.empty_note",
]
type ThemeCode = Literal[
    "duplicate_override",
    "prohibited_override",
    "invalid_support",
    "compatibility_unavailable",
    "missing_capability",
    "incompatible_version",
    "unsupported_mapping",
    "untested_mapping",
    "missing_property",
    "exceeded_limit",
]
type CompatibilityCheck = Callable[[CapabilityVersion, CapabilityRequirement], bool]

_PROPERTY_NAMES = cast(tuple[SupportProperty, ...], get_args(SupportProperty.__value__))
_PREFIXES = {
    "report.table": ("table",),
    "report.line_chart": ("chart",),
    "report.semantic_style": ("text", "format", "grid"),
}
_STATUSES = ("supported", "unsupported", "untested")


def _text(value: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty support text")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > 128:
        raise ValueError("Support text exceeds serialized UTF-8 bound")


def _properties(identity: str) -> tuple[SupportProperty, ...]:
    return tuple(name for name in _PROPERTY_NAMES if name.split(".")[0] in _PREFIXES[identity])


@dataclass(frozen=True, slots=True)
class CapabilityStatus:
    capability: CapabilityVersion
    target_mode: str
    release: VersionPin
    profile: VersionPin
    status: MappingStatus
    properties: tuple[tuple[SupportProperty, MappingStatus], ...] = ()

    def __post_init__(self) -> None:
        require_immutable(self)
        if (
            type(self.capability) is not CapabilityVersion
            or self.capability.identity not in _PREFIXES
        ):
            raise ValueError("Expected a bounded report capability")
        _text(self.capability.version)
        _text(self.target_mode)
        for pin in (self.release, self.profile):
            if type(pin) is not VersionPin:
                raise ValueError("Expected shared release/profile VersionPin")
            _text(pin.identity)
            _text(pin.version)
        if self.status not in _STATUSES:
            raise ValueError("Unknown mapping status")
        if type(self.properties) is not tuple or len(self.properties) > len(_PROPERTY_NAMES):
            raise ValueError("Expected bounded immutable property declarations")
        allowed = _properties(self.capability.identity)
        for pair in self.properties:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("Expected property/status pair")
            name, status = pair
            if name not in allowed or status not in _STATUSES:
                raise ValueError("Unknown property or mapping status for capability")
        require_unique(tuple(name for name, _ in self.properties), "support properties")


@dataclass(frozen=True, slots=True)
class ThemeFailure:
    code: ThemeCode
    location: tuple[str | int, ...]

    def __post_init__(self) -> None:
        require_immutable(self)
        if self.code not in get_args(ThemeCode.__value__):
            raise ValueError("Unknown theme failure code")
        if type(self.location) is not tuple or not 1 <= len(self.location) <= 3:
            raise ValueError("Expected bounded failure location")
        for part in self.location:
            if type(part) is str:
                _text(part)
            elif type(part) is not int or part < 0:
                raise ValueError("Expected text or nonnegative location index")


def validate_support(support: tuple[CapabilityStatus, ...]) -> ThemeFailure | None:
    if type(support) is not tuple:
        return ThemeFailure("invalid_support", ("support",))
    seen: set[str] = set()
    for index, item in enumerate(support):
        if type(item) is not CapabilityStatus or item.capability.identity in seen:
            return ThemeFailure("invalid_support", ("support", index))
        first = support[0]
        if (item.target_mode, item.release, item.profile) != (
            first.target_mode,
            first.release,
            first.profile,
        ):
            return ThemeFailure("invalid_support", ("support", index))
        seen.add(item.capability.identity)
    for identity in _PREFIXES:
        if identity not in seen:
            return ThemeFailure("missing_capability", ("support", identity))
    return None


def _mapping_failure(status: MappingStatus, location: tuple[str | int, ...]) -> ThemeFailure | None:
    if status == "unsupported":
        return ThemeFailure("unsupported_mapping", location)
    if status == "untested":
        return ThemeFailure("untested_mapping", location)
    return None


def _support_failure(
    theme: Theme, support: tuple[CapabilityStatus, ...], is_compatible: CompatibilityCheck | None
) -> ThemeFailure | None:
    shape = validate_support(support)
    if shape is not None:
        return shape
    if is_compatible is None:
        return ThemeFailure("compatibility_unavailable", ("support",))
    optional = {
        "format.decimal_places": any(value.decimal_places is not None for value in theme.formats),
        "format.date_pattern": any(value.date_pattern is not None for value in theme.formats),
    }
    for item in support:
        identity = item.capability.identity
        location = ("support", identity)
        if failure := _mapping_failure(item.status, location):
            return failure
        requirement = CapabilityRequirement(identity, ">=1,<2", item.target_mode)
        if is_compatible(item.capability, requirement) is not True:
            return ThemeFailure("incompatible_version", location)
        properties = dict(item.properties)
        for name in _properties(identity):
            if not optional.get(name, True):
                continue
            if name not in properties:
                return ThemeFailure("missing_property", (*location, name))
            if failure := _mapping_failure(properties[name], (*location, name)):
                return failure
    return None


def resolve_theme(
    theme: Theme,
    overrides: tuple[StyleOverride, ...],
    support: tuple[CapabilityStatus, ...] | None,
    *,
    is_compatible: CompatibilityCheck | None = None,
) -> ResolvedTheme | ThemeFailure:
    if type(theme) is not Theme or type(overrides) is not tuple:
        raise ValueError("Expected a theme and immutable override declarations")
    styles = dict(theme.styles)
    seen: set[tuple[object, str]] = set()
    for index, override in enumerate(overrides):
        if type(override) is not StyleOverride:
            raise ValueError("Expected StyleOverride")
        key = (override.role, override.property_name)
        if key in seen:
            return ThemeFailure("duplicate_override", ("overrides", index))
        if key not in theme.permitted_overrides:
            return ThemeFailure("prohibited_override", ("overrides", index))
        seen.add(key)
        styles[override.role] = replace(
            styles[override.role], **{override.property_name: override.value}
        )
    if support is not None and (failure := _support_failure(theme, support, is_compatible)):
        return failure
    try:
        return ResolvedTheme(
            theme.version_pin,
            tuple(styles.items()),
            theme.formats,
            theme.chart,
            theme.grid,
            theme.null_marker,
            theme.empty_note,
        )
    except ValueError:
        return ThemeFailure("exceeded_limit", ("theme",))
