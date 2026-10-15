# Implementation Plan

Requirements, Design and Tasks are owner-approved. Implementation is in progress. All acceptance work is mandatory. Design's File Structure Plan defines
exact file ownership; every normal task stays within its named boundary, and
tasks crossing those seams are explicitly integration work.

Each executable task is planned as a bounded 1–3 hour unit. Task-local review,
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

- [x] 1.2 Define validated run identities, findings and immediate resource ownership
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

- [x] 1.3 Prepare and independently review the synthetic workbook expectations
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

- [x] 1.4 Inspect the fixed fixture and saved XLSX semantics without rewriting bytes
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

- [x] 2.1 Acquire and identify the latest official prebuilt application
  - Resolve official stable latest metadata, enforce minimum version and a unique
    web asset; verify trusted expected digest on download and cache reuse.
  - Extract safely under bounded paths/sizes and retain HTML/JS/WASM hashes;
    cache acquisition failures cannot relabel an old release as latest.
  - Done when the real archive is verified without compiling and corrupted,
    missing or too-old selections produce specific non-passing findings.
  - Validation: acquisition fault tests, one official download/reuse and fast checks.
  - _Boundary: Release_
  - _Requirements: 1.1, 1.2, 1.3, 6.6_

- [x] 2.2 Select an owned Compose deployment or verify an explicit external target
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

- [x] 2.3 Implement the reviewed browser capability budget amendment
  - Implement the owner-approved exact browser-verification aggregate override
    of 2,800 LLOC, retaining the global 1,500 default and local 50/300/10 rules.
  - Parse typed capability/rule/value/owner/rationale/approval metadata; reject
    unknown or unapproved capability, wildcard scope, unsupported rule, invalid
    number, duplicate entry and missing approval. No CLI/env/run-config limits.
  - Count all helpers and recipe once; preserve separate test reporting. No waiver
    or ownership relocation replaces numeric enforcement.
  - Done when browser 2,800 passes / 2,801 fails, another capability still fails
    at 1,501, and function/module/branching and policy faults retain enforcement.
  - Validation: flag-off RED/ON GREEN/removal, focused engineering regressions,
    canonical fast checks, independent review and actual installed commit hook.
  - _Boundary: Development-gates budget enforcement integration_
  - _Depends: 2.2; owner approval recorded in budget-amendment.md_
  - _Requirements: 2.6, 6.6, 8.1_

- [x] 2.4 Integrate isolated browser startup with minimum evidence and cleanup
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
  - _Depends: 1.2, 2.2, 2.3_
  - _Requirements: 1.5, 1.6, 2.4, 2.6, 3.5, 3.6, 3.7, 5.3, 5.4, 6.6, 7.1_

## 3. Prove the released-browser route before expanding the harness

- [x] 3.1 Open the known fixture, perform one edit and observe fresh real UI values
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
  - _Depends: 1.3, 2.4_
  - _Requirements: 2.4, 2.5, 3.1, 3.2, 3.3, 5.2, 6.2_

- [x] 3.2 Establish independently reviewed live chart and presentation observations
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

- [x] 3.3 Capture a real Save download, inspect it and reopen its exact bytes
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

- [x] 3.4 Prove route sensitivity and retain the first bounded feasibility result
  - Suppress only edit dispatch in a disposable test variant; fresh readback must
    detect unchanged B3 and produce a failed attempt with review evidence.
  - Restore real dispatch in a distinct run and repeat the complete round trip.
  - Record actual route/profile capability findings and first-slice source budget.
    Stop expansion if required routes are blocked or the approved cap cannot fit;
    seek an owning design/budget correction rather than manufacturing success.
    Owner-approved exception: after independent acceptance of the Windows
    headless sensitivity/recovery checkpoint, tasks 4.1 and 4.2 may proceed
    under `headless-continuation-amendment.md`. Retain unsupported profile
    findings explicitly; stop again before 5.1 for the profile/verification decision.
  - Done when independent review can inspect both the expected failed challenge
    and restored successful journey, including owned cleanup.
  - Validation: paired real sensitivity/recovery runs and relevant fast checks.
  - _Boundary: Journey feasibility integration_
  - _Depends: 3.3_
  - _Requirements: 3.7, 6.3, 6.4, 6.5, 6.6, 7.3, 7.5_

