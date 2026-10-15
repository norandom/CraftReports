# Implementation Plan

All tasks are unchecked. Each executable task is a bounded 1–3 hour unit and requires fresh relevant evidence plus independent task review before root accepts/commits it. Overnight fast-track does not waive those gates. Root coordinates shared gate files and commits; no worker stages another owner's files.

## Foundation

- [x] 1. Activate the bounded preparation owners and imports
  - Apply the unchanged 50 function / 300 module / 1,500 capability / complexity 10 defaults to reporting, themes, policies and public-packs; record exact reviewed source/content paths and this spec approval in breadth/quality policy before source expansion.
  - Keep existing application unchanged at measured 1,449/1,500; put feature operations/ports under reporting. Include supporting existing adapters/composition and development-gates recipe paths in their existing budgets; do not add executable content below data-only examples or raise any existing limit.
  - Narrowly extend import checks for the Design's dependency direction and add positive/negative boundary fixtures, retaining SDK/ORM/runtime prohibitions. Serialize shared edits with snapshot-runtime and root.
  - Done when focused engineering checks accept the exact reviewed owners and reject a deliberately forbidden reporting-to-runtime/app-SDK import; canonical fast checks pass with real exit code recorded.
  - _Boundary: Development-gates activation integration_
  - _Requirements: 1.3, 4.1, 4.6, 6.1, 6.3_

## Core

- [ ] 2. Establish pure value contracts and reusable declarations

- [ ] 2.1 Integrate the prerequisite theme and policy value contracts
  - Introduce the Design's pure themes.values SemanticRole, ValueFormat, theme/style values and PackPin using the accepted upstream shared VersionPin; introduce policies.values ReleasePolicy, ExternalStatement, CheckScope, observations, findings and release result values.
  - Keep these frozen value modules independent of report definitions, compilation, orchestration and concrete adapters. This explicit integration task crosses the theme/policy contract seam once; later resolution/evaluation tasks consume these existing contracts.
  - Done when the two pure value modules import independently through the approved inward boundaries and the exact types needed by ReportDefinition and PreparedReport exist before those modules are implemented.
  - _Boundary: ThemeResolution and QualityEvaluation pure value-contract integration_
  - _Depends: 1_
  - _Requirements: 2.1, 3.1, 4.7, 5.1, 5.7_

- [ ] 2.2 Define reusable report declarations and parameter validation
  - Consume accepted upstream Snapshot/Scalar/Field/InputRequirements and shared VersionPin; never redefine those values.
  - Consume the accepted theme/policy value contracts from 2.1; keep their ownership in themes.values/policies.values rather than introducing replacement types in reporting.
  - Implement the closed table/line-chart/source/parameter schema using installed Pydantic support and frozen inward values. Validate definition/template identity, inclusive ranges, choices, defaults, reference dependencies, explicit field/metric kind/unit/shape/null constraints, target requirements and release scope.
  - Emit parameter-resolved upstream input requirements and structured locations for missing/invalid parameters or unsupported executable/unknown constructs. Apply the reviewed bounded source/cardinality/string limits before admission; metric chart requirements exclude scalar/non-numeric input before latest-complete selection.
  - Done when one public definition validates, invalid range/type/default/reference cases reject at the affected field, template digest mismatch cannot override pack structure, and no app effect is claimed.
  - _Boundary: DefinitionPreparation declarations_
  - _Depends: 2.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [ ] 3. Resolve semantic presentation and pack metadata
  - Resolve the existing theme roles, supported style/format fields, shared version pins and model-owned PackPin attribution/distribution fields established in 2.1; do not redefine their contracts.
  - Implement pure role resolution with allowlisted overrides and explicit unsupported/untested mapping status. Keep imported values/methods independent from palette/number/date presentation.
  - Specify wrapping, typed null plus display marker, empty headers/note and chart gaps; preserve units, zero and negative-value meaning.
  - Done when the public house profile resolves all required roles, prohibited/duplicate overrides reject and target fit/fidelity remains unevaluated without observed app evidence.
  - _Boundary: ThemeResolution_
  - _Depends: 2.2_
  - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 3.5, 4.7_

