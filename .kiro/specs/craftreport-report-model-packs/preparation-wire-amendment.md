# Preparation wire reuse amendment — proposal

Status: proposal only, not implementation approval. Task 6 was accepted and
pushed as 53a78a3. No production or test source changes accompany this proposal.
The whole adapters-owner forecast remains uncertain. A bounded task-7 implementation
may proceed after independent contract review and root GO, with actual approved
limits enforced and the complete residual forecast retained. Root owns phase/task
integration; this does not authorize subsequent tasks or establish their fit.

## Observed gaps and selected library seam

The existing PydanticCodec uses strict Python model_validate. That rejects JSON
arrays/enums for borrowed stdlib dataclasses. Its numeric traversal also cannot
read dataclass members. Conversely, direct TypeAdapter(PreparedReport) cannot
publish a schema: its private callable InitVar produces CallableSchema failure.
Its Scalar unions also cannot preserve the required public scalar distinctions.

Use installed Pydantic 2.14.1 create_model to derive **fixed, feature-owned**
wire shapes from dataclasses.fields/get_type_hints. Override only fields whose
wire representation differs. This replaces copied prepared metadata fields;
it does not add a public model registry, recursive schema language, plugin
loader, arbitrary class selection or generic codec framework. All classes and
override names are literals in the adapter source. Existing constructors remain
the semantic validators and must run once when producing each inward value.

The small private field-projection helper preserves each authoritative field's
required/default state, including when overriding its annotation. fields excludes
InitVars: _identify never becomes a public field. Prepared content projection
also omits content_digest; its final-result subtype adds the required lowercase
SHA-256 field. Unknown _identify or content digest fields in the content-only
shape fail through extra=forbid, rather than accepting an unused callback.

The corresponding constructor helper takes a validated StrictWireModel, copies
the exact original dataclass field names and replaces the explicitly decoded
scalar-bearing fields before calling the original dataclass constructor. It
does not construct business values from unvalidated JSON, skip constructors or
retain Pydantic models. Its result is typed by the supplied original dataclass.
No Any type enters the public request/result contracts. The probe's sole library
call cast fixes create_model's dynamic keyword overload while __base__ remains
the literal StrictWireModel; it does not cast an input body to a business value.

## Narrow shared-codec change requiring explicit review

Add an opt-in JSON mode to existing adapters/validation.py PydanticCodec, default
False. Default Python validation, normalization, alias rules, numerical-kind
rules and schemas remain unchanged for existing clients.

For the opt-in mode, bounded canonical JSON is passed to model_validate_json with
strict=True, extra=forbid and the existing alias restrictions. Serialization uses
model_dump(mode='json') before the existing bounded/frozen result path. Retain
the numeric walker: extend its member lookup to validated dataclasses, and in
this mode permit only exact Python int to float normalization. Boolean-to-number,
text-to-number and float-to-int remain forbidden. All report float fields are
bounded presentation sizes or validated presentation override values; supplied
business numbers remain string payloads in the existing exact scalar wire.

Strict JSON mode itself rejects boolean/text sizes. The existing TextStyle,
ChartStyle, GridStyle and StyleOverride constructors enforce their field-specific
bounds, flags and property/type agreement. This matches accepted task-6 integer
presentation behavior rather than introducing a stricter report API.

For JSON-mode schemas, reuse task 6's recursive object-closure projection. Move
that small projection to the shared validation boundary and let asset_schema
reuse it; no owner changes and no second validator are introduced. Existing
default-mode schemas must remain byte-equivalent. No application, transport or
kernel admission code changes are proposed.

Apply field-local exclude_if omission to ParameterDeclarationWire's three absent
default/minimum/maximum sentinels. Actual model_dump(mode='json') otherwise emits
raw null values that those fields deliberately reject. Global exclude_none is
incorrect because CheckScope and other contracts have required nullable fields.
An installed-library probe proves field-local omission and revalidation. Existing
encode_definition already omits these fields; its exact bytes, identity and
published schemas must remain unchanged. This is an explicit task-6 compatibility
extension, not a new nullable-parameter rule.

## Concrete existing-schema reuse, including upstream task 2.3

