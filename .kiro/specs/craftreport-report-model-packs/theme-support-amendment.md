# Theme support descriptor clarification

Accepted for implementation under the bounded overnight authorization.
Independent reviewer `/root/review_theme_support_plan` returned PASS after one
repair, for proposal SHA-256
`DC6323435EC16BA2082F2F3EAA0A4F36CBA99771EF58912BA1452E1D47A56117`.
Implementation still requires independent review and fresh verification.
Requirements 3.1–3.5 and the Design's
ThemeResolution contract remain in force; no dependency, import permission,
capability owner or numeric limit changes.

The accepted source has Theme, ResolvedTheme, StyleOverride and PackPin in
themes.values, but no CapabilityStatus or ThemeFailure. Task 3 will add only the
two missing frozen descriptor/failure values in themes/resolve.py and consume
the accepted values unchanged. ResolvedTheme remains declarative presentation;
it gains no observed-layout, fidelity or release-assurance fields.

The exact service signature is:

```python
type CompatibilityCheck = Callable[[CapabilityVersion, CapabilityRequirement], bool]

def resolve_theme(
    theme: Theme,
    overrides: tuple[StyleOverride, ...],
    support: tuple[CapabilityStatus, ...] | None,
    *,
    is_compatible: CompatibilityCheck | None = None,
) -> ResolvedTheme | ThemeFailure: ...
```

Use contracts.identity's existing CapabilityVersion/CapabilityRequirement and
contracts.pins.VersionPin. CompatibilityCheck is an injected boundary function,
not a version parser: task 7/8 adapter/composition wiring will use the installed
packaging Version/SpecifierSet. Pure themes imports remain contracts and stdlib.
A boundary compatibility callable catches packaging's InvalidVersion (including
malformed version strings) and returns False, which resolution maps to
`incompatible_version`; no parser exception crosses the pure service. Tests must
exercise malformed supplied versions through this real boundary callable.
A supplied descriptor without that checker fails closed. The checker evaluates
each of the three fixed requirements with range `>=1,<2` and the common mode.
No support descriptor needs no checker and returns presentation requirements
without claiming supported mapping or physical fit.

`CapabilityStatus(capability: CapabilityVersion, target_mode: str,
release: VersionPin, profile: VersionPin, status: MappingStatus,
properties: tuple[tuple[SupportProperty, MappingStatus], ...] = ())` is frozen.
MappingStatus is the closed literal `supported | unsupported | untested`.
Capability identity is one of `report.table`, `report.line_chart`,
`report.semantic_style`; no arbitrary capability framework is introduced.
Each descriptor's mode is nonempty opaque text with at most 128 canonical JSON
UTF-8 bytes; release/profile identity/version have the same 128-byte bound and
reuse valid shared digest pins. Capability version is bounded to 128 bytes and
is parsed only by the injected checker. Containers are tuples; property names
and statuses are closed and unique, with at most the following 24 properties:

| Capability | Exact property vocabulary |
| --- | --- |
| report.semantic_style | `text.font_family`, `text.size_pt`, `text.bold`, `text.italic`, `text.color`, `text.fill`, `text.alignment`, `text.wrap`, `format.kind`, `format.decimal_places`, `format.date_pattern`, `format.negative_style`, `grid.show_gridlines`, `grid.header_height`, `grid.column_width` |
| report.line_chart | `chart.series_colors`, `chart.line_width`, `chart.legend`, `chart.grid`, `chart.null_gaps` |
| report.table | `table.typed_null`, `table.null_marker`, `table.empty_headers`, `table.empty_note` |

This explicit vocabulary is the authority. Properties must belong to their
declared capability. All are requested by the resolved theme/mandatory bounded
table-and-chart presentation, except `format.decimal_places` and
`format.date_pattern`, which are requested only when some declared ValueFormat
sets that field. A missing requested property fails closed. A supplied untested
or unsupported requested property fails with its explicit status. Optional
unused properties do not grant support for content added later.

Resolve in declaration order using stdlib dataclasses.replace. Duplicate
role/property overrides fail even when values match. Only Theme's exact
permitted_overrides pairs may change. Return the same theme VersionPin,
formats, chart/grid declarations, null marker and empty note with resolved styles;
PackPin is carried unchanged by later preparation, not transformed by this
service. No input values, units or producer/method metadata enter resolution.
Wrap is an explicit style requirement, retained with all role fields; typed null
plus marker, empty headers/note and chart null gaps are mapping requirements,
not fabricated cells, interpolation or observed effects.

`ThemeFailure(code: ThemeCode, location: tuple[str | int, ...])` is frozen.
ThemeCode is the closed literal `duplicate_override | prohibited_override |
invalid_support | compatibility_unavailable | missing_capability |
incompatible_version | unsupported_mapping | untested_mapping |
missing_property | exceeded_limit`. Locations identify the override index or
capability/property; diagnostics contain no source bodies or runtime paths.
Resolution rejects duplicate/missing capabilities and mixed mode/release/profile
pins before checking each capability and requested property's status/version.
The descriptor only describes a claimed mapping. It cannot supply observed
layout/consistency evidence or qualify a report for validated release, even if
every declaration says supported. Tasks 5 and 8 retain that separation.

Task 7 owns strict wire schemas in adapters/report_models.py and
adapters/report_codecs.py, rejecting unknown/coerced/executable descriptor fields
and preserving these frozen values. Task 8 owns trusted discovery wiring and the
packaging compatibility callable in composition/reporting.py, injected through
preparation into theme resolution. Task 8 operation-level tests must prove
incompatible and untested descriptors reject admission, plus the real callable's
malformed-version-to-incompatible rejection. These checks carry Requirements
3.1, 3.2 and 3.5 through tasks 3, 7 and 8. Caller descriptors cannot manufacture
trusted app evidence. The GridCraft support profile remains bound to its actual
release/mode and separate observation contract.

Task 3 changes only themes/resolve.py and tests/reporting/test_themes.py, plus
ignored task-3 evidence. Forecast 160–220 source LLOC added to the current themes
221 LLOC, within unchanged 50/300/1,500/10 limits. Tests prove full role resolution,
override failures, missing/mixed/duplicate/version/status/property rejection and
no-target pure resolution. They cannot establish app fit or actual fidelity.
