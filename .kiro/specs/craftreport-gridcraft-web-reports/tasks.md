# Implementation Plan — draft for independent task-graph review

All tasks are unchecked. This file is a proposal, not `tasks.md` and not task approval. Independent graph sanity review must PASS before root finalizes the plan. Each executable item is a bounded 1–3 hour unit; a failed feasibility attempt is a stopping gate, not permission to build an alternative route. No `(P)` markers are justified because the app contracts, fact/provider state, driver lane and assembly share prerequisites. Parent alone integrates shared files, commits with installed hooks and pushes.

Canonical validation: focused `uv.exe run --frozen python -m pytest tests/gridcraft/<affected-file>` after setup, canonical `uv.exe run --frozen python scripts/check.py --fast` through installed hooks, and affected installed `--integration`/real headless browser journeys for integration changes. Record exact invocation, exit code, source/wheel/dependency/release/profile and evidence directory. Reuse fresh matching checks rather than run duplicate suites alongside heavy browser timing. No task is complete without required fresh checks and independent task-local review.

- [ ] 1. Activate exact app ownership, default budgets and dependency boundaries
  - Root activates the reviewed gridcraft package, app tests, resources, exact executable caller/launcher, guide and deployment ownership before app source expansion. Apply existing 1,500 capability/50 function/300 module/McCabe10 defaults, with no increases; reconcile shared executable-owner totals with both upstream specs.
  - Extend typed/linted/build/import checks narrowly for the app package and example; pure core/app values cannot import concrete browser/workbook SDKs, application core receives no additions, and production app cannot import fixture-verification drivers. Keep allowed composition and exact SDK exceptions local; include positive/negative gate fixtures.
  - Done when ledger/budget/import/typed scope recognizes the exact owners, forbidden imports still fail and canonical fast checks pass. A configured gate is not described as enforced until actually run.
  - _Boundary: ActivationGate; root-owned shared engineering files from Design_
  - _Requirements: 1.4, 1.5, 6.1, 6.4_

- [ ] 2. Resolve released-app and library prerequisites without building GridCraft
  - Pin XlsxWriter3.2.9/openpyxl3.1.5 and the reviewed Playwright1.64.0 dependency path, resolve exact transitive versions and record Python/Chromium compatibility. Root serializes pyproject/lock changes with snapshot storage work. Package metadata/resources use the approved ordinary wheel layout; no generic framework or empty modules are added.
  - Reuse the downloaded official v0.7.0 archive, verify checksum and loaded JS/WASM hashes, configure the isolated same-origin parent/app/facade deployment and exact Windows headless profile. Debian WSL serves Docker only; no local Rust build, foreground browser or X server.
  - Done when selected libraries import in the locked environment and the exact isolated released page/bridge readiness loads with retained diagnostics and owned cleanup. This proves prerequisites only, not live reporting or an installed working app capability.
  - _Boundary: Packaging and host-configuration prerequisite integration_
  - _Depends: 1_
  - _Requirements: 1.1, 1.4, 6.4, 6.5, 6.6_

- [ ] 3. Prove the bounded real browser route before production expansion
  - Use a tiny literal test-only workbook to bootstrap once through the selected official bridge, observe marker/table/line chart/styles/outside sentinel, perform two real UI value edits in that same document and inspect actual chart/category/series effects. Include literal formula-marker text and a null gap in the minimum supported profile.
  - Invoke actual released Save, correlate the official outbound bytes under one armed lane, persist/read back private scratch, independently inspect and reopen those exact bytes in a separate GridCraft context. Deliberately modify owned content and prove the next mismatched update rejects before mutation. Resolve the recorded chart-before/category-copy problem against this route; no screenshot-only or source-equivalence pass.
  - Done when current real evidence proves every promised minimal effect and records the support subset, dimensions/types/styles/bounds, commands/exit code, screenshots/flushed video/diagnostics and observed owned cleanup. This test-only fixture does not require or pretend to implement upstream production providers.
  - If any required effect is unproven, stop tasks4–16, record untested/unavailable status and return the route to independent Design review. No fallback engine, repeated-open refresh, custom unrestricted bridge or larger driver build is authorized.
  - _Boundary: Feasibility; isolated actual released-browser test only_
  - _Depends: 2_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 2.6, 2.7, 4.3, 4.4, 4.5, 6.4, 6.5, 6.6_

