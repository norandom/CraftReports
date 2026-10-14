# Implementation Plan

Requirements and Design are owner-approved. This plan awaits separate Tasks
approval. All acceptance work is mandatory. Design's File Structure Plan defines
exact file ownership; every normal task stays within its named boundary, and
tasks crossing those seams are explicitly integration work.

Each executable task is planned as a bounded 1â€“3 hour unit. Task-local review,
fresh relevant checks and a commit follow each accepted task. Parallel markers
authorize only non-overlapping implementation after declared prerequisites;
heavy runtime verification and shared gate/configuration changes run serially.
The existing probe on 8871 is preserved.

## 1. Establish the approved tooling foundation

- [x] 1.1 Install and verify the isolated browser tooling environment
  - Activate the Design-approved tooling owner and limits before new source lands;
    retain whole-scope Ruff, strict typing, ownership and pre-commit enforcement.
  - Resolve the exact development dependencies, install matching Chromium and
    record Python/browser/OS identities. Keep the production wheel unchanged.
  - Implement targeted import checks preventing production dependence on the
    harness and preventing tooling from importing production implementation.
  - Done when a clean locked environment imports the selected tools, the actual
    hook passes and disposable forbidden-import cases fail the boundary gate.
  - Validation: canonical fast checks, installed hook and minimal browser launch;
    missing display/tooling is a named failed prerequisite, not a silent skip.
  - _Boundary: Development-gates integration_
  - _Requirements: 2.6, 3.5, 3.6, 6.6, 8.1_

- [ ] 1.2 Define validated run identities, findings and immediate resource ownership
  - Implement the Design's typed records, success/rejection envelopes and config
    validation, including owned/external deployment choice and positive deadlines.
  - Give run, context, page generation, fixture and output distinct identities;
    preserve pending, unresolved and unexecuted states.
  - Establish immediate acquisition registration before any runtime setup can
    fail, including partial-start resources and cancellation intent.
  - Done when invalid config is rejected and a rejected partial acquisition retains
    its cleanup token without producing a success payload.
  - Validation: focused contract/state tests and canonical fast checks.
  - _Boundary: Values and Journey ownership foundation integration_
  - _Requirements: 2.1, 2.4, 5.1, 5.6, 6.1, 6.2, 7.1, 7.4_

- [ ] 1.3 Prepare and independently review the synthetic workbook expectations
  - Retain the small single-sheet XLSX, hash and authoring provenance described by
    Design; keep the one-time authoring tool outside runtime dependencies.
  - Freeze known typed cells, marker/sentinels, B3 20-to-25 edit, line-chart title,
    literal series name, category/value references and presentation expectations.
  - Done when independent ZIP inspection confirms the fixture matches those
    expectations before any candidate output is used as an oracle.
  - Validation: fixture semantic/provenance review; source checks if executable
    authoring helpers are needed, with their source counted in the capability.
  - _Boundary: FixtureManifest_
  - _Requirements: 3.1, 3.4, 4.5, 8.2_

- [ ] 1.4 Inspect the fixed fixture and saved XLSX semantics without rewriting bytes
  - Follow sheet/drawing/chart/style relationships and compare declared cells,
    types, sentinels, series/category formulas and presentation semantics.
  - Support equivalent inline/shared strings and normalized references; bound
    archive/XML inputs and reject duplicate/traversal/external/DTD content.
  - Done when the original fixture passes and deliberately wrong cell types,
    marker, chart bindings and missing chart fail independently.
  - Validation: focused real-ZIP fixture tests and canonical fast checks.
  - _Boundary: ArtifactInspector_
  - _Depends: 1.3_
  - _Requirements: 4.5, 4.7_

## 2. Establish owned runtime access and minimum recording

- [ ] 2.1 Acquire and identify the latest official prebuilt application
  - Resolve official stable latest metadata, enforce minimum version and a unique
    web asset; verify trusted expected digest on download and cache reuse.
  - Extract safely under bounded paths/sizes and retain HTML/JS/WASM hashes;
    cache acquisition failures cannot relabel an old release as latest.
  - Done when the real archive is verified without compiling and corrupted,
    missing or too-old selections produce specific non-passing findings.
  - Validation: acquisition fault tests, one official download/reuse and fast checks.
  - _Boundary: Release_
  - _Requirements: 1.1, 1.2, 1.3, 6.6_

