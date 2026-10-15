# Implementation Plan

All executable units target 1â€“3 hours and remain unchecked until fresh task-local verification and independent review. Implement sequentially unless an explicit (P) marker permits otherwise; no marker is currently justified because shared schemas/provider assembly create dependencies. The first useful slice ends at 4.2; later tasks remain required for feature acceptance. Parent alone integrates shared edits, stages, commits with installed hooks and pushes.

Canonical checks: focused `uv.exe run --frozen python -m pytest tests/snapshot_runtime/<affected-file>`, then `uv.exe run --frozen python scripts/check.py --fast` through installed hooks; integration tasks run the affected installed-wheel journey and final `--integration`. Record actual commands/exit codes/source/evidence. Root coordinates shared gate changes with report-model before new source. Per-task tests verify domain effects rather than mirror implementation.

- [ ] 1. Activate exact ownership and durable runtime prerequisites
- [x] 1.1 Apply reviewed ownership, budgets and import boundaries before source expansion
  - Root registers most-specific snapshot-storage ownership of adapters/storage, data/runtime, exact executable recipe/bootstrap paths and fixture/content/docs ownership; applies existing 1,500 capability/50 function/300 module/McCabe 10 defaults without raises.
  - Extend the five-layer import gate narrowly for data, runtime and snapshot-storage; keep runtime free of compiler/theme/framework/storage imports and pure data free of application/framework imports. Only data.ports may import the existing application.service_values Missing/VersionConflict/ServiceUnavailable values. Include exact positive/negative import fixtures and same typed/linted source scope; add no application code.
  - Done when canonical fast checks accept allowed fixtures and reject forbidden dependencies; ledger approval refers to this reviewed Design and shared edits are serialized with sibling activation.
  - _Boundary: ActivationGate; root-owned shared engineering files from File Structure Plan_
  - _Requirements: 1.5, 5.7, 6.1, 6.2_
- [x] 1.2 Resolve the selected storage dependency and create a fail-closed database lifetime
  - Pin SQLAlchemy 2.1.4 and resolve uv.lock against installed Python 3.12; record exact Python/sqlite/dependency versions and installed-wheel import.
  - Implement database/schema version 1, local path validation, OS lifetime lock, explicit nonlegacy transactions, per-connection constraints/configuration and short worker-thread transactions; no custom queue or database engine.
  - Done when a real file commits/rolls back/reopens, foreign keys and durability settings read back, unknown schema fails without replacement and a second actual process cannot open the same host database until the first exits. No PID/lockfile-presence heuristic.
  - _Boundary: DurableSchema; snapshot-storage, pyproject/lock root integration_
  - _Depends: 1.1_
  - _Requirements: 5.1, 5.2, 5.7_

- [ ] 2. Establish exact immutable input contracts
- [x] 2.1 Implement snapshot values and the shared generic version pin
  - Add recursively immutable datasets, fields, scalar/series metrics, SnapshotRef/Snapshot and contracts.pins.VersionPin exactly as reviewed; add typed publication validation with no financial recomputation.
  - Exercise signed 64-bit integer/Decimal precision 38 exactness, null/key/required-field rules, empty typed content, dataset labels/source provenance, ordered metric scalar/series shape, formula-like text and distinct provenance/timings; reject datetime precision above six fractional digits before parsing.
  - Done when invalid values identify the affected rule/location and supplied values roundtrip independently fixed fixtures without coercion or mutable aliases; report-model imports the single agreed value seam.
  - _Boundary: SnapshotValues, VersionPin_
  - _Depends: 1.1_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_
- [x] 2.2 Implement pure report completeness requirements
  - Add agreed immutable requirement/issue values and pure checker, including missing/incompatible fields/units/metric kinds/shapes and required nonnull declarations/values. Empty metric kinds is unrestricted; chart completeness requires explicit numeric series shape; dataset chart fields use declared exact types, never inferred requirements.
  - Done when one accepted snapshot is independently complete for one binding and incomplete for another, with precise locations and no compiler/runtime import.
  - _Boundary: SnapshotValues requirements_
  - _Depends: 2.1_
  - _Requirements: 3.1_
