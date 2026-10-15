"""Requirement-derived theme resolution and declarative mapping contracts."""

import subprocess
import sys
from dataclasses import FrozenInstanceError, asdict, replace
from typing import cast

import pytest

from craftreport.contracts.identity import CapabilityRequirement, CapabilityVersion
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.themes.resolve import (
    CapabilityStatus,
    CompatibilityCheck,
    MappingStatus,
    SupportProperty,
    ThemeCode,
    ThemeFailure,
    resolve_theme,
)
from craftreport.themes.values import (
    STYLE_PROPERTIES,
    ChartStyle,
    GridStyle,
    ResolvedTheme,
    SemanticRole,
    StyleOverride,
    StyleProperty,
    TextStyle,
    Theme,
    ValueFormat,
)

PROPERTIES: dict[str, tuple[SupportProperty, ...]] = {
    "report.table": (
        "table.typed_null",
        "table.null_marker",
        "table.empty_headers",
        "table.empty_note",
    ),
    "report.line_chart": (
        "chart.series_colors",
        "chart.line_width",
        "chart.legend",
        "chart.grid",
        "chart.null_gaps",
    ),
    "report.semantic_style": (
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
    ),
}


@pytest.fixture
def theme() -> Theme:
    style = TextStyle("Arial", 11, False, False, "#112233", None, "left", True)
    return Theme(
        VersionPin("public/house", "1.0.0", "a" * 64),
        tuple((role, replace(style, bold=role is SemanticRole.HEADER)) for role in SemanticRole),
        (
            ValueFormat("text"),
            ValueFormat("bool"),
            ValueFormat("int64", 0),
            ValueFormat("decimal", 4),
            ValueFormat("date", date_pattern="yyyy-mm-dd"),
            ValueFormat("datetime", date_pattern="yyyy-mm-dd hh:mm:ss"),
        ),
        ChartStyle(("#112233", "#445566"), 2, True, True),
        GridStyle(False, 24, 18),
        tuple((SemanticRole.INPUT, cast(StyleProperty, name)) for name in sorted(STYLE_PROPERTIES)),
        "missing",
        "No supplied rows",
    )


@pytest.fixture
def support() -> tuple[CapabilityStatus, ...]:
    return tuple(
        CapabilityStatus(
            CapabilityVersion(identity, "1.0.0"),
            "browser",
            VersionPin("gridcraft/web", "0.6.1", "b" * 64),
            VersionPin("public/bounded", "1.0.0", "c" * 64),
            "supported",
            tuple((name, "supported") for name in properties),
        )
        for identity, properties in PROPERTIES.items()
    )


@pytest.fixture
def compatible() -> CompatibilityCheck:
    # Exact fixture answers, not a second version parser.
    return lambda capability, requirement: (
        capability.version == "1.0.0" and requirement.version_range == ">=1,<2"
    )


def test_no_target_resolves_all_roles_and_retains_presentation_only(theme: Theme) -> None:
    before = asdict(theme)
    resolved = resolve_theme(theme, (), None)
    assert isinstance(resolved, ResolvedTheme)
    require_immutable(resolved)
    assert resolved.version_pin is theme.version_pin
    assert resolved.styles == theme.styles
    assert tuple(role for role, _ in resolved.styles) == tuple(SemanticRole)
    assert resolved.formats is theme.formats
    assert resolved.chart is theme.chart and resolved.grid is theme.grid
    assert resolved.null_marker == "missing" and resolved.empty_note == "No supplied rows"
    assert all(style.wrap for _, style in resolved.styles)
    assert all(format.negative_style == "leading_minus" for format in resolved.formats)
    assert asdict(theme) == before


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("font_family", "Calibri"),
        ("size_pt", 14),
        ("bold", True),
        ("italic", True),
        ("color", "#123456"),
        ("fill", "#abcdef"),
        ("alignment", "right"),
        ("wrap", False),
    ],
)
def test_allowlisted_override_changes_only_one_role_property(
    theme: Theme,
    name: StyleProperty,
    value: str | float | bool | None,
) -> None:
    resolved = resolve_theme(theme, (StyleOverride(SemanticRole.INPUT, name, value),), None)
    assert isinstance(resolved, ResolvedTheme)
    expected = tuple(
        (role, replace(style, **{name: value}) if role is SemanticRole.INPUT else style)
        for role, style in theme.styles
    )
    assert resolved.styles == expected
    assert resolved.formats is theme.formats
    assert resolved.version_pin is theme.version_pin
    assert resolved.null_marker == theme.null_marker
    assert dict(theme.styles)[SemanticRole.INPUT] != dict(resolved.styles)[SemanticRole.INPUT]


