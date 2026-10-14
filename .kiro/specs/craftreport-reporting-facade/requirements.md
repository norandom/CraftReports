# Requirements Document

## Introduction

CraftReport provides a reusable reporting facade for external data producers and supported Craft applications. This first specification covers declarative reporting using supplied datasets and metrics, visible live GridCraft dashboards, snapshot-consistent XLSX export, deterministic app-to-app MCP access, reusable configurable templates/themes, and validation evidence. AI is an optional caller.

The owner confirmed this scope during requirements elicitation: the first spec is the reporting foundation; paused reports resume with the latest complete snapshot; failed or unevaluated required quality checks permit clearly marked draft artifacts but prevent release as validated output.

During Design discovery, the owner clarified that producer-ordered snapshot versions determine latest, and older arrivals are rejected. Known duplicate retries retain their existing receipts without moving the current binding backwards.

## Boundary Context

- **In scope:** high-level report definitions and parameters; named typed data/metric publication; identified immutable snapshots; visible sheet/table/line-chart rendering and refresh controls; target/capability discovery; XLSX export and reopen evidence; shared software-callable operations; public/private template loading; separate layout, template, consistency, compliance and accuracy findings; run and failure diagnostics.
- **Out of scope:** implementing the external allocation framework or Jupyter; notebooks/kernels or a client SDK; allocation/optimization/trading; local portfolio-method calculations or a built-in GIPS rule pack; firm-wide compliance certification; WordCraft/PDF and other app implementations; accounting/forensic/invoice/tax/book/letter domains; a visual report designer; Crystal file/formula compatibility; advanced cross-tabs, subreport execution and report-derived financial aggregations; enterprise recipient distribution.
- **Adjacent expectations:** external producers supply data, metric values and methodological/provenance metadata; an available compatible GridCraft session supplies the visible editing surface; deployments configure target access, permitted pack sources and artifact destinations. CraftReport identifies unsupported capabilities rather than assuming native, browser and headless sessions are interchangeable.
- **Deployment constraint:** use the latest official downloadable GridCraft release, at least version 0.6.1, without compiling GridCraft locally. Browser deployment/verification is primary; the selected release and actual mode-specific capabilities are recorded per run.
- **Preserved future direction:** later domain methods, richer reporting operators and document targets reuse the reporting contracts and evidence without being required for this foundation. Their activation follows the breadth ledger. Foundation tables/charts present supplied values; they do not implicitly derive portfolio totals or risk measures.
- **References:** [discovery brief](brief.md), [confirmed delivery priorities](delivery-priorities.md), [Crystal delta](crystal-reports-delta.md), [template-pack boundary](template-pack-boundary.md), [verification workflow](verification-workflow.md).

## Terms and Acceptance References

- A **snapshot** is an identified immutable accepted version of the datasets and imported metric results required by a report binding. A **complete snapshot** satisfies that binding's declared input requirements.
- Producer ordering belongs to an identified publication feed. Versions from unrelated feeds are not compared as one sequence; changing a feed identity is an explicit binding change.
- A **run** identifies the snapshot, report-definition version, resolved parameter values, template/theme versions, target and validation scope used for one report evaluation or update.
- A **complete visible update** has applied the requested report-owned content and verified that content against its run; incomplete mutation is a partial result.
- **Validated output** means eligible for release under the run's explicitly declared reporting checks. It does not assert unperformed financial-method validation or standards compliance.
- **Draft output** is explicitly marked as draft, identifies failed/unevaluated checks, and cannot be described as validated output.
- Draft export relaxes reporting-quality release eligibility only; it does not bypass input/definition validation, target access, destination authorization or truthful persistence/reopen results.
- Acceptance criteria are referenced as requirement-number.criterion-number, for example 1.3. Such references remain stable through design and task generation.

## Requirements

### Requirement 1: Declarative Report Definitions and Parameters

**Objective:** As a report owner, I want to describe report intent and inputs without programming individual app commands, so that I can reuse reports consistently.