- [x] 2.3 Integrate exact boundary codecs and the snapshot read port
  - Follow the independently reviewed wire-codec-amendment.md: split closed transport schemas from conversion, preserve WireFailure diagnostics in the shared codec, and provide the inward SnapshotFinalizer callable returning finalized Snapshot plus canonical producer bytes. Composition injection and actual persistence remain tasks 4.1/4.2.
  - Reuse PydanticCodec for strict version 1 publication; implement shared scalar encoder/schema-driven decoder, tagged parameter scalars, canonical bytes and digest; expose data.ports.SnapshotReader with existing kernel Missing/VersionConflict/ServiceUnavailable results.
  - Encode all int64 cells/producer versions as decimal strings, decimal values at declared scale, dates/UTC explicitly; reject unknown fields, unsafe coercion and exceeded advertised byte/shape limits. Compute full snapshot.read result bound with maximum-length closed service fields before admission; oversize has no accepted command identity.
  - Done when safe-integer boundaries, digest equivalence/difference, text/int/decimal distinctions and exact output schema pass contract tests; report-model can use the port and scalar codec without its own snapshot serializer.
  - _Boundary: Explicit integration of SnapshotCodecs and SnapshotReadPort_
  - _Depends: 2.1, 2.2_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 6.1_

- [ ] 3. Supply concrete retained kernel guarantees
- [x] 3.1 Implement atomic retry admission and append-only receipt observations
  - Follow journal-reuse-amendment.md: derive exact Receipt/CommandIntent serialization using TypeAdapter with narrowly tested import allowances; retain constrained command/query headers in one journal; implement and fault-test only the known transactional deployment-only v1 to journal-v2 transition, preserving identity/settings and rejecting unknown schema unchanged.
  - Persist trusted scoped intent/retry keys, initial receipt, CAS revisions and query observations; use existing outcome/transition rules and safe immutable serialization.
  - Done when real concurrent equal retries return one operation, changed content/preconditions conflict, losing CAS cannot erase history and reopen returns exact receipts rather than reconstructed success.
  - _Boundary: DurableJournal_
  - _Depends: 1.2, 2.3_
  - _Requirements: 2.2, 2.3, 2.6, 5.1, 5.2, 5.6, 6.2, 6.3_
- [ ] 3.2 Implement one-process version guards and operation-linked resource effects
  - Implement sorted per-resource leases and authoritative version reads, with no SQL transaction held across awaits; assert current immediately before atomic effects.
  - Implement allowed feed/snapshot changes and committed operation/evidence facts for the first slice; add binding/run state effects with 5.1 after those typed values exist. Unknown change shapes fail closed. Leave app mutation to injected app operations.
  - Done when guard loss/cancellation blocks new work, locks release, stale/resource races cannot overwrite winners and postcommit inspection identifies exactly which operation changed state.
  - _Boundary: DurableProviders guard/resource effects_
  - _Depends: 3.1_
  - _Requirements: 2.1, 2.4, 2.5, 2.6, 3.3, 5.2, 5.7_
- [ ] 3.3 Implement immutable result and evidence retention with access-safe readback
  - Persist opaque result/evidence references and exact canonical bytes bound to deployment, subject, operation and versions; independently read and validate digests/pins.
  - Expose the Design's narrow trusted retain_preparation_fact method in existing storage results/evidence files for reporting composition: generic kernel values/canonical closed fact bytes only, retained-command ownership, full declared pins including report-owned resources and independent exact readback. Reuse the evidence table/reader; no reporting imports, public trusted-fact submission, new table or second completion authority.
  - Done when content survives reopen, unauthorized callers cannot inspect private content, deliberate missing differs from unavailable/corrupt storage and unsupported evidence is never marked passed.
  - _Boundary: DurableProviders results/evidence_
  - _Depends: 3.1_
  - _Requirements: 5.1, 5.5, 6.2, 6.3_
- [ ] 3.4 Complete handoff, capability and actual health providers
  - Persist exact trusted RecordedHandoff and installed capability/version/mode decisions; implement allowlisted actual provider probes and default retain-all policy inspection.
  - Done when all nine GuaranteeProviders are concrete, unavailable names fail closed, old owner strings do not prove liveness and production assembly passes focused existing provider conformance without synthetic defaults.
  - _Boundary: DurableProviders handoffs/capabilities/health_
  - _Depends: 3.2, 3.3_
  - _Requirements: 5.1, 5.5, 5.7, 6.1, 6.2_