- [ ] 2.2 Select an owned Compose deployment or verify an explicit external target
  - Use the existing static recipe with a unique project, verified absolute mount,
    labels and available port; preserve 8871 and unrelated services.
  - Implement Debian WSL and native Linux command/path handling plus external
    origin/build-manifest selection. External resources are never adopted/stopped.
  - Record bind separately from browser origin; compare served assets to selected
    hashes. Register created resources immediately and close only owned identities.
  - Done when an owned service exposes matching assets and shuts down cleanly;
    external mode can verify the supplied target without lifecycle mutations.
  - Validation: owned deployment smoke, external-mode observation, project/port/
    build mismatch cases, cleanup inspection and fast checks.
  - _Boundary: Deployment_
  - _Depends: 2.1_
  - _Requirements: 1.4, 2.2, 2.3, 7.1, 7.2_

- [ ] 2.3 Integrate isolated browser startup with minimum evidence and cleanup
  - Create owned fixed-profile contexts with diagnostics before navigation and
    explicit video recording; verify loaded asset hashes and usable canvas.
  - Exercise the disclosed picker-capability removal, confirm absence and record
    its original state. Never install a fake picker or modify app/document effects.
  - Honor headed/headless selection; expose a real visible window for local review.
  - Register browser/context resources immediately, close them on startup failure,
    retain failure screenshot/diagnostics and finalize minimal video evidence.
  - Done when actual readiness is distinguishable from HTTP health, and missing
    app assets/display/clipboard prerequisites stop without a passing journey.
  - Validation: real readiness run, startup-failure cleanup and canonical fast checks.
  - _Boundary: BrowserDriver, Evidence and Journey startup integration_
  - _Depends: 1.2, 2.2_
  - _Requirements: 1.5, 1.6, 2.4, 2.6, 3.5, 3.6, 3.7, 5.3, 5.4, 6.6, 7.1_

## 3. Prove the released-browser route before expanding the harness

- [ ] 3.1 Open the known fixture, perform one edit and observe fresh real UI values
  - Exercise the actual Open chooser and verify marker/before values in the
    selected workbook. Calibrate real accessibility or canvas geometry controls.
  - Use genuine Name Box navigation, formula-bar commit and real Copy readback,
    with a per-observation clipboard nonce and independently checked reference.
  - Stop on unexpected page/build/marker/generation; issue the edit once and leave
    timeouts after possible input unresolved.
  - Done when B3 visibly changes from 20 to 25 and unchanged marker/sentinels are
    freshly observed in the same identified page, with checkpoint screenshots.
  - Validation: actual browser before/after journey and mismatch/timeout cases;
    input dispatch or stale clipboard alone cannot pass.
  - _Boundary: BrowserDriver_
  - _Depends: 1.3, 2.3_
  - _Requirements: 2.4, 2.5, 3.1, 3.2, 3.3, 5.2, 6.2_

- [ ] 3.2 Establish independently reviewed live chart and presentation observations
  - Verify the one chart's title/placement, category field, series name and selected
    values-range outline against visible B2:B4 geometry.
  - Capture before/after chart plots and freeze independently reviewed profile
    crops, masks and thresholds; keep categories/sentinels tied to the same chart.
  - Reject unknown geometry/build/graphics profiles and prohibit automatic candidate
    baseline acceptance. Saved OOXML cannot replace the live source-binding check.
  - Done when the changed middle point, range outline and declared presentation
    checks are repeatable; inaccessible/ambiguous binding leaves 3.4 blocked.
  - Validation: real visual/clipboard observations plus wrong crop/range/profile
    rejection; review both local and unattended baseline prerequisites.
  - _Boundary: VisualOracle and BrowserDriver observation integration_
  - _Depends: 3.1_
  - _Requirements: 3.4, 3.6, 3.7, 5.2, 6.6_