## 4. Complete evidence and lifecycle accountability after feasibility

- [x] 4.1 (P) Finalize inspectable evidence and scoped verdict reduction
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
owner-requested project documentation extension and approved criteria 8.3–8.4.
Deployments here are disposable verification infrastructure, not product release.

## Implementation Notes

- Owner instruction on 2026-10-15 after resuming: automated tests and diagnostics must run headlessly without windows entering the foreground. Preserve existing headed evidence; do not repeat headed tests or activate native windows without a new explicit request. Use explicit headless selection for current investigation and regression commands; report any remaining headed coverage gap separately.

- 1.1 accepted: exact Playwright 1.64.0/Pillow 12.3.0 and Chromium 1248/156.0.8078.4; Windows headed blank-page liveness/owned cleanup verified. Evidence `artifacts/browser-verification/task-1.1`; canonical fast 607 passed/65 subtests; independent task review and actual staged installed hook passed. This is tooling proof, not GridCraft workbook proof.
- Workers must leave installed hook execution to parent after selective staging: pre-commit stashes unstaged implementation while untracked regression tests can remain, causing a misleading baseline failure.
- 1.2 accepted after output-ID alias repair: canonical fast 639 passed/65 subtests, independent focused review 32 passed; browser source 314/1,500 LLOC. Evidence `artifacts/browser-verification/task-1.2` and `artifacts/task1.2/remediation-*`.
- Component records remain with their actual owners: release/bundle identities in 2.1, fixture expectations in 1.3/1.4, interaction observations/edits in 3.1 and visual profiles in 3.2. No placeholder runtime runner was introduced. Use `scripts.browser_verification` imports; the owned test-package marker prevents duplicate test-module names.
- 1.3 accepted: independently audited/reproduced static fixture, 7,559 bytes SHA256 `7a0583c2418c988c4ec1d261e503b30c45aae3f77bc0fc548886fee4cc591ca8`; all 11 typed cells/chart references/styles checked. Before/after expectations differ only at B3 20 to 25. Evidence `artifacts/browser-verification/task-1.3`; no app-rendering or save/reopen claim.
- 1.4 accepted after chart-reference normalization repair: real-ZIP focused tests 42 passed, canonical fast 681 passed/65 subtests, independent alias/binding/read-only checks passed. Saved-artifact inspection verifies size/hash against the same retained bounded bytes. Source 723/1,500 LLOC. Evidence `artifacts/browser-verification/task-1.4`; no actual browser persistence claim.

- 2.1 accepted after malformed-deflate rejection repair: official latest v0.7.0 asset/checksum and cache reuse independently verified; focused 37 passed, canonical fast 718 passed/65 subtests; source 943/1,500 LLOC. Evidence `artifacts/browser-verification/task-2.1`. No deployment/browser acceptance follows.
- Owner authorized replacing the existing 8871 probe on 2026-10-14: it now serves verified v0.7.0 assets with a successful rendering smoke, screenshot and finalized video under `artifacts/gridcraft-deployment-probe/browser-0.7.0`. Disposable harness runs still preserve that operator-owned service.

- 2.2 accepted after delayed-start cleanup repair: focused 17 passed, canonical fast 735 passed/65 subtests; actual WSL owned/external asset hashes, normal cleanup and unrelated resource preservation independently reviewed. Ambiguous Compose startup retains failed cleanup/project ownership; no daemon quiescence claim. Native Linux has command/path unit coverage only. Source 1,195/1,500 LLOC. Evidence `artifacts/browser-verification/task-2.2/remediation-*`.

- Owner approved the independently reviewed browser-only 2,800-LLOC amendment on 2026-10-14. New 2.3 implements bounded enforcement; former 2.3 is now 2.4 and 3.1 depends on it. There are 19 executable tasks. All acceptance criteria and other numeric limits remain. See `budget-amendment.md`; current global enforcement stays until 2.3 is accepted.