def test_multiple_overrides_accumulate_and_keep_declaration_order(theme: Theme) -> None:
    theme = replace(theme, styles=tuple(reversed(theme.styles)))
    resolved = resolve_theme(
        theme,
        (
            StyleOverride(SemanticRole.INPUT, "fill", "#123456"),
            StyleOverride(SemanticRole.INPUT, "bold", True),
        ),
        None,
    )
    assert isinstance(resolved, ResolvedTheme)
    assert tuple(role for role, _ in resolved.styles) == tuple(role for role, _ in theme.styles)
    assert dict(resolved.styles)[SemanticRole.INPUT] == replace(
        dict(theme.styles)[SemanticRole.INPUT], fill="#123456", bold=True
    )


def test_none_fill_override_clears_only_the_declared_fill(theme: Theme) -> None:
    selected = replace(
        theme, styles=tuple((role, replace(style, fill="#abcdef")) for role, style in theme.styles)
    )
    resolved = resolve_theme(selected, (StyleOverride(SemanticRole.INPUT, "fill", None),), None)
    assert isinstance(resolved, ResolvedTheme)
    assert dict(resolved.styles)[SemanticRole.INPUT].fill is None
    assert dict(resolved.styles)[SemanticRole.EXTERNAL_RESULT].fill == "#abcdef"


@pytest.mark.parametrize("second", ["#123456", "#654321"])
def test_duplicate_override_rejects_identical_and_conflicting_values(
    theme: Theme,
    second: str,
) -> None:
    assert resolve_theme(
        theme,
        (
            StyleOverride(SemanticRole.INPUT, "color", "#123456"),
            StyleOverride(SemanticRole.INPUT, "color", second),
        ),
        None,
    ) == ThemeFailure("duplicate_override", ("overrides", 1))


def test_prohibited_override_reports_index_before_target_use(theme: Theme) -> None:
    assert resolve_theme(
        theme,
        (StyleOverride(SemanticRole.OUTPUT, "bold", True),),
        None,
    ) == ThemeFailure("prohibited_override", ("overrides", 0))


