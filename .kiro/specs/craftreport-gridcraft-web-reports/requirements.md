# Requirements Document

## Introduction

An ordinary software integrator connects accepted supplied-data snapshots and a reusable prepared report to one identified released GridCraft web document. The thin app capability renders one table and one line chart, exposes live controls and freshness, and obtains an actual app-saved XLSX for inspection and fresh reopen. AI is optional. These requirements describe intended behavior; released-browser feasibility and implementation remain unproven.

## Boundary Context

- **In scope:** installed browser capability discovery; same-document owned-region updates; supported semantic presentation; controls using shared lifecycle operations; target conflicts; actual app save, persisted bytes and fresh reopen; scoped evidence and an ordinary-client adopter workflow.
- **Out of scope:** another snapshot store, compiler, scheduler, kernel or general browser framework; financial calculations/GIPS; native/headless-engine substitution for browser effects; other Craft apps; local GridCraft compilation; a designer; library-generated files presented as app exports.
- **Adjacent expectations:** snapshot-runtime supplies retained ordered complete snapshots, immutable run pins and lifecycle/recovery. Report-model/packs supplies prepared content, semantic roles, pack/artifact visibility and release decisions. The kernel supplies common guards, retry/receipt semantics and retained readback. Browser-verification supplies isolated deployment/profile/evidence facilities; its required headed acceptance remains separate and open.

Reader: report integrator/evaluator. Planned guide: `docs/quickstarts/Quickstart_How_to_run_a_live_GridCraft_report.md`; runnable Python recipe/demo: `scripts/examples/run_live_gridcraft_report.py`. These become delivery artifacts after their steps work, not placeholder availability claims.

## Requirements

### Requirement 1: Discovered target and bounded support

**Objective:** As an integrator, I want an identified compatible target and truthful support limits, so that work reaches the intended workbook.

#### Acceptance Criteria

1. When an integrator discovers GridCraft reporting, the GridCraft reporting capability shall return app release/build, browser mode, deployment/session/page/document identity, applicable limits and supported, untested, unavailable or blocked status for each required operation with its reason.
2. When a report binds to a target, the GridCraft reporting capability shall verify the identified document, required table/line-chart/style support and declared owned scope before allowing mutation.
3. If the target is absent, replaced, disconnected, incompatible or cannot be identified unambiguously, the GridCraft reporting capability shall withhold mutation and identify the affected target without selecting another document.
4. If an interaction or file route lacks current evidence of its promised effect for the selected released build, the GridCraft reporting capability shall expose it as untested or unavailable and withhold verified-path status.
5. If a request exceeds advertised size, precision, layout or output limits, the GridCraft reporting capability shall identify the exceeded limit before accepting the requested work.

### Requirement 2: Faithful same-document table and chart

**Objective:** As a reader, I want supplied content in my bound document, so that refresh preserves its meaning and unrelated work.

#### Acceptance Criteria

1. When a complete prepared run is applied, the GridCraft reporting capability shall render its table, line-chart categories/series, title and run identity in the identified document using pinned supplied content and declared ordering.
2. When a later run refreshes a bound report, the GridCraft reporting capability shall update the same document and retained report-owned identities rather than count opening another workbook as refresh.
3. When an update changes owned content, the GridCraft reporting capability shall preserve content outside the declared owned scope, including declared sentinel cells and objects.
4. When content is rendered, the GridCraft reporting capability shall preserve supported value types, units, null gaps, empty-data behavior and literal text, and apply selected supported semantic styles without silently rounding values or evaluating supplied text as formulas.
5. If the target cannot preserve a required value, chart or style behavior, the GridCraft reporting capability shall report that incompatibility before mutation rather than silently coerce or replace it.
6. When an update is reported as a complete visible effect, the GridCraft reporting capability shall compare observed table values/types, chart categories/series, required styles and run markers against that exact pinned run.
7. If external edits or changed document/owned-content identity conflict with a run's preconditions, the GridCraft reporting capability shall identify the conflict, invalidate dependent output findings and withhold verified completion until reconciled.

### Requirement 3: Shared live controls and visible freshness

**Objective:** As a dashboard user, I want visible lifecycle and freshness, so that I can control updates and recognize stale content.

#### Acceptance Criteria

1. When the user activates visible start, pause, resume or stop controls associated with the bound report, the GridCraft reporting capability shall invoke the same authorized lifecycle operation used by ordinary software and display resulting intent, pending state and effect outcome.
2. While live reporting runs, the GridCraft reporting capability shall display configured refresh interval, last attempt/completion times, latest accepted and latest complete accepted versions, selected run and last complete applied version/time as distinct facts.
3. When the reference report uses a 10-second refresh interval, the GridCraft reporting capability shall expose that interval separately from observed end-to-end apply time and pending work.
4. When pause is requested, the GridCraft reporting capability shall immediately prevent new mutation starts and display pause pending until any already-started mutation reaches a reported complete, partial, ambiguous or failed outcome, retaining that outcome alongside the paused/error state.
5. While publications continue during pause, the GridCraft reporting capability shall retain visible document content and expose the latest complete accepted version separately.
6. When a paused report resumes, the GridCraft reporting capability shall apply the highest producer-ordered complete snapshot selected by the shared lifecycle rather than replay paused arrivals.
7. When stop completes, the GridCraft reporting capability shall prevent further automatic mutations until explicit start and preserve any partial or ambiguous prior effect in displayed status.
8. When a configured freshness threshold is exceeded or inputs/target effects fail, the GridCraft reporting capability shall display stale/error status with the triggering measure and last complete applied facts rather than infer currency from a running timer.
9. If a prior update remains active or an older run completes late, the GridCraft reporting capability shall expose the pending/conflict outcome and prevent that completion from replacing a newer verified visible version.

