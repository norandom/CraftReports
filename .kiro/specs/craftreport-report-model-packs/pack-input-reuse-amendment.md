# Pack input codec reuse amendment — proposal

Status: independently approved bounded task6/7 plan. Task5 was accepted in
commit bd04016; root integrates this plan before task6 source implementation.
Reviewed SHA256: 684335e16561ec8208ccbb30fbe14492fe90a84dc0bebad83e112550b673863f.
This status paragraph is the only post-review editorial change.

Task 6 promises identical public/private JSON validation, but task 7 currently
owns the absent production asset codecs and canonical definition identifier.
Bring forward only those prerequisites into task 6, in the already approved
`adapters/report_models.py` and `adapters/report_codecs.py`. Task 7 reuses and
completes them. Inject those real functions into the reader; fixture decoders
cannot establish the task 6 production acceptance claim. No dependency, owner,
budget increase or general schema framework is proposed.

## Smallest source seam

| File | Task 6 responsibility |
| --- | --- |
| `src/craftreport/reporting/ports.py` | Frozen `PackSelection`, `PackSummary`, `PackFailure` and `PackReader` protocol. These types do not yet exist; reuse existing `reporting.prepared.ResolvedPack` and `themes.values.PackPin`. Selection carries namespace/name/exact version; summary carries only opaque qualified identity, version, attribution and permitted distribution metadata; failure carries a closed safe code/location, never a root or body. |
| `src/craftreport/adapters/pack_reader.py` | Trusted deployment-only `PackSource`, bounded activation, injected typed asset decoders/definition identifier, installed packaging compatibility and immutable authorized lookup. |
| `src/craftreport/adapters/report_models.py` | Only missing closed manifest/reference fields and the thin declaration/parameter wire envelope described below. Borrow existing contract types for every compatible nested field. |
| `src/craftreport/adapters/report_codecs.py` | Asset decode/encode, existing canonical serialization plus SHA-256 identifier, exact scalar conversion, bounds and safe errors. |
| `tests/reporting/test_pack_reader.py`, `tests/reporting/test_report_codecs.py` | Production-collaborator tests using public/synthetic documents and temporary external private roots. |

No edits to snapshot codecs, pure declaration/theme contracts, kernel validation,
application or transports are needed. The two new adapter files retain adapters
ownership; moving work between tasks does not change its aggregate cost.

## Reuse the installed library

Installed Pydantic is 2.14.1. Its `TypeAdapter.validate_json` accepts `strict=True`
and `extra='forbid'`; its stdlib dataclass schema generation invokes existing
`__post_init__`. Use adapters derived from existing `Theme`, manifest field
contracts and non-scalar declaration dataclasses, including tuples and enums,
instead of hand-copying their recursive schemas or constructors.

Direct `TypeAdapter[ReportDefinition]` is insufficient: parameter defaults,
choices and bounds contain the `Scalar` union, whose public contract requires
exact tagged wire values. Add a small boundary declaration envelope whose
non-scalar annotations borrow the existing contracts and whose parameter field
uses an explicit parameter wire type. Present scalar values use existing
`snapshot_models.ParameterWire` and `snapshot_wire.decode_parameter` /
`encode_parameter`; preserve omissions/defaults explicitly and construct the
existing `ParameterDefinition`/`ReportDefinition` once. Require tag/declaration
kind agreement. Do not infer Decimal/date/int64 from string contents or allow
JSON numbers for exact numeric scalar payloads. This is a wire/domain difference,
not a second authoritative semantic validator.

Keep existing `PydanticCodec` for task 7 operation envelopes. Its current
`StrictWireModel` constraint and strict Python `model_validate` path do not
provide direct JSON-mode stdlib-dataclass conversion. Do not change that shared
codec merely to fit asset loading. The bounded asset functions can validate
canonical JSON through `TypeAdapter` and later be composed by the operation
codecs. Reuse `bounded_object`/`canonical_bytes` for limits and normalization;
never validate JSON by first coercing arbitrary raw values into domain objects.

Before implementation acceptance, run focused experiments proving recursive
extra rejection, tuple/enum conversion, constructor invariants, numeric-kind
behavior and JSON-schema closure on these actual contracts. JSON strict mode
still has documented type-specific conversions; prove the allowed presentation
number policy separately from the exact supplied-scalar policy. Experiments have
not been run for this proposal. Library source inspection establishes available
APIs, not runtime acceptance.

## Bytes, identity and access

Activation must check the manifest shape and every listed asset's actual retained
bytes, including both definition and template references independently. Bound
manifest/declaration JSON to 64 KiB and depth 32, and semantic theme to 32 KiB;
reject unsupported constructs, duplicates, missing/incompatible assets and any
partial activation. Reuse the definition identifier for `validate_template`.
Freeze the successfully validated bytes/values for the host lifetime.

A resolve-then-read path check alone is insufficient against a junction or
symlink replacement race. Bind containment to the file actually opened, read it
once, and hash/decode those same bytes. Reject absolute, drive-relative, UNC,
URL/traversal and link/reparse escapes. On Windows, establish containment from
the opened file handle's final path beneath the anchored configured root, rather
than claiming `Path.resolve()` alone proves it; fail closed when the selected
platform cannot establish that property. Test replacement between preliminary
path inspection and open, plus Windows junction escape. Deployment sources are
trusted, stable during activation, and not request-selected; this does not claim
protection against an administrator maliciously modifying an already trusted
source. Retained bytes cannot be silently reread/substituted after activation.