#### Acceptance Criteria

1. When a caller submits a report definition, the CraftReport service shall validate its identity/version, input bindings, parameter declarations, requested content, template/theme selection, target requirements and validation scope before starting target mutation.
2. When a valid report definition requests a bound grid/table and line chart, the CraftReport service shall produce those requested elements from its declared input bindings without requiring the caller to specify low-level app commands.
3. When a caller supplies parameter values, the CraftReport service shall validate their declared types, required values, permitted choices/ranges and binding dependencies before executing the report.
4. If a required binding, parameter, template or feature is missing or incompatible, the CraftReport service shall report the affected definition location and reason without presenting the definition as executable.
5. When a caller changes a definition or parameter selection, the CraftReport service shall identify the resulting definition/parameter version and invalidate evidence that depends on the changed selection.
6. When a caller requests presentation-only changes for an identified snapshot, the CraftReport service shall retain the supplied values and method metadata while generating new presentation evidence.
7. If a definition requests executable code or a native action outside the published reporting contract, the CraftReport service shall reject that request with an unsupported-operation diagnostic.

### Requirement 2: Typed External Data and Imported Metric Publication

**Objective:** As an external producer, I want to publish data and metrics through a documented contract, so that reports preserve their meaning and precision.

#### Acceptance Criteria

1. When an external caller publishes named datasets or grids, the CraftReport service shall validate their declared fields, value types, null handling, keys where declared, units and associated metadata before accepting them.
2. When an external caller publishes metric values or series, the CraftReport service shall require their declared metric identity, units, period/as-of metadata, source reference and producer/method version without calculating an undeclared replacement.
3. When publication succeeds, the CraftReport service shall return an identified accepted version with its schema/content summary, acceptance time and validation findings.
4. If a payload cannot preserve a declared type or numerical precision, the CraftReport service shall reject the affected publication with a field/value diagnostic instead of silently coercing it.
5. If publication violates declared required fields, key uniqueness or input-value rules, the CraftReport service shall retain the previously accepted complete version and report the violated rule.
6. When the input contains text beginning with a spreadsheet formula marker, the CraftReport service shall retain that input as text rather than execute it as a formula.
7. When producer observation time, producer generation time or receipt time is supplied or recorded, the CraftReport service shall retain each available timing field under its distinct meaning.
8. When an imported metric includes producer-declared validation evidence, the CraftReport service shall retain its provenance and distinguish that claim from checks executed by CraftReport.
9. When the external allocation framework or another conforming software client publishes the same declared input, the CraftReport service shall apply the same publication contract without requiring an AI model, notebook runtime or client SDK.
10. When the report presents supplied tables or series, the CraftReport service shall retain their declared labels, units, column order and series ordering without introducing unrequested financial aggregation.
11. When an external producer publishes a snapshot, the CraftReport service shall require its publication-feed identity and ordered producer snapshot version so that arrivals can be evaluated independently of receipt time.

### Requirement 3: Snapshot Consistency and Reproducibility

**Objective:** As a report reviewer, I want every update and artifact tied to a complete identified input, so that results can be traced and reconciled.

#### Acceptance Criteria