def test_compatibility_checker_receives_existing_contracts_and_common_mode(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
) -> None:
    calls: list[tuple[CapabilityVersion, CapabilityRequirement]] = []

    def check(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
        calls.append((version, requirement))
        return True

    resolved = resolve_theme(theme, (), support, is_compatible=check)
    assert isinstance(resolved, ResolvedTheme)
    assert calls == [
        (item.capability, CapabilityRequirement(item.capability.identity, ">=1,<2", "browser"))
        for item in support
    ]
    # A descriptive profile never adds an observed fit/fidelity result to presentation.
    assert resolved == resolve_theme(theme, (), None)


def test_supplied_support_requires_boundary_compatibility_checker(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
) -> None:
    assert resolve_theme(theme, (), support) == ThemeFailure(
        "compatibility_unavailable", ("support",)
    )


@pytest.mark.parametrize("version", ["2.0.0", "0.9", "malformed!", "1.0rc1"])
def test_incompatible_boundary_answer_is_not_parsed_or_ignored(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    version: str,
) -> None:
    changed = replace(support[0], capability=CapabilityVersion("report.table", version))
    seen: list[str] = []

    def reject(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
        seen.append(version.version)
        return False

    assert resolve_theme(theme, (), (changed, *support[1:]), is_compatible=reject) == ThemeFailure(
        "incompatible_version", ("support", "report.table")
    )
    assert seen == [version]


@pytest.mark.parametrize("missing", ["report.table", "report.line_chart", "report.semantic_style"])
def test_missing_required_capability_is_not_optional(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
    missing: str,
) -> None:
    selected = tuple(item for item in support if item.capability.identity != missing)
    assert resolve_theme(theme, (), selected, is_compatible=compatible) == ThemeFailure(
        "missing_capability", ("support", missing)
    )


def test_duplicate_capability_rejects_even_if_identical(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
) -> None:
    assert resolve_theme(
        theme, (), (*support, support[0]), is_compatible=compatible
    ) == ThemeFailure("invalid_support", ("support", 3))


@pytest.mark.parametrize("field", ["target_mode", "release", "profile"])
def test_mixed_mode_release_or_profile_rejects_before_compatibility(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    field: str,
) -> None:
    value = "native" if field == "target_mode" else VersionPin("different", "1", "d" * 64)
    changed = (support[0], replace(support[1], **{field: value}), support[2])

    def unexpected(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
        pytest.fail("Mixed descriptors must reject before compatibility checks")

    assert resolve_theme(theme, (), changed, is_compatible=unexpected) == ThemeFailure(
        "invalid_support", ("support", 1)
    )


@pytest.mark.parametrize("field", ["release", "profile"])
def test_matching_identity_and_version_cannot_hide_mixed_content_pins(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
    field: str,
) -> None:
    pin = support[1].release if field == "release" else support[1].profile
    changed = (
        support[0],
        replace(support[1], **{field: replace(pin, content_digest="f" * 64)}),
        support[2],
    )
    assert resolve_theme(theme, (), changed, is_compatible=compatible) == ThemeFailure(
        "invalid_support", ("support", 1)
    )


@pytest.mark.parametrize("index", [0, 1, 2])
@pytest.mark.parametrize("status", ["unsupported", "untested"])
def test_each_required_capability_preserves_explicit_failed_mapping_status(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
    index: int,
    status: MappingStatus,
) -> None:
    changed = tuple(
        replace(item, status=status) if n == index else item for n, item in enumerate(support)
    )
    assert resolve_theme(theme, (), changed, is_compatible=compatible) == ThemeFailure(
        cast(ThemeCode, f"{status}_mapping"), ("support", support[index].capability.identity)
    )


@pytest.mark.parametrize(
    "identity,property_name",
    [(identity, name) for identity, properties in PROPERTIES.items() for name in properties],
)
@pytest.mark.parametrize("status", ["unsupported", "untested", "missing"])
def test_each_requested_style_format_grid_and_content_property_is_checked(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
    identity: str,
    property_name: SupportProperty,
    status: str,
) -> None:
    changed = tuple(
        replace(
            item,
            properties=tuple(
                (name, cast(MappingStatus, status) if name == property_name else state)
                for name, state in item.properties
                if name != property_name or status != "missing"
            ),
        )
        if item.capability.identity == identity
        else item
        for item in support
    )
    code = "missing_property" if status == "missing" else f"{status}_mapping"
    assert resolve_theme(theme, (), changed, is_compatible=compatible) == ThemeFailure(
        cast(ThemeCode, code), ("support", identity, property_name)
    )


def test_unused_optional_format_fields_need_no_mapping_until_requested(
    theme: Theme,
    support: tuple[CapabilityStatus, ...],
    compatible: CompatibilityCheck,
) -> None:
    selected = replace(theme, formats=(ValueFormat("text"),))
    changed = tuple(
        replace(
            item,
            properties=tuple(
                (name, state)
                for name, state in item.properties
                if name not in ("format.decimal_places", "format.date_pattern")
            ),
        )
        for item in support
    )
    assert isinstance(resolve_theme(selected, (), changed, is_compatible=compatible), ResolvedTheme)
    decimal = replace(selected, formats=(ValueFormat("decimal", 4),))
    assert resolve_theme(decimal, (), changed, is_compatible=compatible) == ThemeFailure(
        "missing_property", ("support", "report.semantic_style", "format.decimal_places")
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "passed"},
        {"target_mode": ""},
        {"target_mode": "界" * 128},
        {"capability": CapabilityVersion("arbitrary.plugin", "1")},
        {"capability": CapabilityVersion("report.table", "x" * 129)},
        {"release": VersionPin("x" * 129, "1", "a" * 64)},
        {"profile": VersionPin("profile", "x" * 129, "a" * 64)},
        {"properties": (("text.css", "supported"),)},
        {"properties": (("text.bold", "supported"),)},
        {"properties": (("table.typed_null", "passed"),)},
        {"properties": (("table.typed_null", "supported"),) * 2},
        {"properties": [("table.typed_null", "supported")]},
    ],
)
def test_descriptor_is_closed_bounded_and_capability_specific(
    support: tuple[CapabilityStatus, ...],
    changes: dict[str, object],
) -> None:
    with pytest.raises((ValueError, TypeError)):
        replace(support[0], **changes)


def test_support_failure_values_are_recursively_frozen(
    support: tuple[CapabilityStatus, ...],
) -> None:
    require_immutable(support)
    failure = ThemeFailure("unsupported_mapping", ("support", "report.table"))
    require_immutable(failure)
    with pytest.raises(FrozenInstanceError):
        setattr(support[0], "target_mode", "native")
    with pytest.raises(FrozenInstanceError):
        setattr(failure, "code", "untested_mapping")


def test_no_target_does_not_call_compatibility(theme: Theme) -> None:
    def unexpected(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
        pytest.fail("No target must not invoke compatibility")

    assert isinstance(resolve_theme(theme, (), None, is_compatible=unexpected), ResolvedTheme)


def test_resolver_has_no_parser_app_runtime_or_reporting_imports() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import craftreport.themes.resolve; "
            "assert not any(name.startswith(('packaging', 'craftreport.reporting', "
            "'craftreport.runtime', 'craftreport.adapters', 'pydantic', 'fastapi')) "
            "for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