- [ ] 4. Implement the admitted fixed-shape mapping and installed value contracts
  - Wait for accepted snapshot-runtime2.1–2.3 and report-model2.1–4/7 value+codec tasks; consume their exact Snapshot/RunPins/PreparedReport/policy values without copying schemas or changing frozen upstream interfaces. Runtime values additionally require its5.1 before integration that uses RunPins.
  - Implement strict app settings/target/layout/observation/artifact values, admitted mapping plan, explicit text-safe one-time XlsxWriter bootstrap and support descriptor from task3's observed subset. Fix shape/types/series references at bind; reject dimension/precision/unsupported-style/empty-data changes before admission, with no coercion/truncation.
  - Build/install the actual app wheel/resources and verify public imports/descriptor packaging. Done when independently fixed literals compare exact mapped values/order/types/styles/markers, malicious formula/URL text stays text and installed package identity matches its manifest. Unsupported mappings remain explicit.
  - _Boundary: AppValues and WorkbookMapping integration; exact package files in Design_
  - _Depends: 3_
  - _Requirements: 1.2, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 6.1_

- [ ] 5. Retain immutable app external-effect facts with exact read-back
  - Implement operation-linked intent/observation facts and current-observation index under the private configured root, using exclusive canonical writes, fsync and independent digest readback. Bind trusted subject/deployment/operation/run/target identity; no caller paths, journal/receipt replacement or upstream table changes.
  - Exercise real-file reopen, torn/missing/corrupt facts/indexes and crash cutpoints before/after external intent/observation retention. Missing differs from unavailable; orphans remain recovery-required, never reconstructed success.
  - Done when immutable fact identities survive reopen with access-safe exact contents, unexpected corruption is unavailable and all prior failure/unknown facts remain retained. Media/byte references resolve only through authorized opaque IDs.
  - _Boundary: AppFacts_
  - _Depends: 4_
  - _Requirements: 5.1, 5.4, 5.5, 5.6, 5.7, 6.4_

- [ ] 6. Compose exact app resources, evidence and guards with real upstream providers
  - Wait for accepted snapshot-runtime3.1–3.4/4.2 real provider/host tasks. Route only app document/artifact kinds and evidence namespace; delegate upstream resources/effects/health without altering their authority. Preserve the sole kernel journal/results/handoffs.
  - Implement complete-set outer sorted locks then delegated non-app locks, reverse release/cancellation and actual-current checks. Every invocation enters the composed provider, never mixed raw guards; local stored versions are observations, not a fence on external users. Unknown app generic changes fail closed.
  - Done when real mixed-resource reverse requests, cancellation/stale CAS and principal isolation pass; every completion/stage/reconciliation evidence ref has the exact full declared completion pin set. Missing/altered upstream pins must make the kernel reject completion, while correct full-set evidence passes.
  - _Boundary: AppProviders integration with existing GuaranteeProviders_
  - _Depends: 5_
  - _Requirements: 1.3, 2.7, 5.1, 5.4, 5.5, 5.6, 5.7, 6.1_

- [ ] 7. Implement the released browser session and same-document observations
  - Promote only the task3-proved narrow route into the app package: exact context/page/frame/navigation/build/profile/marker identity, one bootstrap, selected-reference/nonce reads, chart/reference/style observation and bounded official message capture. Never import/copy fixture state or create a generic automation framework.
  - Add read-only bounded workbook-byte inspection for actual app inspection saves, comparing source types/values/chart/styles plus supported outside signatures; no openpyxl resave. Record native dirty/saved side effects separately from host persistence/user export.
  - Done when actual released-browser observations bind one document/run, wrong page/marker/build/unrecognized geometry or multiple/late messages fail closed, and scratch bytes independently match observed content. Unknown outside structure conflicts before mutation.
  - _Boundary: BrowserDriver observation and ArtifactVerification scratch integration_
  - _Depends: 6_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 2.4, 2.6, 2.7, 5.1, 6.4, 6.5_

- [ ] 8. Apply pinned content through one guarded real document lane
  - Implement before-signature/UI checks, actual bounded keyboard/formula-bar edits to owned addresses and after UI/chart/app-byte comparison in the same document. Serialize apply/verify/save through one lane; do not alter chart structure or outside regions.
  - Recheck real target/owned/outside identities around effects, record intent before dispatch and immutable observed facts after. Pre-dispatch failures have no effect; after-dispatch timeout/identity/conflict failures remain partial/unknown, never a rollback over user edits.
  - Done when two pinned snapshots change the same document/table/chart with exact types/styles/markers, outside sentinel cell/object remains unchanged, deliberate external edits conflict and a partial update never grants verified-complete/app-applied status.
  - _Boundary: BrowserDriver mutation_
  - _Depends: 7_
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.9, 5.1, 5.4, 5.5_