- [ ] 3.5 Implement explicit stopped-host retention maintenance
  - Implement the design's offline purge in the existing storage provider files, using the database lifetime lock to reject maintenance while a host owns the database; require explicit operator-selected references and return the affected-reference list.
  - Preserve snapshot/retry identity tombstones, feed high-water, deployment epoch and journal evidence; remove only selected retained content without making an old retry eligible for execution. Keep missing content distinguishable from provider unavailability after reopen.
  - Done when a real retained file can be purged only with the host stopped, the returned references match the removed bytes and a reopened provider reports missing content while retaining retry identity, high-water and epoch.
  - _Boundary: DurableProviders retention; src/craftreport/adapters/storage/database.py, snapshots.py, results.py and providers.py under snapshot-storage ownership_
  - _Depends: 3.4_
  - _Requirements: 5.1, 5.5, 5.7, 6.2_

- [ ] 4. Deliver the first durable producer workflow
- [ ] 4.1 Implement ordered publication and exact snapshot queries through the facade
  - Atomically commit validated canonical bytes/high-water/effect facts; handle identical versions, conflict, stale arrivals and normalized retries distinctly.
  - Before the acceptance transaction commits, serialize the exact final canonical snapshot.read result including finalized service timestamps/digest and enforce the descriptor byte cap; a failure retains prior snapshot content and high-water. Preserve 2.3's preadmission worst-case bound and the defensive exact readback check.
  - Register snapshot.publish/read/latest using existing OperationBinding and shared kernel resources, limits, receipts and required persisted-stage evidence.
  - Done when real stored snapshots are immutable, acceptance summaries/times/findings read back, incomplete input remains accepted but is excluded from complete selection and concurrent arrivals expose one feed order.
  - _Boundary: Explicit integration of PublicationOperations and SnapshotStore_
  - _Depends: 2.3, 3.5_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 6.1, 6.3_
- [ ] 4.2 Assemble and verify installed REST publish and MCP read after restart
  - Compose the explicit provider lifetime/capability with open_application/settings.configure, trusted principal policy and installed entry point; no alternate dispatcher or transport route.
  - Start isolated installed host, publish via REST, inspect result/read bytes, stop/reopen same retained database and retrieve/retry through ordinary MCP with AI disabled.
  - Done when identities/digests/exact typed values survive restart and duplicates/stale/conflicts behave as promised; record real storage readback and owned non-forced shutdown. This closes only the first slice, not all lifecycle/app acceptance.
  - _Boundary: Explicit integration of DurableHost, publication and durable providers_
  - _Depends: 4.1_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 5.1, 5.2, 5.7, 6.1, 6.2, 6.3, 6.4, 6.6_

- [ ] 5. Retain binding lifecycle and truthful recovery
- [ ] 5.1 Persist immutable binding requirements and exact run pins
  - Implement typed binding/target/RunPins values and atomic generation/revision changes, complete selection and run retention; generic VersionPins avoid importing report compiler/theme modules. Include injected RunPreparer with PreparedRunInputs/PreparationIssue, retained prepared operation/result identity and exact newly selected snapshot/pin/digest matching before run commit.
  - Own strict runtime.bind/runtime.inspect codecs, OperationBinding registrations and capability updates in the reviewed SnapshotCodecs/BindingRuntime files; extend DurableHost assembly to inject binding services through the existing facade without changing interfaces/application.
  - Done when ordinary REST/MCP discovery exposes bind/inspect, incomplete snapshots cannot start runs, feed/definition/parameter/target changes increment generation and public readback of every reopened run exposes original input/parameter/template/theme/target/scope pins.
  - _Boundary: Explicit integration of BindingRuntime values, BindingStore, SnapshotCodecs, capability registration and DurableHost assembly_
  - _Depends: 4.2_
  - _Requirements: 3.1, 3.2, 3.5, 5.1, 6.2_
- [ ] 5.2 Accept verified app observations conditionally and retain partial history
  - Add injected typed app caller/inspection/cancellation ports and operation/run-linked observed stages; no wire assertion may grant verified completion.
  - Done when exact matching verified observation alone advances applied state, stale generation/target completion loses CAS, and partial/ambiguous effects remain historical without current complete status.
  - _Boundary: BindingRuntime effect observation_
  - _Depends: 5.1_
  - _Requirements: 3.3, 3.4, 3.5, 6.3_