- [ ] 4. Prepare exact supplied tables and line-chart content
  - Project selected dataset columns/rows or the fixed metric label/value view without sorting, aggregation, joins, sign/scale conversion or interpolation; reject scalar metric chart sources and duplicate source selections within a projection; deduplicate imported metric provenance by identity.
  - Preserve upstream Decimal/int64/date/text/null types, formula-looking literal strings, category/series ordering, field metadata and imported metric provenance.
  - Assemble the reviewed immutable PreparedReport with resolved title, category Field schema, snapshot/definition/template/theme/pack/parameter/scope pins and injected existing canonical content identity; exclude clock/run/target/quality observation from content identity.
  - Done when independently expected content matches two different snapshots reused with the same definition, repeated inputs have the same digest, and a theme-only change preserves every supplied value.
  - _Boundary: DefinitionPreparation compilation_
  - _Depends: 2.2, 3_
  - _Requirements: 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.3, 3.4_

- [ ] 5. Evaluate separate findings and draft/release eligibility
  - Evaluate the existing closed check scope, observations, five quality dimensions and release-policy membership contracts established in 2.1 without generic predicates or executable rule extensions. Emit one aggregate finding per closed check, at most nine whole bounded findings; reject contradictory duplicate observations without unbounded output.
  - Mark missing/unexecuted and changed-scope observations unevaluated; validate/copy the optional closed ExternalStatement scope/issuer/evidence and retain external metric/compliance claims as external without upgrading methodology or standards assurance.
  - Require internally passed declared checks for scoped validated eligibility; provide draft designation and visible failed/unevaluated summary after valid input/access. Accept target evidence only through matching trusted app observations.
  - Done when the policy matrix proves required missing/fail/pass behavior, stale target/artifact/content scope invalidation, external evidence separation and no release from ingestion-only validation.
  - _Boundary: QualityEvaluation_
  - _Depends: 4_
  - _Requirements: 1.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

## Integration

- [ ] 6. Load configured public and private declarative packs
  - Add the feature-owned reporting PackReader protocol and concrete bounded configured-root reader; compose one immutable pack snapshot without ambient search, remote URLs, archive extraction or executable loading.
  - Resolve qualified exact versions with installed packaging; enforce manifest digests, declared compatibility and permitted path containment including symlink/junction escape, duplicate identities and missing assets.
  - Filter discovery/read access independently from artifact distribution permission and sanitize failures without private body/root/data disclosure.
  - Done when a temporary external private fixture uses the same validator as public content, missing/incompatible/duplicate/executable/escaping packs reject without fallback, and unauthorized discovery exposes no private source.
  - _Boundary: ConfiguredPackReader integration_
  - _Depends: 3, 5_
  - _Requirements: 1.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 6.2_

- [ ] 7. Encode the preparation contracts with exact public wire values
  - Reuse existing strict PydanticCodec and upstream scalar encoder/decoder for exact int64/Decimal/date/datetime values and typed fields; reject unknown fields and coercions.
  - Implement the reviewed definition, pack summary, requirements and PreparedReport/QualityEvaluation request/result codecs with published 64 KiB input/depth-32 and 8 MiB preparation-result limits; do not increase unrelated operation limits.
  - Bind the existing kernel canonical serialization to prepared content identity without an inward adapter import or duplicate fingerprint implementation.
  - Done when result roundtrips preserve wide int64, Decimal precision, date/time, literal text and null distinctions, tagged resolved parameters/category schemas remain typed, input caps reject before acceptance and the independently counted maximal output fits the Design's 6S+512 KiB bound below 8 MiB. Defensive result-cap checks fail any implementation defect without weakening the approved pre-acceptance limit contract.
  - _Boundary: Preparation boundary codecs_
  - _Depends: 4, 5, 6_
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 6.3, 6.4_

