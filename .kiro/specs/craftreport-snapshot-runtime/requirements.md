# Requirements Document

## Introduction

CraftReport accepts externally supplied data as immutable producer-ordered snapshots and retains the operation, binding and run state needed to use them after a restart. This bounded specification implements the publication/runtime obligations of umbrella requirements 2, 3, 7 and 11 with shared access and inspection behavior from 10 and 12. Acceptance references use requirement-number.criterion-number.

## Boundary Context

- In scope: complete replacement publications, named typed datasets and imported metrics, durable retry and version identities, completeness inspection, pinned runs, one-process refresh coordination and truthful recovery.
- Out of scope: financial calculations, append/merge/patch ingestion, client SDK/notebooks, report compilation or layout, app mutation, XLSX export, alternate database backends and distributed workers.
- Adjacent expectations: report definitions provide declared input requirements; app integrations provide target/session identity and verified effect observations. Publication validity is independent of completeness for a particular report. Accepting input never proves a visible update or numerical-method validation.
- Umbrella allocation: this feature supplies retained freshness inputs for 7.1–7.3, 7.5–7.6, 7.8–7.9 and 7.11–7.12. GridCraft web reports owns visible status/control rendering and classifying fresh/stale/missing/failed from the run's declared freshness threshold under 7.10; the runtime exposes the required times and versions rather than inventing a separate threshold policy.
- Reader and outcome: an external Python integrator publishes through ordinary REST or MCP, restarts an owned service and retrieves identical values and identities. The delivered guide is `docs/quickstarts/Quickstart_How_to_publish_and_recover_a_snapshot.md`; its runnable recipe is `scripts/examples/publish_and_recover_snapshot.py` with public data in `examples/data/`.

## Requirements

### Requirement 1: Typed publication with preserved meaning

**Objective:** As an external producer, I want precise data acceptance so that downstream reporting preserves supplied meaning.

#### Acceptance Criteria
1. When a producer submits a replacement snapshot, the CraftReport service shall require its feed identity and positive ordered producer version and validate each named dataset's declared field types, nullability, keys, units and row shape before acceptance.
2. If a supplied value cannot preserve its declared type or precision, the CraftReport service shall reject the publication with an affected field/value location and retain prior accepted content.
3. When a snapshot contains imported scalar metrics or ordered series, the CraftReport service shall require metric identity, units, period or as-of time, source reference, producer identity and method version and retain their supplied values and external validation claims without calculating replacements or claiming independent method validation.
4. When publication succeeds, the CraftReport service shall retain dataset labels, column/row/series order, units, formula-like text, distinct observation/generation/receipt/acceptance times and source provenance without unrequested aggregation or executable formulas, and return the accepted snapshot identity, schema/content summary, acceptance time and validation findings.
5. When a caller inspects publication limits, the CraftReport service shall expose supported types, precision, sizes and ordering rules; if a publication exceeds an applicable limit, the service shall reject it before accepting work.
6. If a publication violates declared required fields, key uniqueness, row shape or input-value rules, the CraftReport service shall report the affected location and violated rule and retain the previously accepted content.

### Requirement 2: Ordered immutable snapshots and safe retry

**Objective:** As a producer, I want one retained identity for each accepted version so that retries and late arrivals cannot corrupt the feed.

#### Acceptance Criteria
1. When a valid new producer version is accepted, the CraftReport service shall atomically retain its immutable content identity and advance that feed's latest accepted version without changing earlier versions.
2. When a caller repeats a request with the same retry identity and normalized content/preconditions, the CraftReport service shall return the existing operation and retained result without accepting or applying it again.
3. If a retry identity is reused with different content/preconditions, the CraftReport service shall return a conflict without applying that request.
4. If an unseen publication is older than its feed's latest accepted producer version, the CraftReport service shall reject it as stale without changing accepted or applied versions.
5. If a producer version already exists with different content, the CraftReport service shall return a version conflict without replacing content; when that version has identical content, the CraftReport service shall return its retained snapshot identity without moving the feed backwards.
6. When concurrent publications or retries compete, the CraftReport service shall retain one authoritative acceptance order and expose the winning identities or conflicts consistently through both supported interfaces.

### Requirement 3: Completeness, pins and conditional progress

**Objective:** As a report operator, I want separate accepted, complete, selected and applied states so that partial work cannot become a complete report.