- [ ] 5.3 Implement single-binding scheduling and public start/pause/resume/stop
  - Use one asyncio owner with monotonic 10-second reference opportunities and at most one in-flight preparation/update; select highest complete, obtain new prepared pins for that snapshot through injected RunPreparer, recheck generation plus lifecycle revision/running intent before run commit/start, coalesce arrivals and preserve run pins. A pause while preparation awaits prevents target start.
  - Implement the local lifecycle start fence separately from SQL transactions/kernel leases. Serialize final recheck/run commit plus the actual bounded facade start/operation-ID handoff with pause/stop; release all selection transactions/leases before nested invoke, exclude mutable binding resources from app-start admission, and release the fence before inspection/polling. Record pending pause behind an earlier start; failures/lost acknowledgement retain truthful admission uncertainty without replay.
  - Expose pause pending immediately, preserve accepted publications, stop until explicit start, request cancellation and retain distinct lifecycle/effect/last-error/attempt/completion/version facts.
  - Own runtime.control codec/OperationBinding registration and capability/host updates in the existing reviewed files; controls use the shared facade and existing interfaces/application remain unchanged.
  - Done when ordinary REST/MCP discovery and invocation expose control with retained intent readback, deterministic tests cover every transition and one bounded real 10-second smoke observes selection without claiming apply-latency guarantees or visible app completion.
  - _Boundary: Explicit integration of BindingRuntime scheduler/control, SnapshotCodecs, capability registration and DurableHost assembly_
  - _Depends: 5.2_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 6.1, 6.3_
- [ ] 5.4 Reconcile interrupted operations without replaying uncertain effects
  - Implement the narrow runtime-owned trusted recovery use case over existing application outcome_update, new reconciliation evidence and journal CAS/readback; enumerate recoverable records through an explicit restricted provider reader. Keep the existing application kernel unchanged at its measured 1,449/1,500 LLOC baseline.
  - Suspend recovered running bindings until authorized exact target/session revalidation; retain paused/stopped intent. Inspect committed local effects and injected external observations; original terminal evidence remains immutable.
  - Own runtime.reconcile codec/OperationBinding registration and capability updates; DurableHost startup injects the restricted recovery collaborators, enumerates orphaned work and records recovery-required/ambiguous state before readiness. No ordinary handler receives raw journal writers and existing interfaces/application remain unchanged.
  - Done when ordinary REST/MCP discovery exposes reconcile and readback shows retained recovery observations, startup orphans become inspectable ambiguity, committed publication reconciles once, absent local effects differ from unavailable storage and uncertain external mutation is never blindly retried.
  - _Boundary: Explicit integration of RecoveryUseCase, DurableJournal, BindingRuntime recovery, SnapshotCodecs, capability registration and DurableHost startup_
  - _Depends: 5.3_
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7, 6.2, 6.3, 6.5_

- [ ] 6. Prove recovery and deliver the adopter workflow
- [ ] 6.1 Verify real crash cutpoints and inspectable retention behavior
  - Kill/reopen owned host before/after admission, effect commit, result retention and receipt acknowledgement; independently inspect actual rows/bytes and original/recovery identities.
  - Verify stopped-host explicit purge/tombstone behavior, retained retry non-reexecution, second-host protection, unknown schema and provider failure without volatile fallback.
  - Done when each cutpoint yields one committed acceptance or known absence and uncertain effects stay ambiguous; prior failure/recovery evidence remains distinct and missing/unavailable truthful.
  - _Boundary: Verification of durable providers and trusted recovery_
  - _Depends: 3.5, 5.4_
  - _Requirements: 2.2, 2.3, 2.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.5_
- [ ] 6.2 Verify installed lifecycle and shared-interface contracts
  - Use ordinary REST/MCP clients, real durable providers, a clearly synthetic preparation collaborator retaining fixture results and a synthetic effect collaborator with independently inspected local durable output; do not require report-model completion. Exercise incomplete newest input, pause during preparation, pause/publish/latest-resume, stale completion, stop, restart and ambiguous acknowledgement.
  - Verify permission denials, pending/stage distinctions, no duplicate target effect and exact run/binding/target identities; add affected journey to existing integration command.
  - Race pause against final start handoff in both orders, including a runtime.control binding lease held during app admission: prove no lease inversion/deadlock, no new start after acknowledged pause, truthful pending for the earlier in-flight start, and fence release on start rejection/exception.
  - Done when canonical fast/integration checks and reference journeys pass with retained commands/exit codes/source/dependency/evidence identities; real browser/export acceptance remains explicitly downstream.
  - _Boundary: Explicit installed integration validation_
  - _Depends: 6.1_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