- [ ] 8. Register guarded validation, discovery and preparation operations
  - Inject the accepted upstream data.ports SnapshotReader and existing journal/result services plus reporting PackReader/PreparationFactWriter into feature-owned reporting.operations handlers and the composition provider; keep kernel application and HTTP/MCP transport files unchanged. Implement the typed fact conversion and immutable pack ResourceReader/delegating ExecutionGuard in adapters/report_resources.py; storage owns the restricted retention method from upstream 3.3 and imports no reporting types.
  - Require accepted upstream 4.1 concrete SnapshotStore/publication/read behavior and its finalized retained-snapshot size invariant before exposing the preparation capability; fail closed when a reader cannot establish S <=1 MiB across restart. The protocol alone or a later post-activation check cannot establish this admission-proof prerequisite.
  - Register the three versioned contracts behind existing authentication/resource guards. Preparation creates a retained result with kernel retry identity and separate preparation/quality stages; target mutation/export/reopen stay absent.
  - Use unversioned registry operation names with contract version 1 and `.v1` MCP tool names. Declare exactly the Design's two immutable pack resources for validation, no resources for filtered discovery, and snapshot plus both pack resources for preparation. Wire separate source/artifact-scope authorization, authoritative token readback and actual provider health before exposing the capability; reject pack mutations/reloads during a host lifetime.
  - Retain trusted prepared-check and quality-decision facts through the existing durable evidence table, read back exact bytes/ownership/digests/full resource pins, then attach verified refs to observations and stages. Include all three completion pins in every stage ref; neither public payloads nor expected values can manufacture trusted facts. Preserve prepared passed/quality failed and retained findings for release_blocked.
  - Revalidate exact pack/template/snapshot pins and bindings on execution. Reusing retry identity/content returns the same operation; changed content conflicts; missing input never switches to latest. Honor draft/validated requested designation; missing required checks produce release_blocked with retained preparation/findings and no validated label.
  - Done when operation discovery, authorization, structured stage/recovery failure and retained result/evidence readback work through the real kernel, with no source disclosure or alternate journal; correct full-set evidence completes, omitted/altered pack pins and unavailable preparation evidence prevent completion.
  - _Boundary: PreparationOperations integration_
  - _Depends: 6, 7_
  - _Requirements: 1.1, 1.4, 1.5, 4.3, 4.5, 4.7, 5.4, 6.1, 6.2, 6.3, 6.4_

- [ ] 9. Add public table/chart content and the ordinary caller recipe
  - Add examples/reports/supplied_portfolio.json, examples/templates/public_report/manifest.json and examples/themes/house.json under declared public-packs ownership and scripts/examples/prepare_reusable_report.py under the existing development-gates executable owner.
  - Use the accepted production snapshot-runtime host, SnapshotReader and durable journal providers with synthetic data published through their public operation. Reuse installed-host lifecycle helpers where applicable; do not create a synthetic journal/reader or a new test-only host capability. Supply explicit roots and credentials outside transcripts, two snapshots and bounded owned resource lifecycle.
  - Exercise REST and MCP using the same adopter caller path, inspect retained typed values/pins/findings and demonstrate corrected missing-binding failure plus required-unevaluated draft/release rejection with AI disabled.
  - Done when the recipe's exact invocation returns independently compared public table/chart content for both snapshots and cleans up only its owned host/process/root resources.
  - _Boundary: Public preparation example integration_
  - _Depends: 8_
  - _Requirements: 1.5, 2.1, 2.2, 2.3, 4.1, 5.3, 5.4, 5.5, 6.1, 6.5, 6.6_

## Validation and adoption