#### Acceptance Criteria
1. When a caller evaluates or selects a snapshot against declared dataset/field/metric requirements, the CraftReport service shall identify missing or incompatible locations, distinguish publication acceptance from report completeness and exclude incomplete snapshots from complete execution during start, refresh and resume.
2. When a report run is selected, the CraftReport service shall pin snapshot feed/version/content identity, definition/version, resolved parameter values, template/theme versions, validation scope and exact target/session/document identity before dependent work starts.
3. When an integration reports a complete verified effect for a selected run, the CraftReport service shall advance the binding's applied version only if the binding generation, selected run and target identity still match.
4. If an integration reports a partial, failed or ambiguous effect or an older completion conflicts with a newer binding generation, the CraftReport service shall retain that observation and withhold current complete-applied status.
5. When a binding changes feed, target, definition, parameters, template/theme or required inputs, the CraftReport service shall create a new binding generation and invalidate dependent current-completion claims without modifying prior run evidence.

### Requirement 4: One-process refresh lifecycle

**Objective:** As a report user, I want predictable pause/resume and stop behavior so that incoming data does not undo my control choice.

#### Acceptance Criteria
1. While a supported live binding is running, the CraftReport service shall provide refresh selection opportunities at its configured interval including the 10-second reference interval, coordinate at most one active update for that binding and expose cadence separately from end-to-end apply latency.
2. When a pause is requested, the CraftReport service shall immediately stop starting updates for that binding, expose pause pending while an active effect resolves and continue accepting valid publications; while the binding is paused, the service shall start no new target updates.
3. When a paused binding resumes, the CraftReport service shall select the highest producer version in its bound feed that satisfies its declared input requirements, skipping intermediate versions and retaining incomplete-version diagnostics.
4. When a binding is stopped, the CraftReport service shall cancel future selection and request cancellation of owned pending work while reporting any already-started effect according to its observed outcome, and prevent further automatic updates until an explicit start.
5. If a newer complete version arrives during an update, the CraftReport service shall keep the in-flight run pinned and coalesce later selection to the highest complete version without overlapping target updates or changing the in-flight input.
6. When a binding is inspected, the CraftReport service shall expose running/paused/pause-pending/stopped/recovery-required intent, last attempt/completion times, latest complete accepted and last complete applied versions/times, pending work and last error, preserving partial or ambiguous effect status alongside lifecycle intent.

### Requirement 5: Durable state, recovery and retention

**Objective:** As an operator, I want truthful restart visibility so that recovery does not duplicate uncertain external actions.

#### Acceptance Criteria
1. When the service restarts using its retained deployment state, the CraftReport service shall retrieve accepted snapshot content, retry identities, receipts/results, run pins, binding generations and lifecycle intent with the same identities and values.
2. If publication is interrupted before or after durable commit, the CraftReport service shall expose either no accepted content or the one committed snapshot and reconcile its existing operation without creating a second acceptance.
3. If target work may have started before interruption or acknowledgement loss, the CraftReport service shall retain an ambiguous effect until an authorized inspection/reconciliation establishes the actual target state and shall not blindly replay the action.
4. When runtime bindings are recovered, the CraftReport service shall preserve pause/stop intent and require target/session revalidation before scheduling active work or claiming a live target.
5. When retention policy is inspected, the CraftReport service shall expose its scope and effect on snapshot, retry, result, run and evidence availability; if content is unavailable or deliberately removed, the service shall distinguish known missing content from provider unavailability and withhold reproducibility claims.
6. When recovery follows a failed attempt, the CraftReport service shall retain the preceding failure and subsequent reconciliation evidence separately without rewriting terminal observations.
7. If configured durable storage is unavailable, incompatible or already owned by another host, the CraftReport service shall fail closed without replacing retained state or substituting volatile providers.

### Requirement 6: Ordinary clients, access and verifiable adoption

**Objective:** As an integrator, I want one documented software-callable workflow so that I can adopt the feature without AI or private dependencies.

#### Acceptance Criteria
1. When an ordinary REST or MCP caller publishes, reads or controls a binding, the CraftReport service shall apply the existing shared authorization, retry, precondition and receipt semantics with AI disabled and expose structured failure/recovery diagnostics.
2. If a caller lacks access to a feed, snapshot, binding, run, receipt or retained result, the CraftReport service shall reject the operation without exposing protected data or provenance.
3. When an operation is accepted but its effect is unfinished, the CraftReport service shall expose an inspectable pending operation identity and separate input acceptance, state persistence and externally observed effect stages.
4. When the adopter follows the guide and runs the public example against an isolated owned host, the CraftReport verification workflow shall publish and read back exact typed values through REST and MCP, restart the host and read back identical identities/content, exercise duplicate/stale/conflicting input and pause/resume selection, and retain commands, receipts and independent storage/read-back evidence.
5. When the recovery example interrupts an effect, the CraftReport verification workflow shall demonstrate ambiguity without duplicate mutation, reconcile using independently observed state and clean up only resources owned by that example.
6. If browser/native mutation or export has not been exercised, the CraftReport service and guide shall identify those paths as outside this feature's verification rather than claim visible-report or verified-artifact acceptance.