### Requirement 4: Pinned actual app save and independent reopen

**Objective:** As a recipient, I want an immutable XLSX from one complete run, so that I can inspect it independently of the live feed.

#### Acceptance Criteria

1. When an XLSX save is requested, the GridCraft reporting capability shall identify the pinned complete run/snapshot, source document and authorized destination before saving.
2. While save and verification are active, the GridCraft reporting capability shall keep saved table, chart, styles, designation and markers tied to the selected run despite newer publications, and retain that artifact unchanged when live refresh continues.
3. When an app save is reported as persisted, the GridCraft reporting capability shall provide a reference and digest for actual app-emitted bytes read back from the authorized destination, separately from the app's save signal.
4. When save verification completes, the GridCraft reporting capability shall independently inspect those exact saved bytes and reopen them in a fresh GridCraft verifier document/context, comparing values/types, chart references/series, supported styles, draft/validation designation and run identity against the pinned run.
5. If capture, persistence, inspection or fresh reopen fails or cannot be associated with the exact source document/run, the GridCraft reporting capability shall report the affected stage and withhold verified-export status.
6. If a destination already exists without applicable explicit overwrite authorization, the GridCraft reporting capability shall report a conflict without changing the existing artifact.

### Requirement 5: Scoped trust, findings and recovery

**Objective:** As an operator, I want truthful findings and recoverable effects, so that receipts do not overstate assurance.

#### Acceptance Criteria

1. When an operation is inspected, the GridCraft reporting capability shall distinguish preparation, target application, app save, host persistence, byte inspection, reopen and quality evaluation with exact run/target/artifact references and separate pending, complete, partial, ambiguous or failed outcomes.
2. When output is draft-eligible because required reporting checks fail or remain unevaluated, the GridCraft reporting capability shall render and verify the visible DRAFT designation and required-check summary supplied by shared quality policy before claiming draft output.
3. If a request seeks validated output without the shared policy's matching passed required findings, the GridCraft reporting capability shall reject that designation and preserve scoped failed/unevaluated findings without implying numerical-method or standards assurance.
4. When target/artifact content or pinned validation scope changes, the GridCraft reporting capability shall invalidate dependent observations and require new matching evidence before reusing validated status.
5. If mutation or save may have occurred before acknowledgement is lost, the GridCraft reporting capability shall retain an ambiguous/partial outcome and inspect the exact target or artifact before recovery instead of blindly replaying the effect.
6. If the service or target restarts or disconnects, the GridCraft reporting capability shall retain inspectable original run/effect identities, require authorized target revalidation before further mutation and keep failure and subsequent recovery evidence distinct.
7. When access, pack distribution or destination policy denies an operation, the GridCraft reporting capability shall reject it without exposing private template bodies, private data, credentials or unauthorized artifact content.

### Requirement 6: Installed ordinary-client journey and acceptance evidence

**Objective:** As an adopter, I want a reproducible ordinary-client workflow, so that I can evaluate actual capability without AI or private fixtures.

#### Acceptance Criteria

1. When an ordinary MCP or supported REST caller uses the installed capability with AI disabled, the GridCraft reporting capability shall expose discovery, apply/inspect and save operations through the same guarded operation path and retained outcome semantics as visible controls and shared publication/preparation/lifecycle operations.
2. When the public adopter demo runs, the GridCraft reporting capability shall use installed real snapshot-runtime/report-model/app providers with synthetic supplied data to publish identified versions, update one table/line-chart document, exercise visible lifecycle controls, pause/publish/latest-resume, save during a newer publication, and inspect/reopen the actual artifact.
3. When the quickstart and demo are validated, the GridCraft reporting capability shall provide their exact environment/prerequisites, invocations, expected independent observations, one meaningful disconnect or partial-effect recovery case and cleanup of only owned resources.
4. When acceptance evidence is retained, the GridCraft reporting capability shall associate requirement references, source/dependency identities, fixture/snapshot/prepared/run pins, app/build/mode/page/document/profile identities, operation results, actual artifact digest, screenshots, flushed review video and diagnostics with that execution.
5. If a required browser assertion, critical diagnostic, artifact comparison or owned-resource cleanup fails, the GridCraft reporting capability shall preserve failed evidence and withhold acceptance even if earlier stages passed.
6. While required headed browser acceptance has not been performed, the GridCraft reporting capability shall identify it as MANUAL_VERIFY_REQUIRED and scope unattended headless evidence without presenting it as full visible-browser acceptance.

## Feasibility and phase constraints

The official released browser bridge currently evidenced in research supports bootstrap/open and outbound save notifications, not same-document cell mutation/query or an acknowledged save command. Actual browser mutation, reliable chart readback, save correlation and fresh reopen remain feasibility gates. No acceptance criterion is waived. Design must prove a bounded real route before a large production build; failure leaves the affected capability open. Both upstream reviewed designs/tasks are contract inputs, not implemented providers. Engineering activation, exact dependencies, owner paths and unchanged budget enforcement belong to Design/tasks.