- [ ] 6.3 Deliver and execute the public producer recipe and quickstart
  - Write reusable caller recipe separately from owned demo bootstrap, synthetic fixture and planned quickstart; link indexes. State supported scope, environment/auth/data, exact steps/results, diagnostics/recovery and cleanup.
  - Follow the guide from a clean installed checkout, running the same ordinary client functions with AI disabled. Owned restart mode may stop only the host it launched; operator-host mode never stops that host. Retain public-safe transcripts and one meaningful ambiguity/recovery demonstration.
  - Done when another integrator can reproduce exact published/recovered content and identities through both interfaces, pause/latest-resume and rejection results, with actual evidence and no visible-report/export claim. Record fresh independent feature validation before any feature completion claim.
  - _Boundary: Adopter workflow recipe/bootstrap, fixture, guide and acceptance record_
  - _Depends: 6.2_
  - _Requirements: 1.5, 2.2, 2.4, 2.5, 3.1, 4.2, 4.3, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

## Implementation Notes

- Task 1.1: independently approved by `/root/review_snapshot_gate_1_1`;
  focused Windows tests 21 passed/60 subtests, Ruff/format/Pyright and real
  breadth/import/quality gates passed. RED and final evidence retained under
  `artifacts/snapshot-runtime/task-1.1/`. Exact member imports preserve the
  data.ports exception; recipes remain development-gates, fixture public-packs.
  Scanner +7 LLOC; no application code or budget increase. Installed hook is
  required before this acceptance lands.
- Task 1.2: independent `/root/review_snapshot_database_1_2` approval;
  15 focused Windows tests and Ruff/format/Pyright passed. Installed-wheel
  storage files match current source; actual database reopen retains epoch.
  Python 3.12.10 / SQLite 3.49.1 / SQLAlchemy 2.1.4. Evidence:
  `artifacts/snapshot-runtime/task-1.2/`. Storage +134 LLOC, tests +200;
  application unchanged. Schema v1 currently has the deployment table; provider
  tables belong to later tasks. Cancelled awaits do not roll back a running
  worker transaction; close retains ownership until that transaction finishes.

- Task 2.1: independently approved by `/root/review_snapshot_values_2_1` after
  two validation repairs. Focused Windows suite: 59 passed; Ruff/format/Pyright
  and real gates passed. Five repair regressions first failed. Evidence:
  `artifacts/snapshot-runtime/task-2.1/`. Data 294 LLOC; shared pins 19; tests192.
  Datetime keys compare exact UTC instants without changing source rows; invalid
  identifiers cannot contaminate diagnostic locations. Generic VersionPin.version
  is a nonempty string label; producer_version is positive signed64; digests are
  lowercase SHA256. Task 2.3 must check datetime lexical precision before parsing
  and normalize UTC; wire serialization remains that task's responsibility.


- Task 2.2: independent `/root/review_snapshot_requirements_2_2` approval;
  40 focused Windows tests, Ruff/format/Pyright and breadth passed. Pure
  requirements/checker adds 131 LLOC (data425/1500), with declared kind, shape,
  unit and nonnull semantics, no inference or snapshot mutation. RED evidence
  and fresh checks: `artifacts/snapshot-runtime/task-2.2/`.

- Task 2.3: independently approved by `/root/review_snapshot_wire_2_3` after
  checking complete normalized read-result string limits before admission.
  Fresh 100 wire and 50 existing kernel validation tests, scoped Ruff/format/
  Pyright and gates passed. RED repair: 3 failing lower-string-limit cases.
  Evidence: `artifacts/snapshot-runtime/task-2.3/`; adapters873/data436 LLOC.
  Shared scalar encoding, immutable reader/finalizer ports and canonical bytes
  are accepted; runtime publication, persistence and app effects remain open.

- Task 3.1: independently approved by `/root/review_snapshot_journal_3_1`;
  fresh 59 journal/database and 63 kernel tests, scoped static checks and gates
  passed. File-backed admission/CAS races, transactional rollback and actual
  close/reopen artifact readback verified. Evidence: `artifacts/snapshot-runtime/task-3.1/`.
  Storage365/1500 LLOC; journal does not establish later provider/host readiness.