- 2.3 accepted: bounded typed browser-only 2,800-LLOC override enforced; focused policy regressions and independent review passed, canonical fast 741 passed/88 subtests. Other 1,500 defaults and local 50/300/10 retained. Development-gates 1,042/1,500; browser source 1,195/2,800. Evidence `artifacts/browser-verification/task-2.3`; first hosted Linux CI separately exposed fixture-cache/test-platform defects being repaired at their owners.

- 2.2 reopened for a hosted-Linux test portability regression: seven simulated owned tests passed Windows paths to the WSL profile on Linux and failed before their intended assertions. Actual WSL deployment evidence remains valid. Fix the owning test setup and verify Linux without weakening production path checks. Hosted failure `https://github.com/norandom/CraftReports/actions/runs/38612814632`, retained `artifacts/ci-first-push/failed.log`. Kernel offline fixture-cache resolution is a separate upstream repair.

- 2.2 Linux portability follow-up accepted: old Linux suite 7 failed/10 passed; repaired and independent source-hash-matched Linux run 17 passed. Windows focused 17 passed/canonical fast 741 passed/88 subtests. Only simulated test mode/argv assertions changed; production validation and all fault assertions retained. Evidence `artifacts/browser-verification/task-2.2/linux-portability`. Hosted kernel cache repair remains separate.

- 2.4 accepted on 2026-10-15: independent review and fresh canonical fast checks passed (763 tests, 88 subtests); four real final runs proved headed/headless startup and missing-WASM/denied-clipboard rejection with graceful owned cleanup. Reviewer independently rehashed/decoded all four videos and matched all five source hashes. Loaded HTML/JS/WASM, native window visibility, disclosed picker removal and reversible A1/B1/A1 selection are observed. Evidence `artifacts/browser-verification/task-2.4/review-index.json`; source 1,714/2,800 LLOC. Calibrated Windows profile is explicit; unknown profiles block, including Linux until separately calibrated. Workbook mutation/save/reopen and complete lifecycle/evidence acceptance remain later tasks.