1. When publication accepts a snapshot version, the CraftReport service shall preserve that version's identified content rather than modify it in place after acceptance.
2. If a report requires multiple datasets or metric series and a publication lacks a required binding, the CraftReport service shall identify the incomplete input and exclude it from complete report execution.
3. When a report run starts, the CraftReport service shall pin its input snapshot, definition, parameter values, template/theme versions, target identity and validation scope.
4. When one run produces table cells, chart series and an XLSX artifact, the CraftReport service shall associate those outputs with the same pinned supplied values and version identifiers.
5. If an update completion conflicts with a newer established binding version, the CraftReport service shall report the version conflict and prevent the older completion from being represented as the current complete report.
6. When a caller repeats a publication or mutating request using the same declared retry identity and content, the CraftReport service shall return the existing operation identity/result instead of creating a duplicate accepted operation.
7. If a caller reuses a retry identity with different content, the CraftReport service shall report a conflict without applying the conflicting request.
8. When a reviewer inspects a run, the CraftReport service shall expose its retained input/version references, producer/method metadata and output references sufficient to identify what was used.
9. If retained input or artifact content is unavailable for a run, the CraftReport service shall report that missing content instead of representing the run as reproducible.
10. If a previously unseen publication has an older producer snapshot version than the latest accepted version for its feed, the CraftReport service shall reject it with a stale-version diagnostic and retain the current accepted/applied versions.
11. If a publication reuses a feed's producer snapshot version with different content, the CraftReport service shall report a version conflict without replacing that version or its current binding.

### Requirement 4: Configurable Templates and Semantic House Style

**Objective:** As a report owner, I want versioned templates and configurable semantic styles, so that reports share a house style without hardcoded financial logic.

#### Acceptance Criteria

1. When a caller selects a compatible template, the CraftReport service shall validate its required bindings and render its declared report structure using the selected dataset/parameter values.
2. When a caller selects a theme profile and permitted overrides, the CraftReport service shall resolve the declared semantic roles, typography, colors, value/date formats, units, chart styling and grid presentation for that run.
3. If a template/theme requires an unsupported target feature or contains conflicting or prohibited overrides, the CraftReport service shall report that incompatibility before target mutation.
4. When a template/theme changes, the CraftReport service shall preserve imported numerical values and method conventions while recording the changed presentation versions.
5. When a compatible template is reused with different datasets, the CraftReport service shall validate the new bindings rather than require rewriting its report operations.
6. When bound content contains long labels, missing values or empty datasets, the CraftReport service shall apply the template's declared presentation behavior and report any unmet layout rule.
7. When a report renders through an explicitly supported output capability, the CraftReport service shall apply the selected semantic profile and report unsupported style mappings instead of silently substituting an unrelated profile.

### Requirement 5: Public and Private Template-Pack Boundaries

**Objective:** As a project/deployment owner, I want public examples and private packs to use one reporting contract, so that private content does not require a separate engine.

#### Acceptance Criteria

1. When CraftReport is built or verified using its public examples, the CraftReport service shall operate without requiring private template packs or private datasets.
2. When an operator configures an external private pack, the CraftReport service shall validate it through the same compatibility and binding rules used for public packs.
3. When a caller selects a template, the CraftReport service shall resolve its qualified identity/version only from the configured permitted pack sources.
4. If a requested pack, asset or version is missing, incompatible or ambiguously identified, the CraftReport service shall report that condition without silently selecting a different pack.
5. When a caller discovers templates or requests private-pack content, the CraftReport service shall expose only content permitted for that caller by the deployment's access policy.
6. When CraftReport produces public examples, distributable packages or sanitized diagnostics, the CraftReport service shall exclude private-pack bodies/assets, credentials and deployment datasets from those outputs.
7. When a report is exported, the CraftReport service shall record the selected pack/version identity under the artifact's visibility policy without automatically including the underlying template source.
8. If a pack requests arbitrary executable code, the CraftReport service shall reject the pack as unsupported by the declarative reporting contract.

### Requirement 6: Target Discovery, Identity and Visible Report Rendering

**Objective:** As a dashboard user, I want updates in the intended visible GridCraft document, so that software completion matches what I can see.

#### Acceptance Criteria