The proposed shared projection helper also replaces the existing FieldWire,
DatasetWire and MetricWire metadata declarations in snapshot_models.py, plus
DefinitionWire in report_models.py. This explicitly reopens the **boundary schema
implementation** of accepted upstream task 2.3 for a compatibility refactor.
It does not change upstream domain contracts, publication behavior or scalar
conversion. The same fixed helper lives in existing validation.py and is used by
both report and snapshot models; it is not duplicated or moved to another owner.

The upstream wire differences must be explicit overrides, not dataclass default
inference: retain the existing Text aliases, list containers for dataset fields,
rows, keys, metric labels/values/evidence, string as_of, FieldWire precision1–38
and scale0–38, source_version default None, and period/as_of defaults None.
Those three defaults are intentionally different from required inward dataclass
constructor fields. The helper therefore supports a small fixed default-override
mapping in addition to annotation overrides, preserving every other required and
default field. DefinitionWire overrides only tagged parameter declarations.

The actual ignored upstream_reuse_probe.py generated all four replacements.
For each, the entire published model_json_schema dictionary equals the existing
dictionary exactly. Actual input/default/list normalization also matches and
invalid precision/scale/boolean/extra cases reject. Pyright strict passes the
candidate together with the typed shared derivation and complete operation
shape probes. upstream-reuse-experiment.log and all-typed-probes-pyright.log retain
the actual outputs. These probes do not replace full upstream codec regressions.

Measured original/new class LLOC is FieldWire15/2, DatasetWire17/2,
MetricWire25/2 and DefinitionWire19/2: 68 gross lines removed in the **same**
adapters capability. The shared helper is already included in the proposed new
work; reserve six additional lines for explicit default handling, field-local
omission and import costs rather than counting the entire gross saving. Use
62 as the conservative net candidate saving until actual production measurement.
Production implementation must retain old schema/normalization fixtures,
exercise public publication/read/parameter behavior and run accepted snapshot2.3
tests before accepting this refactor. No list/tuple, required/default, alias,
unknown-field or precision behavior may change to obtain the saving.

## Pure API values brought forward from task 8

The approved API's request/result values do not yet exist. Bring forward only
these frozen, slotted values into already-owned reporting/ports.py, with recursive
immutability checks. They contain no boundary models or concrete services:

| Value | Exact fields |
| --- | --- |
| EmptyRequest | none |
| ValidateRequest | pack: PackSelection; definition: ReportDefinition or None = None; parameters: tuple[ParameterValue,...] = (); overrides: tuple[StyleOverride,...] = (); target_support: tuple[CapabilityStatus,...] or None = None |
| PrepareRequest | ValidateRequest fields, required SnapshotRef snapshot, requested_designation draft/validated default draft; keyword-only construction avoids inherited default ordering ambiguity |
| ValidationResult | InputRequirements requirements; resolved parameter pairs in declaration order; definition/template/theme VersionPins; PackPin pack; required_capabilities tuple |
| DiscoveryResult | tuple[PackSummary,...] packs |
| PreparationResult | PreparedReport prepared; QualityEvaluation quality |

The selected immutable pack owns the exact template and theme. A request cannot
select another theme body, path, source root or ambient version. Optional supplied
definition content must match that pack's template; omitted definition uses that
exact template. ValidationResult exposes selected pins and requirements without
returning source bodies. Quality/release failure still uses existing kernel
diagnostics/stages with the identified PreparationResult retained where promised.
No second failure journal or public passed-check input is introduced.

Promote the existing themes.resolve support-group shape check to a public narrow
name, preserving its implementation and resolve_theme caller. The request
conversion reuses that check for duplicate/missing capabilities and mixed common
mode/release/profile pins. Per-descriptor vocabulary and bounds remain owned by
CapabilityStatus. No duplicate descriptor validator is proposed.

The existing theme-support amendment assigns the packaging compatibility callable
to composition/reporting.py. Bring forward only that pure callable if required
to test task 7 against the production seam; task 8 still owns composition,
registration and activation. Catch InvalidVersion/InvalidSpecifier and return
False. A supplied descriptor never establishes observed fidelity or release
assurance. Creating that already-planned module requires root's ledger update
before source creation, not a new owner or capability.

## Exact wire projections

