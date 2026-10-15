# Requirements Document

## Introduction

A report owner prepares a reusable table and line-chart report from supplied datasets and metrics, with a consistent semantic theme and an inspectable draft/release decision. Preparation is deterministic and works for ordinary software callers with AI disabled. This bounded feature allocates the umbrella's definition, template/pack and quality-policy obligations; it does not establish live rendering, export fidelity or financial assurance.

## Boundary Context

- **In scope:** versioned declarative definitions, typed parameters and bindings; prepared table/line-chart values; one configurable semantic profile; public and configured private declarative packs; scoped findings and release eligibility.
- **Out of scope:** data publication/storage/scheduling, app mutation, XLSX creation/reopen, executable definitions, report-derived aggregation, financial methods/GIPS, generic policy languages, visual designers and other apps/domains.
- **Adjacent expectations:** snapshot-runtime supplies immutable identified input and retained operation results; the kernel guards ordinary operations; the app supplies verified capability and observed layout/consistency evidence. Missing downstream evidence remains unevaluated.
- **Umbrella allocation:** 1.1–1.7, 4.1–4.7, 5.1–5.8 and 9.1–9.3, 9.5–9.12; preparation portions of 2.6, 2.10, 3.2–3.4, 3.8, 10.1–10.2, 10.4–10.8, 11.1, 11.7 and 12.1–12.2. Actual output comparison in umbrella 9.4 and visible draft/export enforcement are app-owned consumers of this policy contract.

## Requirements

### Requirement 1: Reusable definitions and parameters

**Objective:** As a report owner, I want a bounded reusable definition, so that changing supplied data does not require rewriting app commands.

#### Acceptance Criteria

1. When a caller validates a versioned definition, the CraftReport preparer shall identify its table, line-chart, named input and parameter requirements without mutating an app.
2. When a caller supplies parameter values, the CraftReport preparer shall validate required names, declared types, defaults and permitted choices and expose the resolved values.
3. If a definition contains unknown constructs, executable code, formulas, SQL or arbitrary app actions, the CraftReport preparer shall reject it with a structured location and unsupported or invalid-input reason.
4. If a required binding, field, metric or compatible type/unit is absent, the CraftReport preparer shall identify the unmet requirement and withhold complete preparation.
5. When the same compatible definition is selected against different complete snapshots, the CraftReport preparer shall prepare each report without changing the definition.
6. When definition, parameters or presentation selections change, the CraftReport preparer shall expose the new selection identities and invalidate findings dependent on the changed selections.

### Requirement 2: Pinned supplied content

**Objective:** As a reviewer, I want prepared content tied to exact supplied values, so that presentation remains traceable to the producer.

#### Acceptance Criteria

1. When preparation succeeds, the CraftReport preparer shall identify the immutable input feed/version/content, definition/version, resolved parameters, pack/template/theme versions and validation scope used.
2. When preparing table content, the CraftReport preparer shall preserve selected supplied values, value types, labels, units and declared column/row order without financial aggregation or sign/scale conversion.
3. When preparing line-chart content, the CraftReport preparer shall preserve selected category and series order, supplied values and explicit null gaps without interpolation or invented replacement values.
4. When prepared content uses imported metrics, the CraftReport preparer shall retain their producer/method, period/as-of, source and externally supplied evidence identity.
5. When input text begins with a spreadsheet formula marker, the CraftReport preparer shall preserve its text type and literal content.
6. When all pinned inputs and preparation selections are identical, the CraftReport preparer shall return identical content and presentation identity independent of execution time or caller transport.

### Requirement 3: Semantic presentation

**Objective:** As a report owner, I want configurable semantic styling, so that the report communicates data roles consistently without changing their meaning.

#### Acceptance Criteria

1. When a compatible theme is selected, the CraftReport preparer shall resolve the declared roles, typography, colors, value/date formats, units, chart styling and grid presentation into inspectable presentation requirements.
2. If overrides conflict, are prohibited or require an unsupported target feature, the CraftReport preparer shall report the incompatibility before target mutation.
3. When only the theme or template changes, the CraftReport preparer shall preserve supplied values and methodological conventions and identify the changed presentation versions.
4. When content contains long labels, missing values or an empty dataset, the CraftReport preparer shall apply the declared presentation behavior and expose unmet or unobserved layout checks.
5. When a target's style mapping is unsupported or untested, the CraftReport preparer shall identify that status and withhold a claim that the style has been faithfully applied.