- [ ] 3.3 Capture a real Save download, inspect it and reopen its exact bytes
  - Arm download capture before actual Save, persist to an exclusive destination,
    record route/size/hash and inspect against expected edited fixture semantics.
  - Protect existing destinations and treat native picker, cancel/no file/timeouts
    as non-passing; do not replay Save to resolve an ambiguous outcome.
  - Open the retained artifact in a fresh isolated recording context/page and
    repeat the real cell/chart checks with a new generation/artifact association.
  - Done when a complete real round trip agrees across visible values, actual
    stored types/bindings and fresh-page reopen without rewriting the output.
  - Validation: actual Save/inspect/reopen journey, destination conflict and no-file
    checks; retained persisted/reopen screenshots and finalized videos.
  - _Boundary: BrowserDriver, ArtifactInspector and Journey round-trip integration_
  - _Depends: 1.4, 3.2_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.2_

- [ ] 3.4 Prove route sensitivity and retain the first bounded feasibility result
  - Suppress only edit dispatch in a disposable test variant; fresh readback must
    detect unchanged B3 and produce a failed attempt with review evidence.
  - Restore real dispatch in a distinct run and repeat the complete round trip.
  - Record actual route/profile capability findings and first-slice source budget.
    Stop expansion if required routes are blocked or the approved cap cannot fit;
    seek an owning design/budget correction rather than manufacturing success.
  - Done when independent review can inspect both the expected failed challenge
    and restored successful journey, including owned cleanup.
  - Validation: paired real sensitivity/recovery runs and relevant fast checks.
  - _Boundary: Journey feasibility integration_
  - _Depends: 3.3_
  - _Requirements: 3.7, 6.3, 6.4, 6.5, 6.6, 7.3, 7.5_

## 4. Complete evidence and lifecycle accountability after feasibility

- [ ] 4.1 (P) Finalize inspectable evidence and scoped verdict reduction
  - Bind requirement/source/fixture/app/browser/page/artifact identities to stage
    findings; record dirty content hashes when a clean revision is unavailable.
  - Retain named checkpoints, sanitized diagnostics and distinct unexecuted
    findings; fail unexpected page/console/critical-request errors.
  - Write the final packet atomically after cleanup; hash all referenced files,
    decode required finalized video and reject missing/truncated evidence.
  - Done when the packet independently distinguishes readiness, edit, persistence,
    inspection, reopen and cleanup, and no incomplete packet yields VERIFIED.
  - Validation: evidence/verdict tests, actual video decode and canonical fast checks.
  - _Boundary: Evidence_
  - _Depends: 3.4_
  - _Requirements: 5.1, 5.3, 5.4, 5.5, 5.6, 7.4, 7.5_

- [ ] 4.2 (P) Complete bounded ownership cleanup and cancellation behavior
  - Exercise partial acquisition, supported cancellation and reverse dependency
    cleanup using directly owned handles/context/container IDs.
  - Preserve primary and cleanup failures separately; detect forced termination,
    unfinished contexts/recordings and surviving owned resources.
  - Verify Windows process-group and Linux session behavior; preserve external
    deployment, unrelated files/services, shared archive cache and failed evidence.
  - Done when success/failure/cancellation cleanup is observable and a forced or
    incomplete shutdown fails acceptance despite successful content assertions.
  - Validation: real lifecycle fault tests, unrelated-resource preservation,
    platform ownership evidence and canonical fast checks.
  - _Boundary: Journey and Deployment cleanup integration_
  - _Depends: 3.4_
  - _Requirements: 7.1, 7.2, 7.3_

## 5. Integrate the complete mandatory regression journeys

- [ ] 5.1 Integrate full headed and unattended acceptance on the same assertions
  - Connect finalized evidence/cleanup to the existing real reference journey;
    keep reviewed profile identities and semantic checks identical across modes.
  - Run the actual owned WSL local headed path and owned Linux unattended path;
    verify selected app/build identities, saved hashes and fresh reopen observations.
  - Done when both mandatory profiles produce inspectable scoped results and any
    unavailable profile remains blocked rather than disappearing from coverage.
  - Validation: complete actual-browser journeys, canonical fast checks and exact
    artifact/recording/cleanup inspection; do not claim hosted CI from local Linux.
  - _Boundary: Journey acceptance integration_
  - _Depends: 4.1, 4.2_
  - _Requirements: 1.4, 3.3, 3.4, 3.5, 3.6, 4.2, 4.5, 4.6, 5.1, 7.4_