- [ ] 9. Register guarded app operations and consume real preparation/runtime pins
  - Wait for accepted report-model8/10 and snapshot-runtime5.1–5.4 real operations/lifecycle/recovery tasks. Register discovery/open/apply/verify/inspect with existing strict codecs, limits, resource guards, retry semantics and retained results; export remains explicitly unavailable until its implementation.
  - Inject real RunPreparer calling public reports.prepare and exact retained readback; map only reviewed PreparedRunInputs. AppOperationCaller invokes public app operations and converts canonical receipts plus trusted full-pin evidence into exact EffectObservation/cancellation, without advancing bindings itself or nesting a held resource lease.
  - Done when installed ordinary REST/MCP clients discover and invoke the shared path, mismatched/missing prepared pins or public passed flags reject, duplicate retry does not reapply, and only exact verified run/target/generation evidence can advance runtime applied state.
  - _Boundary: AppOperations and AppComposition integration_
  - _Depends: 8_
  - _Requirements: 1.5, 2.6, 2.7, 3.9, 5.1, 5.3, 5.4, 5.7, 6.1_

- [ ] 10. Deliver visible shared lifecycle controls and truthful freshness
  - Add the packaged native labelled control panel using existing public invocation/inspection endpoints, explicit authentication boundary, accessible focus/status and read-only state polling. No embedded credentials, private data transcript or alternate scheduler.
  - Click actual start/pause/resume/stop controls in the isolated browser. Show interval/attempt/completion and accepted/complete/selected/applied facts distinctly, pause immediately blocks new starts including pending preparation, paused publications retain visible content, resume selects highest complete, stop blocks until explicit start.
  - Done when real installed runtime/app observations prove all transitions, 10-second opportunity setting remains distinct from apply latency, stale threshold identifies its measure, and partial/ambiguous/failed outcomes remain visible with pause/error. A deliberately disconnected control must fail its critical test before restoring and proving the correct wiring.
  - _Boundary: ControlPanel lifecycle integration_
  - _Depends: 9_
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.1, 6.5_

- [ ] 11. Stage pinned actual app saves and independently reopen exact bytes
  - Implement export save capture under the same document lane with exact current complete run precheck; a newer publication may be accepted but cannot mix into captured content. Freeze private operation-owned bytes, release live lane after capture and inspect/reopen those exact staged bytes in another GridCraft context.
  - Enforce byte/ZIP/XML/resource bounds and no external/macro/executable links before parsing. Compare actual values/types/chart references/series/styles/run/designation, preserve original bytes and distinguish capture, scratch persistence, inspection and reopen stages.
  - Done when export-during-publication preserves one pinned run through fresh actual app reopen, wrong-run/multiple-message/corrupt/unavailable/reopen failures withhold verified export, and no requested destination has been changed during staging.
  - _Boundary: ArtifactVerification staging/reopen_
  - _Depends: 10_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.4, 6.4, 6.5_

- [ ] 12. Publish only policy-permitted verified draft or final validated bytes
  - Activate gridcraft.export through explicit integration of its strict request/result codecs, existing OperationBinding, exact document/run/artifact/destination resource declarations and descriptor limits/evidence policy. Admit only the authorized pinned current complete run, matching retained prepared/result pins and destination expected version/overwrite policy; use the existing shared kernel guards/retries/stage/result semantics. Transition descriptor availability from unavailable to supported only after tasks11–12's actual route and publication checks pass.
  - Use existing quality evaluate with trusted matching observations; render and verify DRAFT+summary for permitted draft. For validated requests, privately verify provisional eligibility, apply scoped designation, then capture/stage/inspect/reopen and re-evaluate against final target/artifact pins. External methodology/compliance claims cannot grant internal checks.
  - After final applicable checks, reassert destination guard/authorization/expected digest and exclusive-create or explicitly permitted atomic replace of the exact verified staged bytes; fsync/read back destination digest and retain final publication facts. Prepublication failure or conflict leaves existing/absent destination unchanged.
  - Done when blocked validated requests expose no published validated artifact, marked drafts preserve their findings, final published bytes equal final verified digest and continuing live input never changes the artifact. Postpublication lost acknowledgment/readback failure remains ambiguous/failed persistence with its possible real write, never absent-success or blind retry.
  - Installed ordinary REST/MCP discovery and invocation must expose this same export operation and exact descriptor transition; inspect retained preparation/capture/staging/inspection/reopen/policy/publication stages and structured failure readback. Wrong pins/destination authorization/version reject before the effect, retries return the original operation without repeating save/publication, and failed stages cannot acquire a verified-export receipt.
  - _Boundary: AppOperations, ArtifactVerification and policy publication integration_
  - _Depends: 11_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.7, 6.1_