Configured source/artifact scopes are authoritative. Manifest scopes must agree
with trusted configuration and cannot broaden it. Discovery and read filter
source permission before disclosing existence/body; artifact permission remains
a separate check for use/distribution. Return only safe opaque errors. A private
fixture must traverse these same production codecs and reader, with neither a
special validation branch nor private content in public artifacts.

## Proposed exact asset and manifest identity

Each explicit PackSource root contains exactly manifest.json; do not recursively
search directories. Multiple packs use multiple configured roots, with duplicate
qualified identities rejected. The closed version1 manifest has exactly:
schema_version (literal "1"), namespace, name, version, engine_version_range,
definition, template, theme, required_capabilities, permitted_overrides,
source_visibility_scope, artifact_visibility_scope, attribution. The three asset
references each contain exactly path (relative JSON file) and sha256 (lowercase
SHA-256 of the raw bytes actually read). Use existing capability/override types
and scope/identity bounds; all fields required, no executable/unknown extension.
Configured scopes must equal manifest scopes. Manifest permitted_overrides must
match the declared Theme.permitted_overrides; no second override authority.
Engine range is evaluated against the installed CraftReport version. Existing
report-required capabilities and theme support declarations remain authoritative;
manifest capability requirements must agree with the decoded definition.

The pack VersionPin has identity namespace/name, exact declared version, and
content_digest = SHA-256(existing canonical JSON of the whole validated manifest).
The manifest contains no pack digest/self-pin; asset raw hashes transitively bind
all retained source bytes. Manifest whitespace/object-key order is normalized;
changing a listed asset's raw bytes requires a changed listed sha256 and thus a
new pack digest, even if its semantic definition is unchanged.

Definition/template semantic VersionPins use the decoded report_id/version and
SHA-256(existing canonical JSON of the normalized declaration wire representation,
including exact tagged parameters). The same identifier is injected into
validate_template and reused by task7. Independently validate both raw reference
hashes and decode both documents; require their semantic pins and content equal.
Distinct semantic documents remain unsupported; identical semantic documents in
differently formatted JSON do not invent a second template model.

Theme wire uses the existing Theme structure, including VersionPin. Its semantic
content_digest is computed over the normalized theme wire with ONLY
version_pin.content_digest omitted. Verify the supplied digest against that hash
before exposing the Theme. Its identity/version remain included. The manifest
raw theme SHA-256 includes the completed self-pin field, so integrity has no
self-referential hash equation. No blank or placeholder pin crosses the boundary.
Use existing library JSON serialization and canonical_bytes; these are explicit
hash projections, not another serialization engine. Task6 tests raw-vs-semantic
change sensitivity and self-pin tampering; task7 reuses the exact same projections.

These concrete field/hash choices are proposed for independent review. No caller
selects a path or source root, and no new operation or schema version is activated
merely by this amendment.

## Remaining adapter budget and minimal task edits

Parent-supplied current adapters baseline is 873/1,500 LLOC, leaving 627; this
proposal has not rerun measurement. Planning allocation across **all** remaining
report adapter work is:

| Increment | LLOC estimate |
| --- | ---: |
| Task 6 `pack_reader.py`, including platform containment | 180 |
| Task 6 `report_models.py` asset fields | 55 |
| Task 6 `report_codecs.py` asset validation/identity | 90 |
| Task 7 additional envelopes, support descriptors, prepared/quality/results and exact conversion | 220 |
| Task 8 `report_resources.py` fact/resource/guard adapter | 70 |
| Total added / projected aggregate / remaining | 615 / 1,488 / 12 |

These are estimates, not new per-file caps or evidence of feasibility. Task 6
must report measured deltas and refresh the full remaining forecast; the 12-line
reserve is narrow. Stop and simplify within the reviewed seam if actual work
cannot fit. Do not move ownership, omit task 7/8 responsibilities, increase caps
or claim hypothetical deletions as savings. Existing 50/300/1,500/10 limits apply.

Amend task 6 to depend on accepted upstream task 2.3 scalar codecs and own this
asset-codec subset; task 7 changes from creating to completing/reusing that
subset. Preserve task 6's dependencies on 3/5 and task 7's on 4/5/6. Task 8's
activation, durable evidence and public boundary gates are unchanged. No task
checkbox, phase metadata or breadth/quality policy changes accompany this draft.
Existing task 9 example and task 11 quickstart ownership/verification remain:
`scripts/examples/prepare_reusable_report.py` and
`docs/quickstarts/Quickstart_How_to_prepare_a_reusable_report.md`.

Required focused evidence covers unknown/executable fields at every nested
boundary; exact wide int64, Decimal precision/scale, date/time, bool/text/null and
wrong tags; both reference digests and canonical identifier; duplicated identity,
malformed versions and changed files; unauthorized private discovery/read and
separate artifact scopes; real outside-root assets, Windows junction and
check/open replacement; sanitized failure details; immutable post-activation
reads. Task 7 retains complete result roundtrips, schema publication and maximal
output-size proof. Canonical checks and independent review follow source freeze;
no tests, browser run or implementation claims are made by this proposal.
