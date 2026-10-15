# Prepared content and resolved pack clarification

Accepted under the owner-directed bounded fast-track after independent PASS by
`/root/review_prepared_content_plan` for proposal SHA-256
`395C8F3A64594AD8817862B122316CFF2B71CC6F9D037002452BDC94AAD73FBD`.
This clarifies task 4's existing preparation seam and the consumers in tasks 6–8.
It adds no capability, executable language, dependency or budget exception.

## Exact first-slice template selection

The Design states that a pack template is exactly one ReportDefinition document.
The accepted task 2.2 `validate_template` verifies that document's report ID,
version and injected canonical digest against a VersionPin. Keep that contract.
The manifest's definition and template references are still explicit references;
neither is silently discarded or treated as permission to substitute content.

Use a frozen `ResolvedPack` in the already approved
`src/craftreport/reporting/prepared.py` with these fields:

- `pin: PackPin`: manifest version, attribution and artifact visibility scope.
- `definition: ReportDefinition`: the validated exact template document.
- `definition_pin: VersionPin`: the manifest's definition reference pin.
- `template: VersionPin`: the manifest's template reference pin.
- `theme: Theme`: the validated selected theme and its own VersionPin.

In this first slice, both document pins must equal each other and their identity
and version must match the definition's report ID and version. The pack loader
must independently check each declared reference's bytes and digest, even when
both references resolve to the same file. A separately versioned structure or a
template with a different report identity is unsupported, rather than silently
collapsed into the definition pin. PreparedReport retains both explicit fields.
This restriction follows the accepted one-document template contract; supporting
two distinct declaration documents requires a later bounded design change.

Task 6 constructs this resolved value only after reference/digest, compatibility,
path and access checks. Task 7 supplies the existing canonical definition codec
identifier to `validate_template`. The pure compiler receives the validated pack;
it compares the requested definition to `pack.definition` and rejects any
different document before projection. It also requires the selected resolved
theme's VersionPin to equal `pack.theme.version_pin`. Resolution may contain
permitted style overrides, whose complete resolved values enter content identity.
The compiler does not reread pack files or introduce another JSON/hash parser.

## Retained table behavior

Append `null_text: str = '—'` and `long_labels: Literal['wrap'] = 'wrap'` to the
reviewed PreparedTable fields. Copy both exactly from TableDefinition. The
table-specific `null_text` is authoritative for that table, including its default;
the theme's null_marker remains a general presentation default and does not
override an explicit table declaration. This avoids losing either selection or
mutating the resolved theme. The retained row value is still None, never the
display marker. Long labels retain their original text and request wrapping.

For an empty projected table, retain all selected column schemas and use
`ResolvedTheme.empty_note` as `PreparedTable.empty_note`; a nonempty table has
`empty_note=None`. Chart null_behavior remains gap and its values stay None.
Task 7 roundtrips these two added table fields; downstream consumers must use
the retained per-table behavior. No physical fit claim follows from these values.

## Projection and failure contract

Keep the Design's prepare signature and injected identifier. It returns either a
complete PreparedReport or a frozen PreparationFailure with fields:

- `code: Literal['invalid_definition', 'invalid_parameter', 'incomplete_binding']`.
- `issues: tuple[DefinitionIssue | BindingIssue, ...]`.

Reuse the existing structured issue types and their tuple locations. Definition
or pack/theme selection mismatches use invalid_definition with an affected
definition/template/theme location and existing template_mismatch issue code.
Parameter-resolution errors use invalid_parameter and preserve their existing
parameter/reference locations. Incompatible repeated input constraints use
invalid_definition. Missing or incompatible snapshot bindings use
incomplete_binding and preserve upstream check_completeness issues verbatim.
These failures contain no partial PreparedReport, raw source values or paths.
Constructor invariant violations remain explicit ValueError/DefinitionError at
the typed construction boundary, consistent with the accepted declarations.

Dataset projection copies selected columns and every row in declaration/source
order. A metric source exposes virtual label/value columns, using a nonnullable
text Field named label and labelled Label. Its virtual value field is the exact
ImportedMetric.value_schema, even if that source schema's name is not value;
selection by value refers to the virtual column, not a renamed producer schema.
Scalar metric labels contain the metric identity; series labels are copied in
order. Metric charts remain series-only and numeric through the authoritative
upstream requirements. Provenance retains the complete original ImportedMetric,
once per identity in first declaration order (table before chart).

## Identity, immutability and consumer obligations

Retain the reviewed PreparedColumn, PreparedSeries, PreparedLineChart and
PreparedReport fields, with the two table additions above. Values are frozen
stdlib dataclasses with recursively immutable nested values. Table row widths
match selected columns and every chart series length matches categories. Reuse
the accepted scalar/field/snapshot and theme/policy contracts; do not create a
parallel validation framework or recast supplied values.

Resolve parameters in declaration order and title only through a literal or
typed ParameterRef. Preserve the complete supplied field schemas, scalar types,
formula-looking strings and provenance. Copy policy/statement and required
capabilities unchanged. Definition, template, theme, pack and snapshot pins plus
resolved parameters and scope remain part of PreparedReport.

As already designed, assemble the report with a private intermediate blank
content_digest, call the injected identifier once, and return a frozen replacement
with its valid SHA-256 digest. The callback uses the existing canonical serializer
and scalar encoders through task 7's explicit prepared codec, excluding only the
content_digest field. The intermediate value is never returned or retained.
Clock, run, operation, target and quality observation values have no fields in
PreparedReport and cannot enter its content hash. No new production fingerprint
implementation is added to reporting.

Task 7 must preserve these explicit pack pins, virtual metric field metadata,
table behavior and typed parameter/category values on wire roundtrip. Task 8
must map typed failures to existing guarded operation diagnostics, never call a
failed preparation complete, and keep trusted quality/target evidence outside
the prepared content identity. Tasks 6–8 retain their existing independent gates.

## Task 4 evidence and size

Own only reporting/prepared.py (one new production module), reporting/prepare.py
and tests/reporting/test_prepare.py. Forecast approximately 220 additional source
LLOC, reporting approximately 559 total from accepted 339, with actual counts
reported before acceptance. Preserve 50 function / 300 module / 1,500 capability
LLOC and McCabe 10; simplify within these seams if the forecast is exceeded.

Run actual flag-off RED, flag-on GREEN and flag-removed checks. Independently
expected fixtures cover two snapshots with one definition, exact ordered values,
metric deduplication, scalar-metric chart rejection, missing/incompatible bindings,
parameters, empty tables/series, formula text, distinct theme presentation and
stable repeated identity. Verify immutable results and clock independence; the
canonical codec integration itself remains task 7's acceptance responsibility.
Use focused pytest plus scoped Ruff/format/Pyright and retain command/exit evidence
under artifacts/report-model-packs/task-4. Root owns ledger/count/task updates and
commits. This proposal does not approve or complete implementation.