### Requirement 4: Public and configured private packs

**Objective:** As a deployment owner, I want the same safe contract for public and private packs, so that private assets do not require a separate engine.

#### Acceptance Criteria

1. When public verification or an adopter example runs, the CraftReport preparer shall operate without private packs or private datasets.
2. When an operator configures a private pack, the CraftReport preparer shall apply the same schema, compatibility and binding validation used for public packs.
3. When a caller selects a pack/template/theme, the CraftReport preparer shall resolve its qualified identity and exact version only from configured permitted sources.
4. If a pack, asset or version is missing, incompatible, ambiguously identified or outside its permitted source, the CraftReport preparer shall reject the selection without fallback to another pack.
5. When a caller discovers or inspects packs, the CraftReport preparer shall expose only metadata and source content permitted for that caller.
6. When public distribution or sanitized diagnostics are produced, the CraftReport preparer shall exclude private source bodies/assets, credentials and deployment input values.
7. When prepared content is handed to an artifact producer, the CraftReport preparer shall carry pack/version attribution and artifact distribution policy separately from permission to disclose template source.

### Requirement 5: Scoped findings and draft/release decisions

**Objective:** As a reviewer, I want explicit evidence scope and release rules, so that polished presentation cannot imply unperformed numerical assurance.

#### Acceptance Criteria

1. When a report is evaluated, the CraftReport evaluator shall return separate layout, template, consistency, compliance and accuracy findings with checked scope, evidence references and passed, failed, unevaluated or not-applicable status.
2. When metrics have only schema/ingestion checks or producer claims, the CraftReport evaluator shall identify methodology as unevaluated by CraftReport and distinguish externally supplied evidence from CraftReport checks.
3. If a check is missing or was not executed, the CraftReport evaluator shall preserve unevaluated status rather than infer a pass, zero result or standards assurance.
4. If a required check fails or remains unevaluated after input and access validation succeed, the CraftReport evaluator shall permit draft eligibility and reject validated-release eligibility while identifying the blocking checks.
5. When draft output is requested, the CraftReport evaluator shall supply a visible draft designation and a validation summary that the artifact producer must render and verify.
6. When declared required reporting checks pass, the CraftReport evaluator shall state the exact scope of validated-release eligibility without extending it to unevaluated methods or standards.
7. When a compliance-related statement is supplied, the CraftReport evaluator shall retain its stated scope/evidence and identify it as supplied rather than a built-in standards or firm-wide compliance assessment.
8. If input, definition, parameters, theme/template, target content or validation scope changes, the CraftReport evaluator shall invalidate dependent prior findings before reusing a release decision.
9. When an app supplies output observations, the CraftReport evaluator shall accept only matching pinned scope and evidence identity before using them for layout/template/consistency findings.

### Requirement 6: Ordinary caller access and usable examples

**Objective:** As an integrator, I want a documented public preparation path, so that I can adopt reusable reports without AI or a bespoke client SDK.

#### Acceptance Criteria

1. When an ordinary caller discovers or invokes definition validation, pack discovery or report preparation through supported REST and MCP entry points, the CraftReport service shall apply the same versioned validation, access, retry and result-inspection semantics.
2. If a caller lacks permission for input, pack source or artifact distribution, the CraftReport service shall reject the affected action without disclosing restricted content.
3. When a caller inspects preparation limits or a request exceeds them, the CraftReport service shall expose the applicable limits and reject exceeded limits before accepting complete work.
4. When preparation finishes or fails, the CraftReport service shall distinguish preparation and quality evaluation from target mutation, artifact persistence and reopen verification and provide structured stage/recovery diagnostics.
5. When an adopter follows `docs/quickstarts/Quickstart_How_to_prepare_a_reusable_report.md` and runs `scripts/examples/prepare_reusable_report.py`, the CraftReport service shall demonstrate a public table/line-chart definition reused against two synthetic snapshots through ordinary REST and MCP with AI disabled and inspectable pinned results.
6. When feature acceptance runs, the CraftReport service shall demonstrate missing-binding and invalid-parameter rejection, private-pack visibility and distribution isolation, executable-content rejection and required-unevaluated-check draft/release rejection with commands, observed results and owned-resource cleanup recorded.