- [ ] 10. Verify installed-client behavior and public/private distribution isolation
  - Run the installed-wheel ordinary REST/MCP conformance journey against real internal collaborators, including retry equivalence/conflict, authorization, exact retained readback, the actual 8 MiB operation transport profile and maximal supported-size canonical-byte proof. Confirm every activated SnapshotReader provider enforces finalized retained snapshot size <=1 MiB including after restart; include escaped text, repeated labels, parameter tags, provenance and bounded finding/statement/theme metadata in the proof fixture.
  - Inspect actual built wheel/sdist and sanitized diagnostics for private sentinel exclusion; temporary private pack files remain external and independently authorized source/artifact policies remain distinguishable.
  - Verify required check failure/unevaluated release rejection and matching/mismatching trusted app-observation scope using pure target observation fixtures; identify those as policy checks, not browser output evidence.
  - Exercise installed real provider composition with complete snapshot/source/artifact-scope pins, then deliberately omit or alter each pack pin and make retained preparation evidence unavailable. Assert completion is withheld, retained result/stage distinctions remain truthful, and reopened exact fact readback restores only genuinely retained evidence; public passed flags never create trusted facts.
  - Done when focused contract/integration tests pass with snapshot/pack/definition/operation/digest, actual commands/exit codes and owned cleanup evidence recorded under ignored preparation artifacts.
  - _Boundary: Preparation acceptance integration_
  - _Depends: 9_
  - _Requirements: 2.1, 2.6, 3.2, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4, 6.6_

- [ ] 11. Deliver and execute the reusable-report quickstart
  - Write docs/quickstarts/Quickstart_How_to_prepare_a_reusable_report.md from the established template, lead with the report owner's observable result and document exact installed-host/public-pack/credential prerequisites, both transports, expected pins/findings, failure recovery and cleanup.
  - Link the guide from docs/quickstarts/index.md and the relevant product entry point; distinguish reusable preparation from direct isolated app edits and downstream live/XLSX behavior.
  - Follow the guide from a clean installed package with public fixtures and AI disabled; run the same recipe, independently inspect expected content and record environment/command/results rather than copying prior success.
  - Done when an integrator can reproduce two prepared reports and a meaningful rejection/recovery using the documented invocation without private content or an SDK.
  - _Boundary: Preparation adopter documentation and executable verification_
  - _Depends: 9, 10_
  - _Requirements: 6.5, 6.6_

- [ ] 12. Validate the complete bounded preparation feature
  - Run fresh relevant canonical fast/integration checks, requirement coverage, ownership/import/budget assessment and independent feature validation under kiro-verify-completion/kiro-validate-impl.
  - Reconcile exact upstream/downstream immutable seams and confirm there is no duplicate snapshot state, compiler/runtime cycle or unperformed target/artifact assurance in results or guide.
  - Done when the feature validation records GO only for the demonstrated preparation scope with matching source/evidence; any missing required check remains open/NO-GO or MANUAL_VERIFY_REQUIRED as applicable, and all task-local independent review references are real.
  - _Boundary: Bounded preparation final acceptance_
  - _Depends: 10, 11_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

## Cross-spec prerequisites

Task 2.1 requires accepted craftreport-snapshot-runtime task 2.1 shared pins; task 2.2 additionally requires its 2.2 data values/input requirements/completeness. Task 7 requires its task 2.3 exact scalar wire codec. Task 8 requires its 2.3 data.ports SnapshotReader seam, 3.1–3.4 durable journal/provider implementation (including 3.3's restricted preparation-fact retention/readback method) and 4.1 concrete SnapshotStore/publication/read/latest operations with the finalized retained-size invariant; capability exposure fails closed without that invariant. Task 9 additionally requires accepted upstream 4.2 production host with initial durable publish/restart proof and uses synthetic data only. These cross-spec IDs must match the sibling's independently reviewed final plan; a changed upstream task graph triggers revalidation. Root serializes shared activation/provider wiring. These requirements do not gate independent report-value design on browser feasibility.

No `(P)` marker is used: the first preparation slice reuses shared value contracts sequentially; root may delegate disjoint read-only audits without changing task acceptance order. No required acceptance test is optional. Mandatory guide/example tasks follow the explicit project documentation rule, which takes precedence over the generic task rule excluding documentation.


## Implementation Notes

- Task 1: independently approved by `/root/review_report_model_activation_1`;
  24 focused tests/106 subtests, scoped Ruff/format/Pyright and actual gates
  passed, plus 16 independent import probes. Evidence:
  `artifacts/report-model-packs/task-1/`. Scanner +18 LLOC; tests +24;
  development-gates1067/1500 and application1449/1500 unchanged. Exact public
  content remains nonexecutable; snapshot fixture/recipe approvals preserved.