1. When a caller requests target discovery, the CraftReport service shall return app/version/mode, session/document identity and supported, untested, unavailable or blocked reporting capabilities with reasons where applicable.
2. When a caller binds a report to a visible GridCraft target version 0.6.1 or newer, the CraftReport service shall verify that identified session/document and the required grid/table/line-chart capabilities before applying report content.
3. When a valid report run requests a visible update, the CraftReport service shall render its declared grid/table and line chart in the identified visible target and retain their report binding identities.
4. When a run updates a bound report, the CraftReport service shall preserve content outside that report's declared owned scope.
5. If the selected target is absent, disconnected, changed or incompatible, the CraftReport service shall report the affected target and condition rather than redirect the work to a different or invisible session.
6. If a requested target mode or feature has no verified reporting support, the CraftReport service shall identify it as unsupported or untested and withhold a verified-completion claim.
7. When report-owned content has been modified outside the corresponding run, the CraftReport service shall identify the conflict and invalidate affected output evidence before treating that content as verified.
8. When target mutation completes, the CraftReport service shall compare the requested bound values and chart series with observable target content before reporting a complete visible update.

### Requirement 7: Live Refresh and Visible Controls

**Objective:** As a dashboard user, I want a visible live report with explicit lifecycle and freshness, so that I can control incoming updates.

#### Acceptance Criteria

1. When a caller starts live reporting with an accepted definition and compatible visible target, the CraftReport service shall expose a running refresh state and its configured refresh interval.
2. When the reference dashboard selects a 10-second refresh interval, the CraftReport service shall schedule refresh opportunities at that interval and record attempt/completion times separately from the interval setting.
3. While live reporting is running, the CraftReport service shall apply complete accepted snapshots according to the active report binding and expose the last successfully applied version/time.
4. When the user activates the report's visible start/pause/resume/stop control, the CraftReport service shall invoke the corresponding reporting lifecycle operation and display its resulting state.
5. When pause is requested, the CraftReport service shall stop starting new report mutations and report pause as pending until any active mutation has reached a reported complete or partial outcome.
6. While the report is paused, the CraftReport service shall retain its visible content without applying subsequent publications and continue to identify the latest complete accepted snapshot separately.
7. When the user resumes a paused report, the CraftReport service shall select the complete accepted snapshot with the highest producer-ordered version for its bound feed instead of replaying each paused publication.
8. When stop completes, the CraftReport service shall stop further automatic report mutations until a subsequent explicit start.
9. If inputs or target updates fail, the CraftReport service shall expose the error and last complete accepted/applied versions rather than label the report as current solely because its timer is running.
10. When an operator configures a freshness threshold, the CraftReport service shall mark the report stale when the declared freshness measure exceeds that threshold and identify which measure triggered the status.
11. If a previous refresh remains active at the next refresh opportunity, the CraftReport service shall expose the pending/in-progress condition and prevent overlapping completions from replacing a newer complete visible version.
12. If a target mutation remains partial or ambiguous during a pause request, the CraftReport service shall expose that outcome alongside the paused/error state rather than represent the target as a complete verified snapshot.

### Requirement 8: Snapshot-Consistent XLSX Export and Reopen

**Objective:** As a report recipient, I want a saved workbook representing one complete update, so that the artifact can be inspected independently of the live feed.

#### Acceptance Criteria

1. When a caller requests XLSX export, the CraftReport service shall identify the complete run/snapshot selected for that export and its requested destination.
2. When new input arrives during export, the CraftReport service shall keep the exported values and chart series tied to the selected run instead of mixing content from subsequent updates.
3. When XLSX export succeeds, the CraftReport service shall provide the actual saved artifact reference, selected run/snapshot identity, persistence result and validation findings.
4. When an exported workbook is reopened for verification, the CraftReport service shall compare its declared table values, value types, line-chart references/series, selected styles and run identity with the exported run.
5. If save/download, artifact inspection or reopen verification fails, the CraftReport service shall report the failed stage and withhold a verified-export receipt.
6. When the requested export includes a style/chart capability supported by the selected target, the CraftReport service shall preserve that capability in the exported workbook or report an export-fidelity failure.
7. If a request would overwrite an existing artifact without the destination's declared overwrite authorization, the CraftReport service shall report a destination conflict without overwriting the artifact.
8. When a live report continues after an export, the CraftReport service shall retain the exported artifact as the selected snapshot's artifact rather than silently changing its content with the continuing feed.