- [ ] 5.2 Verify effect, file, diagnostic and target failure paths retain honest results
  - Retain the disconnected edit/restored journey as separate regression attempts;
    exercise no-download timeout and protected existing output content.
  - Exercise unexpected page/build/document change, critical request failure,
    missing recording and unsupported capability without substituting another engine.
  - Done when each missing promised effect prevents acceptance and recovery never
    overwrites the failed attempt or blindly replays an ambiguous business action.
  - Validation: real effect/file challenge plus bounded external-failure tests,
    stage/exit-code assertions and canonical fast checks.
  - _Boundary: Journey failure integration_
  - _Depends: 5.1_
  - _Requirements: 1.6, 2.5, 3.7, 4.3, 4.4, 4.7, 5.5, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.3_

## 6. Deliver the ordinary Python example and dedicated automation stage

- [ ] 6.1 (P) Deliver and reproduce the executable adopter recipe and feature quickstart
  - Expose the same Journey through the ordinary Python CLI, with owned WSL/Linux
    and explicit external-target options, finite bounds and a visible local default.
  - Write the planned COBESY-based quickstart and update existing example/setup
    entry points from observed commands; disclose controlled fallback and readiness.
  - Explain the benefit over static hosting and the distinct direct-MCP session,
    keeping future live/reporting capabilities explicitly pending.
  - Done when a clean-checkout adopter follows the guide, runs the real example,
    inspects its file/video/evidence and observes owned cleanup without AI/private
    packs/sibling runtime dependencies.
  - Validation: actual CLI reproduction and guide/link/command review, canonical
    fast checks; guide/example are mandatory project-extension deliverables.
  - _Boundary: Recipe and documentation delivery integration_
  - _Depends: 5.2_
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.6_

- [ ] 6.2 (P) Add the separate browser verification command and hosted workflow
  - Keep fast and installed-kernel stage semantics; exclude real-browser tests from
    fast checks through declared integration/browser markers.
  - Add the canonical browser mode and dedicated CI job, installing pinned browser
    dependencies and serving official verified bytes in an isolated project.
  - Upload scoped sanitized success/failure evidence even on failure; unavailable
    prerequisites or missing required coverage exit nonzero.
  - Done when the canonical browser command executes the same Journey and the
    workflow has inspectable local configuration evidence; hosted execution is
    reported separately and cannot be inferred without an actual hosted run.
  - Validation: actual canonical browser invocation, workflow/marker checks and
    canonical fast/kernel regressions as affected by the shared entry-point change.
  - _Boundary: Development-gates automation integration_
  - _Depends: 5.2_
  - _Requirements: 5.3, 5.5, 6.6, 8.5_

## 7. Independently validate scoped delivery

- [ ] 7. Independently verify the complete browser feature before closure
  - Run fresh relevant canonical checks and the actual recipe/regression journeys;
    reconcile all 49 criteria with real current evidence and approved boundaries.
  - Inspect changed source budgets/import direction, actual downloaded/reopened
    bytes, finalized video, diagnostics, failed/recovered attempts and cleanup.
  - Keep unavailable platforms, remote/hosted execution or unsupported file routes
    visible as limitations; mandatory missing evidence prevents feature acceptance.
  - Done when independent validation returns the appropriate scoped verdict and
    no open mandatory acceptance is concealed by task checkboxes. Only accepted
    completion updates lifecycle/roadmap; no live/financial reporting claim follows.
  - Validation: Kiro final validation and fresh-evidence gate; current full fast
    checks, browser stage and affected kernel integration, with artifact identities.
  - _Boundary: Cross-task final validation integration_
  - _Depends: 6.1, 6.2_
  - _Requirements: 5.1, 5.6, 7.4, 7.5, 8.5, 8.6_

The generic task-generation rule excluding documentation is superseded by the
owner-requested project documentation extension and approved criteria 8.3â€“8.4.
Deployments here are disposable verification infrastructure, not product release.

## Implementation Notes

- 1.1 accepted: exact Playwright 1.64.0/Pillow 12.3.0 and Chromium 1248/156.0.8078.4; Windows headed blank-page liveness/owned cleanup verified. Evidence `artifacts/browser-verification/task-1.1`; canonical fast 607 passed/65 subtests; independent task review and actual staged installed hook passed. This is tooling proof, not GridCraft workbook proof.
- Workers must leave installed hook execution to parent after selective staging: pre-commit stashes unstaged implementation while untracked regression tests can remain, causing a misleading baseline failure.