- 2.4 reopened for hosted Linux strict typing: [run 38691918170](https://github.com/norandom/CraftReports/actions/runs/38691918170) failed on Windows-only `ctypes.windll`/`WINFUNCTYPE` references in `evidence.native_window`. Repair the platform boundary and verify Linux typing plus retained Windows visibility behavior before dependent task 3.1. Prior actual Windows startup evidence remains valid; this is a tooling portability defect.

- 2.4 follow-up accepted: explicit platform guard preserves the Windows API branch and safely returns unverified on other platforms. Independent canonical fast checks passed 765 tests/88 subtests; Linux-target strict typing reports zero errors, and matching-source actual Linux/Windows fast runs also passed. Three final headless runs proved readiness, missing-WASM rejection and clipboard denial with independently rehashed/decoded videos and graceful cleanup. Measured serial WSL command overhead exhausted shortened fixture bounds; the fixture now records readiness/action/cleanup 90/10/60 while production defaults remain 90/20/30. Preserve failed attempts in `artifacts/browser-verification/task-2.4/{linux-portability,clipboard-investigation,cleanup-deadline-investigation,cleanup-calibration}`; final review index is in `cleanup-calibration/review-index.json`. Historical headed clipboard/geometry triggers remain unestablished; no clipboard retry or geometry/app change was made. New verification is headless under the owner's instruction. Browser source 1,717/2,800 LLOC; hosted revalidation follows the repair push.

- Hosted revalidation confirmed: [run 38703204004](https://github.com/norandom/CraftReports/actions/runs/38703204004) at repair commit `7bde0bc` completed successfully, including fast checks and installed-wheel synthetic conformance. This confirms the Linux typing repair on the hosted runner; the dedicated browser workflow remains a later task.

- 3.1 accepted: actual File/Open/Browse chooser imports the verified fixture; real Name Box/formula-bar/Copy interactions prove B3 20-to-25 and all ten unchanged cells. Per-event render synchronization prevents canvas shortcut batching from selecting an unintended range. Five final headless cases passed: healthy edit, wrong page, actual wrong marker (independent B3=20), post-commit timeout (independent B3=25, one commit, no replay), and late navigation after checkpoint. Independent review matched all six source hashes, rehashed/decoded all five videos and checked graceful browser/deployment cleanup; fresh canonical fast 777 tests/88 subtests passed. Evidence `artifacts/browser-verification/task-3.1/review-index.json`; source 1,997/2,800 LLOC. Tests explicitly record 90/60/60 bounds based on measured UI/WSL overhead; production defaults remain unchanged, and earlier timeout/calibration failures remain retained. All new verification was headless. Chart-source/presentation, saved bytes and reopen acceptance remain later tasks.

- Hosted revalidation confirmed for 3.1: [run 38709830633](https://github.com/norandom/CraftReports/actions/runs/38709830633) at commit `426f3b2` completed both fast checks and installed-wheel synthetic conformance successfully. Dedicated browser CI and full report acceptance remain later work.

- 3.2 accepted: two complete headless runs verified the same chart's title/placement, Value series, genuine category-field Copy, blue B2:B4 outline and middle-point change from 20 to 25. All eleven cells matched before and after chart inspection in both phases. Independent review matched all 28 owned file hashes, re-evaluated the observations, checked baseline provenance and decoded four frames from each finalized video; browser/deployment cleanup was graceful. Fresh independent canonical fast checks passed 783 tests/88 subtests; source is 2,250/2,800 LLOC. Evidence `artifacts/browser-verification/task-3.2/review-index.json`; final manifest `90a24c02d76245afd787a7c9ee53eeacce678893599e5fbd48b7e01679f9bc33`. Scoped Git attributes preserve exact reviewed JSON bytes across checkouts. Only Windows headless is calibrated; unknown Linux/headed/render profiles reject. Exact saved types/format, persistence, reopen, complete journey and hosted browser acceptance remain open.
- Carry into 4.1/4.2: task-specific runtime-test cleanup assertions can replace the primary pytest exception, although raw findings and evidence remain retained. Keep primary and cleanup outcomes separately in the finalized journey. The 3.2 RED execution is recorded in the implementer's original tool transcript and summarized in `tdd.json`; no raw RED log was retained, and independent review did not claim to inspect one.

- Hosted revalidation confirmed for 3.2: [run 38717437631](https://github.com/norandom/CraftReports/actions/runs/38717437631) at commit `9c83240` passed both fast checks and installed-wheel synthetic conformance. This is hosted code/kernel validation; the dedicated actual-browser workflow remains task 6.2.

- Owner paused on 2026-10-15 to suspend the laptop. Task 3.3 remains uncommitted and unchecked, pending final canonical-check reconciliation and independent review. Final-source headless healthy run `2eec37bf-1732-4130-8b92-1fde5c9ac15a` passed in 255.36s: real XLSX download, 22 byte-inspection findings, exact-byte fresh-context cell/chart checks, two decoded videos and graceful cleanup. Artifact size 6,475 bytes, SHA256 `defb701297c629533149b674216406ee1d1dc922df26e6c3710554e8f55282cc`. Earlier healthy run `308e7767-e0f6-4661-adcd-1f859f195588` and real conflict/no-file runs `30a0fae3-e8dd-4044-a625-d77dcfbdbed0` / `670e78ea-b0ef-4635-b6a3-c9582983b90c` remain retained; unchanged negative-path source equivalence is recorded by the implementer. Use `artifacts/browser-verification/task-3.3/source-freeze-final.json` and the implementer's pause checkpoint to resume; do not infer task acceptance or a final fast-check result from intermediate 812-test passes. Source was 2,494/2,800 LLOC. Keep all failed attempts and the headless-only development constraint.
- Pause shutdown confirmation: the implementer sent cancellation to its directly owned canonical session, which had already completed with exit 0: 812 tests passed, 74 deselected, 88 subtests, 195.24s. No task process remained active; all owned browser/deployment runs had already closed gracefully. This final check is recorded for resume-time source/evidence reconciliation; independent task review, acceptance and commit remain pending.

- 3.3 accepted after resume: independent review verified all 32 frozen source hashes and 1,234 indexed hash/size references, re-inspected the actual 6,475-byte XLSX (all 22 findings), re-evaluated before/after/reopen chart checks and all eleven cells, and confirmed distinct context/page identities with generation 2 to 3. Fresh independent canonical fast passed 812 tests/88 subtests. Four healthy/fault videos were independently decoded headlessly; browser/deployment cleanup was graceful. Actual conflict preserved existing content with zero Save dispatches; actual no-file retained one unresolved receipt and no output. Evidence `artifacts/browser-verification/task-3.3/review-index.json`; source 2,494/2,800 LLOC. Windows headless download-fallback scope only; sensitivity, final packet/lifecycle, other profiles and adopter/hosted browser delivery remain open.
- Reopen learning: GridCraft preserves the saved active cell (D3), and chooser completion can precede the end of the backstage import screen. Wait within the action bound for the observed Book1-to-imported title transition before real Name Box navigation to A1, then verify the marker and all eleven cells. One Open dispatch only. Journey passes an inspection result bound to artifact hash/size, fixture hash and edited phase; BrowserDriver owns all UI, including the bounded reopen screenshot. Keep failed import attempts distinct and never rewrite exported bytes to match expectations.

- Hosted revalidation confirmed for 3.3: [run 38730830406](https://github.com/norandom/CraftReports/actions/runs/38730830406) at commit `4aa8cf7` passed fast checks and installed-wheel synthetic conformance. Dedicated browser CI remains pending.

- 3.4 accepted: independent review matched 467 evidence files and 34 current source hashes, confirmed actual suppressed dispatch leaves all eleven observed cells unchanged (B3=20) and rejects the edit before Save, and verified a distinct restored full round trip with all 22 saved-byte findings and fresh-context chart/cell checks. Four retained videos independently decoded headlessly; owned cleanup was graceful. Fresh independent canonical fast passed 813 tests/88 subtests. Evidence `artifacts/browser-verification/task-3.4/review-index.json`; source 2,496/2,800 LLOC. Original challenge assertion typo remains retained; exact source equivalence establishes unchanged production/recovery code after its correction. This accepts only the Windows headless download-fallback checkpoint.
- Expansion hold after 3.4: required headed/Linux profiles remain unverified, and the owner prohibits automated foreground windows. The task stop-expansion rule remains in force before 4.1/4.2. The separately proposed `headless-continuation-amendment.md` passed independent review but requires explicit owner approval; no acceptance criteria or budgets are waived. Remaining source forecast is uncertain, not proof the cap cannot fit.

- Owner explicitly approved `headless-continuation-amendment.md` on 2026-10-15. The prior expansion hold is lifted only for tasks 4.1 and 4.2, with headless-only execution, unchanged acceptance criteria and 2,800-LLOC cap. Stop before 5.1; missing headed/Linux coverage remains open.

- Hosted revalidation confirmed for 3.4: [run 38735032116](https://github.com/norandom/CraftReports/actions/runs/38735032116) at `add0f10` succeeded. Dedicated browser CI remains pending.
- 4.1 accepted after reference-completeness remediation: typed readiness/receipts/diagnostics and provenance bind stage findings; final manifest atomically publishes after cleanup with hashed findings and every declared observation reference. Independent review matched 2,020 evidence files and both 75-identity source/input/cache freezes, rechecked 22 actual XLSX findings and all chart/cell phases, and decoded three finalized videos headlessly. Missing actual Open, Reopen or cell screenshots and truncated recordings reject acceptance. Fresh independent canonical fast passed 847 tests/88 subtests. Evidence `artifacts/browser-verification/task-4.1/remediation-1/review-index.json`; source 2,798/2,800 LLOC. Prior incomplete-reference reproduction and intermediate attempts remain retained. Scoped Windows headless synthetic acceptance only; native lifecycle and full-feature/profile acceptance remain open.
- Owner approved both changes in `lifecycle-evidence-budget-amendment.md` on 2026-10-15: explicit SDK/native closure evidence and browser-only 3,400 cap through new gate task 4.0. Apply the amended specification after this 4.1 acceptance; enforcement remains 2,800 until the gate is implemented and independently accepted. Stop before 5.1 remains. Final 4.1 baseline 2,798 is 54 above the proposal planning snapshot 2,744; preserve the approved 3,400 maximum and report the reduced headroom honestly.