### Requirement 9: Independent Quality Findings and Draft Release Rules

**Objective:** As a reviewer, I want separate scoped findings and explicit release eligibility, so that presentation cannot masquerade as financial assurance.

#### Acceptance Criteria

1. When a run is evaluated, the CraftReport service shall record separate layout, template, consistency, compliance and accuracy findings with their checked scope, evidence references and passed, failed, unevaluated or not-applicable status.
2. When a supplied metric has only ingestion/schema checks, the CraftReport service shall label its numerical methodology as unevaluated by CraftReport rather than independently validated.
3. When a quality dimension relies on producer-supplied evidence, the CraftReport service shall identify that evidence as externally supplied and separate it from checks performed by CraftReport.
4. When CraftReport checks output consistency, the CraftReport service shall compare displayed/exported values and chart series with the pinned supplied results under the declared comparison rules.
5. When CraftReport checks layout/template conformance, the CraftReport service shall evaluate the selected profile's required bindings and declared presentation rules and record unmet or unevaluated rules.
6. If a required quality check fails or remains unevaluated and the request satisfies input/definition, access and destination validation, the CraftReport service shall permit export only as draft output with the applicable findings visible.
7. When draft output is exported, the CraftReport service shall include a visible draft designation and a validation summary that identifies failed/unevaluated required checks.
8. If required checks do not satisfy the run's declared release policy, the CraftReport service shall reject a request to label or release the output as validated.
9. When the declared required reporting checks pass, the CraftReport service shall state the scope of validated-output eligibility without extending that status to unevaluated financial methods or standards.
10. If evidence is missing or a check was not executed, the CraftReport service shall preserve that status rather than substitute a reassuring zero or unqualified pass.
11. When output includes a compliance-related statement, the CraftReport service shall expose its supplied scope/evidence and distinguish it from a built-in standards evaluation or firm-wide compliance claim.
12. If data, definition, theme/template, target content or validation scope changes, the CraftReport service shall invalidate dependent prior findings and evaluate the changed output before reusing validated status.

### Requirement 10: Deterministic App-to-App Operations and Optional AI

**Objective:** As a software integrator, I want one reporting contract usable through MCP and external data publication, so that applications can collaborate without a model.

#### Acceptance Criteria

1. When an ordinary MCP client connects, the CraftReport service shall expose documented operations for contract/capability discovery, data publication, definition validation, report execution, live lifecycle control, XLSX export and run/evidence inspection.
2. When software callers invoke an equivalent operation through supported reporting entry points, the CraftReport service shall apply the same validation, target-scope, retry, error and completion semantics.
3. When an external client uses the published data-push interface, the CraftReport service shall accept supported typed publications and provide identified snapshot/run results without requiring a notebook runtime or client SDK.
4. When AI services are disabled or unavailable, the CraftReport service shall retain all required definition, publication, live-report, export and inspection operations for ordinary clients.
5. Where AI assistance is included, the CraftReport service shall subject AI-originated requests to the same contracts and access/release policies as ordinary software requests.
6. If an operation cannot be completed synchronously, the CraftReport service shall return an inspectable operation identity and pending status rather than claim that target mutation or export has completed.
7. When an operation returns an error, the CraftReport service shall provide a structured affected-operation/target reference, failure stage, reason and retry/recovery status suitable for software inspection.
8. If a caller lacks permission for a target, input, pack or artifact operation, the CraftReport service shall reject that operation without exposing restricted content.

### Requirement 11: Run Evidence, Failure Recovery and Restart Visibility

**Objective:** As an operator, I want truthful operation receipts and retained diagnostics, so that incomplete work can be recovered without duplicate or misleading output.

#### Acceptance Criteria