- [ ] 13. Reconcile real interruptions and restore only authorized exact targets
  - Integrate runtime.reconcile with fresh guarded gridcraft.verify and immutable original effect facts. Crash/disconnect before/after edit, capture, staged verification, publication and acknowledgment; do not replay uncertain app operations.
  - Restart invalidates handles/requires recovery, retains original run/target/artifact evidence and paused/stopped intent, and resumes only after authorized exact marker/build/document revalidation. Unknown/replaced target remains unavailable/conflicting; corruption never regenerates passed evidence.
  - Done when real retained state and browser/artifact observations distinguish known absence, partial effect, committed publication and ambiguity; preceding failure and later recovery have distinct linked evidence and no duplicate insert/save occurs.
  - _Boundary: AppComposition recovery integration_
  - _Depends: 12_
  - _Requirements: 1.3, 2.7, 3.7, 5.1, 5.4, 5.5, 5.6, 6.5_

- [ ] 14. Prove the installed ordinary-client reference journey with real providers
  - Assemble installed core/app wheels, accepted production snapshot/runtime/report providers, configured public synthetic pack and isolated released browser. Invoke ordinary REST/MCP with AI disabled: publication, reusable preparation, same-document apply, actual panel controls, incomplete/newer/out-of-order input, latest-complete resume, export while publishing and evidence inspection.
  - Independently compare displayed table/chart, pinned run and actual staged/published/reopened artifact; exercise permissions, retries, destination conflict and one real disconnect/partial recovery. No synthetic GuaranteeProviders/preparer may replace acceptance-critical providers.
  - Done when canonical fast/integration and affected real browser checks pass with matching source/wheel/dependency/build/page/document/run/artifact identities, full evidence-version sets, screenshots/flushed video/diagnostics and observed owned cleanup. Retain failed evidence; required headed acceptance stays MANUAL_VERIFY_REQUIRED.
  - _Boundary: Installed acceptance integration_
  - _Depends: 13_
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.4, 6.5, 6.6_

- [ ] 15. Deliver and execute the adopter guide and reusable Python demo
  - Write the planned Quickstart_How_to_run_a_live_GridCraft_report guide, package support notes, public caller/owned launcher and index links. Lead with integrator task/result and one small public fixture; distinguish current support from pending coverage and direct app edits from facade reusable/pinned lifecycle behavior.
  - Follow exact guide commands from a clean installed setup through ordinary caller functions with real providers and AI disabled. Include explicit environment/auth/hosts/data, expected independent observations, one recovery case and cleanup only of resources launched by the demo; operator-host mode must leave that host alive.
  - Done when runnable recipe reproduces the real table/chart/control/save/reopen journey with retained command/exit/evidence identities, safe public transcript and documented limitations; no placeholder how-to or synthetic-provider guarantee claim is published.
  - _Boundary: Adopter workflow executable recipe/launcher and documentation integration_
  - _Depends: 14_
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

- [ ] 16. Independently validate the bounded feature and umbrella integration status
  - Run kiro-verify-completion/kiro-validate-impl with fresh matching-source evidence, approved requirement coverage, exact measured budgets/import gates and installed critical path outcomes. Verify guide/example links and actual execution, failure/recovery history, artifact persistence/reopen and owned cleanup.
  - Root reconciles umbrella scope/status and accepted evidence without changing its requirements or hiding open fronts. Review all blocked tasks and the independent headed browser requirement; headless app acceptance cannot close the full browser spec.
  - Done when the independent verdict explicitly states GO/NO-GO/MANUAL_VERIFY_REQUIRED by exercised scope with evidence identities, and no missing feasibility/provider/real-effect check is marked passed. Full feature completion requires all mandatory applicable gates; manual headed work remains open under the current unattended restriction.
  - _Boundary: Final app feature validation and umbrella status integration_
  - _Depends: 15_
  - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_