| Wire field | Existing contract and conversion |
| --- | --- |
| table columns | borrow PreparedColumn, Field, SemanticRole and ValueFormat directly |
| table rows | arrays of arrays of existing ScalarWire; decode against each corresponding column Field; retain null_text/long_labels and empty_note |
| series values | existing ScalarWire array; decode against its retained Field, including unit/precision/scale |
| chart categories | ScalarWire array; decode against retained category_schema; retain order and null_behavior |
| resolved parameters | ordered name/tagged ParameterWire pairs; use decode_parameter/encode_parameter |
| supplied parameters | closed name/value objects where value is ParameterWire; at most 16; retain original non-null parameter semantics and check canonical text-value bound 512 bytes before admission |
| metric provenance | reuse existing MetricWire and its existing metric encode/decode functions; preserve labels, schema, period/as_of, producer/method/source and external evidence |
| snapshot reference | one shared upstream SnapshotRefWire: feed_id, producer_version as existing VersionWire string, content_digest; reconstruct SnapshotRef with explicit integer version conversion and the original constructor |
| all remaining prepared fields | derive directly from PreparedReport annotations, including all explicit pins, presentation, capabilities, statement and policy |
| quality/requirements/summaries/support | derive from their existing dataclasses; preserve mixed original/current Finding scopes and every EvidenceRef unchanged |

SnapshotRef.producer_version must not be a raw JSON number: its supported int64
range exceeds canonical safe JSON integers. The shared upstream boundary owns
SnapshotRefWire in snapshot_models.py so report and snapshot/runtime codecs use
one representation. Enforce the reporting request feed_id's canonical 128-byte
bound before admission; task 8 requires the retained snapshot ref to equal it.

Expose public aliases for existing snapshot_wire encode_cell, decode_metric and
encode_metric implementations rather than copying their exact conversions.
This is a small reviewed upstream boundary extension; existing implementations
and existing callers remain unchanged. encode_cell preserves declared Decimal
scale. No numeric/date kind is inferred from the contents of a string.

From-wire prepared conversion reconstructs rows/series/categories, parameter
pairs, snapshot ref and provenance, then calls the original PreparedTable,
PreparedSeries, PreparedLineChart and PreparedReport constructors. Remaining
metadata is already converted by strict JSON-mode Pydantic validation. Output
keeps scalar arrays untagged per cell, with kinds carried once in field schemas.
Only parameter values require individual tags; this preserves the size proof.

## Identities, codecs and task-8 consumers

Keep task 6's definition_identifier and theme projections unchanged. Define the
prepared content identifier as SHA-256 of existing canonical_bytes over the
normalized PreparedContentWire, excluding only its final content_digest field.
The callback operates on the permitted internal constructor state without
serializing a placeholder digest. Public decode/encode verifies the supplied
final digest; a blank or altered digest fails. No clock, operation, receipt,
target observation or quality result enters prepared identity.

Validation-scope identity is exactly SHA-256 over existing canonical JSON for
schema_version='1', ReleasePolicy.required_checks in retained order and the exact
scope_label. requested_designation is excluded. No second policy serializer or
fingerprint algorithm is introduced.

Provide fixed, typed PydanticCodec factories for validation request/result,
discovery request/result and preparation request/result. Provide prepared and
quality leaf codecs for retained-result readback, plus requirements/summary
schema exposure through their derived models. Their schema() output is the exact
descriptor input_schema/result_schema task 8 uses; no handwritten parallel
operation schemas. All use the same fixed projections and opt-in JSON mode.

The three report request codecs advertise max_input_bytes=65,536 and depth=32,
including their wrapper fields; for_input preserves that bound during canonical
request normalization. Only preparation result/retained prepared readback needs
the approved 8,388,608-byte result cap. Validation/discovery retain the existing
1 MiB result default; no unrelated operation limits increase. Result caps remain
defensive and cannot replace supported-shape checks before admission.

## Supported-size proof and independent validation

Retain the approved whole proof: source canonical snapshot S <=1,048,576, one
table/one chart, combined 64 selected fields/series, no duplicate selection,
16 parameters, bounded title/identifiers/presentation and exactly nine findings.
Rows/series/categories are direct primitive arrays, never per-cell objects or
JSON text embedded in JSON. Source values/metadata/provenance repeat at most the
approved six-fold envelope. Metadata allocations remain theme32 + parameters16
+ selection64 + findings324 + statement32 + wrappers32 = 500 KiB <=512 KiB.
Thus result <=6S+524,288 <=6,815,744 <8,388,608.