1. When a caller inspects an operation, the CraftReport service shall distinguish input acceptance, report preparation, target mutation, artifact persistence, reopen verification and quality evaluation results.
2. If target mutation applies only part of a requested update, the CraftReport service shall report a partial outcome with affected content/run identity and withhold complete visible-update status.
3. If work fails after external mutation but before acknowledgement, the CraftReport service shall expose the outcome as ambiguous until reconciled rather than blindly replay an insertion or save.
4. When an operator requests retry or recovery, the CraftReport service shall evaluate the operation's recorded stage and target/version state before performing further mutation.
5. If a service or target restarts while work is pending, the CraftReport service shall expose the retained accepted/run identities and recovered, failed or ambiguous status rather than manufacture completion.
6. When retained runs or artifacts are queried after service restart, the CraftReport service shall resolve their retained references or report missing/unavailable state under the configured retention policy.
7. When an operator inspects a failure, the CraftReport service shall expose relevant validation findings, target/version identity, attempted operation and stage diagnostics under the deployment's visibility policy.
8. When an operator defines retention or publication policies, the CraftReport service shall make their effect on input, run/evidence and artifact availability inspectable.
9. If a previously failed path succeeds after retry, the CraftReport service shall retain the preceding failure and the subsequent recovery result as distinct evidence.

### Requirement 12: Observable Limits and End-to-End Verification

**Objective:** As a project operator, I want reproducible evidence for the actual reporting paths, so that acceptance is based on real outcomes.

#### Acceptance Criteria

1. When a caller inspects supported service/target limits, the CraftReport service shall expose the supported input sizes, content/output limits and refresh capabilities applicable to the selected operation.
2. If an input or output request exceeds an advertised applicable limit, the CraftReport service shall report the exceeded limit before treating the request as accepted work.
3. When reference acceptance verification runs, the CraftReport service shall support a deterministic supplied-data fixture exercising publication, visible grid/line-chart update, live controls, XLSX save/reopen and ordinary MCP inspection with AI disabled.
4. When acceptance evidence is recorded, the CraftReport service shall identify the requirement references, fixture/snapshot, app/version/mode/session, operation results, actual artifact and read-back findings used for that evidence.
5. If the requested path promises visible app behavior, the CraftReport service shall withhold a verified-path claim when evidence covers only an independent headless engine.
6. When a verification run exercises rejection, retry, pause/resume, export-during-refresh or disconnection, the CraftReport service shall record the observed success/partial/failure behavior against the corresponding run.
7. When service, app or output behavior has not been exercised for a declared supported path, the CraftReport service shall identify that path's verification as pending rather than passed.
8. When an agent verifies a critical reference browser journey using synthetic fixtures, the CraftReport verification workflow shall retain screenshots, a review video and browser diagnostics associated with the actual app/session and run/version evidence.
9. If a required browser assertion, unexpected critical browser diagnostic or owned-resource cleanup fails, the CraftReport verification workflow shall record the failure and withhold verified-path acceptance despite any earlier passing assertions.

## Development Constraints and Deferred Decisions

Mandatory engineering direction remains in project steering: typed code, lint/format, pre-commit/CI parity, breadth ownership/lifecycle and reviewed complexity budgets. Numeric cap proposals remain unapproved. Their tools, commands, code boundaries and infrastructure belong in design/tasks, not in these product acceptance criteria.

At requirements generation, core steering files product.md, tech.md and structure.md were absent; existing overview, testing, engineering and breadth steering plus confirmed discovery decisions supplied context. The core files were subsequently consolidated during Design discovery. This context note does not change the acceptance criteria.

Database/ORM choice, internal OOP/functional structure, endpoint/schema syntax, supported payload encodings, browser/native execution mechanism, storage implementation, exact supported-load limits and recovery mechanics remain design decisions. A 10-second reference refresh interval is required; it is not a claimed 10-second maximum end-to-end apply latency.

Local portfolio calculations, detailed GIPS applicability/methods, document pagination and later domain packs require separately bounded requirements before implementation. No formal requirement here establishes financial or regulatory conformance beyond the explicitly recorded reporting scope.