Tests must build a near-maximal supported snapshot through the real upstream
codec, verify its canonical S independently, prepare maximal permitted projection
duplication, include bounded largest generated metadata/findings and count actual
canonical full result bytes independently using standard JSON serialization.
Check both 6S+512 KiB and 8 MiB, exact field-directed values and every pin. Record
component counts separately so a missing provenance/quality section cannot make
the test pass. Include UTF-8/control-character escaping and source-versus-display
labels. The integration owner still proves the retained-snapshot invariant across
restart and actual installed REST/MCP transport/readback. No mock source-size
promise or post-acceptance output failure closes those gates.

Required regressions include existing default PydanticCodec clients, dataclass
unknown fields/constructors/defaults, schemas recursively closed without callback
fields, exact int64 extremes/Decimal scale/date/datetime/bool/text/null cases,
schema-directed table/chart/provenance roundtrips, normalized defaults,
tampered identity, scope-order/content sensitivity, preserved mixed scopes,
descriptor properties/common pins and real malformed-version rejection.

## Experiments and whole-owner budget blocker

Ignored task-7 research establishes actual installed-library behavior, not
implementation acceptance. wire-shape-experiment.log reproduces schema generation
for every explicit operation shape and a quoted wide snapshot version.
derived-shape-experiment.log shows derived prepared shapes preserve borrowed Field
metadata and exact string payloads without the callback. The typed derivation
probe passes Pyright strict and exercises original constructor rejection,
recursive extra rejection, copied defaults, Decimal scale/null and a wide actual
SnapshotRef. typed-derivation-pyright.log and typed-derivation-experiment.log retain
the outputs. complete-derived-models.log covers every derived operation schema.

Measured alternatives: the complete copied shape prototype is 142 LLOC. The
complete fixed derived model declarations/imports are 32 LLOC, plus the measured
9-LLOC typed projection helper, explicit scalar/reference leaf fields and needed
imports. The separate typed constructor helper is 6 LLOC. These measurements do
not yet measure complete production converters, every guard or all other owners'
remaining work, and are not a claim that implementation fits.

Current shared adapters are 1,200/1,500, leaving 300 for **all** approved remaining
work. The previous report-only 220+70/1,490 forecast omitted snapshot-runtime
4.1 public read/latest and runtime5.1–5.4 codecs. It is superseded as a whole-owner
feasibility statement. The upstream planning worker currently estimates another
92–155 adapter LLOC for those surfaces and identifies missing authoritative
publication/latest/binding/run/reconcile result values. Those future contracts are not prerequisites for this bounded task. Before its
acceptance, measure its complete actual delta and update the full residual forecast;
reassess dependencies and actual capacity before each subsequent task GO.

The report draft tentatively needs 155–185 net adapter LLOC including the shared
JSON seam, fixed derived shapes, exact converters/factories and shared scalar
aliases before the existing-schema deletion candidate above; that range is a
forecast, not a measured finished implementation. Keep
the entire task-8 resource/fact/guard estimate of 70, without omitting any function.
Together with upstream92–155 this initially projects 1,517–1,610. The measured
schema reuse candidate, conservatively net62, changes that full-owner range to
**1,455–1,548**. Its lower case fits with45 reserve; its upper case still exceeds
the approved cap by48. This is a concrete source-removal candidate, not guaranteed
fit or a new cap. Root must measure actual shared reuse, retain an explicit forecast for every
remaining adapter surface, and stop the current implementation if it cannot fit
within the approved actual owner/module/function limits. A hypothetical upper
future forecast is a recorded risk, not proof that this bounded task cannot fit;
future tasks require their own capacity and dependency reassessment. No cap increase, ownership relocation, hidden future omission or additional
speculative savings are authorized here. Local 300-module/50-function/complexity10
limits also remain, especially for additional snapshot_wire.py conversions.

If independent review approves this contract seam, implementation still requires
root's explicit bounded task-7 GO under the actual unchanged limits. It must use
RED-first tests, fresh actual measurements, matching-source canonical checks and
independent implementation review. Task 8 activation/evidence and tasks 9–11
example/distribution/guide obligations remain unchanged.
