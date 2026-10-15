# Requirements Document

## Introduction

CraftReport integrators and evaluators need proof that automation changes the
GridCraft workbook visible in the selected browser and produces an XLSX whose
saved and reopened content agrees with that workbook. The existing static-hosting
probe demonstrates rendering and input dispatch only. The completed operation
kernel has independent synthetic REST/MCP evidence, not browser reporting proof.

This specification establishes a repeatable released-browser feasibility and
verification workflow. Its small synthetic journey identifies a workbook, edits
known cells through a supported browser interaction, preserves unrelated fixture
content and its line chart, saves the actual file, inspects its bytes and reopens
them in a fresh browser page. The reference edit has distinct declared before
and after values. Evidence and cleanup determine the result.

## Boundary Context

- **In scope:** official prebuilt app acquisition/readiness, isolated browser
  interaction, reference workbook edit/save/reopen, capability findings,
  screenshots/video/diagnostics, failure sensitivity and recovery, owned cleanup,
  and an executable Python demo with a task quickstart.
- **Out of scope:** a production reporting service or general app adapter,
  snapshot publication/scheduling, live refresh controls, declarative report
  compilation, template/theme packs, production persistence, financial-method or
  GIPS assurance, WOPI integration and other Craft apps.
- **Adjacent expectations:** the approved umbrella requirements define the future
  reporting outcomes; this spec supplies scoped browser feasibility evidence for
  later app/report work. Kernel identities and guards remain upstream contracts.
  A separate native/headless engine or an API receipt cannot substitute for this
  selected browser workbook or its saved artifact.

## Confirmed Operating Constraints

Use the latest official downloaded GridCraft release, minimum 0.6.1; do not
compile GridCraft locally or rely on unreleased features. Docker in Debian WSL,
native Linux or explicitly supplied remote instances are the deployment
orientations. Playwright is the requested repeatable browser flow; headed local
review and unattended browser verification exercise the same app journey.
Screenshots and finalized review video are required for critical journeys.
Typed Python, Ruff, declared ownership, reviewed budgets and phase approvals
remain project rules; concrete architecture and dependencies belong in Design.

The web archive contains the compiled Rust/WASM app served as static assets. It
does not provide a Rust backend daemon or the desktop TCP bridge. Save can use a
native file picker or a download fallback. Those source contracts do not prove
the chosen route works in the evaluator's actual browser.

## Requirements

### Requirement 1: Official Application Acquisition and Usable Readiness

**Objective:** As an evaluator, I want to test an identified released application
without building it, so that findings apply to the app users can deploy.

#### Acceptance Criteria

1. When an evaluator prepares an owned GridCraft deployment, the Browser Verification workflow shall select the prebuilt web asset from the latest official release and record its version, release source and asset identity.
2. When the selected archive is acquired or reused, the Browser Verification workflow shall verify its published or explicitly trusted expected checksum before using it.
3. If the selected release is older than 0.6.1, the archive identity/checksum is inconsistent, or the required official prebuilt asset is absent, the Browser Verification workflow shall reject that deployment preparation with a specific reason.
4. When the app is prepared for browser access, the Browser Verification workflow shall identify the serving deployment and the actual served application build separately from the static server's readiness.
5. When the evaluator starts a browser journey, the Browser Verification workflow shall wait within the configured readiness bound for the actual grid and required controls to become usable.
6. If required assets, graphics support or app startup prevent usable readiness, the Browser Verification workflow shall record the failed stage and diagnostics without treating a listening port or HTTP success as a passing app journey.

### Requirement 2: Isolated Ownership and Exact Target Identity

**Objective:** As an operator, I want verification confined to its intended target
and resources, so that a test cannot alter another workbook or deployment.

#### Acceptance Criteria

1. When a run starts, the Browser Verification workflow shall assign a unique run identity to its deployment selection, browser context, fixture, output destination and evidence.
2. When an owned deployment is started, the Browser Verification workflow shall use a project-specific deployment identity and available browser origin without taking over an existing unrelated service or the probe on port 8871.
3. Where an operator supplies an external deployment, the Browser Verification workflow shall verify its configured app identity and reachability while treating that deployment as externally owned.
4. When a browser page or workbook is selected, the Browser Verification workflow shall record its app/build/mode, origin, page/document identity and generation before acceptance-critical interaction.
5. If the selected page/document/build changes unexpectedly or cannot be identified, the Browser Verification workflow shall stop further mutation and record the target mismatch rather than redirect work to another page or engine.
6. While verification is running, the Browser Verification workflow shall use an isolated browser context and public or synthetic fixture rather than the operator's ordinary browser profile, credentials or private workbook.

### Requirement 3: Released-Browser Interaction and Observable Workbook Effects

**Objective:** As an integrator, I want a small known edit proven in the visible
workbook, so that a future report adapter has an exercised interaction path.

#### Acceptance Criteria

1. When the reference journey starts, the Browser Verification workflow shall open an identified synthetic workbook with known cell values/types, sentinel content and a line chart whose source series is declared by the fixture.
2. When a reference edit is requested, the Browser Verification workflow shall identify the actual released-browser interaction route and its target before performing the edit.
3. When the selected control or input action executes, the Browser Verification workflow shall verify the declared changed cells in the selected visible workbook rather than infer the effect from input dispatch or control availability.
4. When the reference edit completes, the Browser Verification workflow shall verify that declared unedited sentinel cells and the fixture's line-chart identity/source bindings remain consistent with the expected workbook.
5. When an evaluator requests headed review, the Browser Verification workflow shall expose the selected workbook in a visible browser window without silently substituting a headless session.
6. When an evaluator selects headed review or unattended verification, the Browser Verification workflow shall exercise the same declared workbook assertions and record the selected browser/runtime profile.
7. If a required input, file or control route is unavailable or unexercised in the selected release/profile, the Browser Verification workflow shall identify the affected capability as unverified or blocked and withhold verified-browser acceptance.

### Requirement 4: Actual XLSX Persistence, Inspection and Reopen

**Objective:** As a report recipient, I want the saved workbook and its reopened
content checked, so that visible edits survive a real file boundary.

#### Acceptance Criteria

1. When Save/export is requested for the reference workbook, the Browser Verification workflow shall identify the expected edited fixture and the actual picker or download route selected by the browser.
2. When that save route completes, the Browser Verification workflow shall capture the actual persisted XLSX bytes, their destination, size and content hash before declaring persistence verified.
3. If the save is cancelled, times out, fails or produces no readable persisted file, the Browser Verification workflow shall record that outcome and withhold verified-persistence status despite any UI acknowledgement.
4. When a requested destination already contains content without declared overwrite authorization, the Browser Verification workflow shall preserve that content and report the destination conflict.
5. When saved content is inspected, the Browser Verification workflow shall compare its declared fixture/document marker, changed and sentinel cell values/types, declared line-chart source/series and declared fixture presentation checks against the expected edited workbook.
6. When reopen verification runs, the Browser Verification workflow shall open the exact saved bytes in a fresh selected browser page and verify the expected visible edited workbook, recording the new page/document generation and its artifact association.
7. If saved-byte inspection or browser reopen does not satisfy the declared fixture checks, the Browser Verification workflow shall report the affected content or stage and withhold verified-round-trip acceptance.

### Requirement 5: Inspectable Evidence and Safe Diagnostics

**Objective:** As a reviewer, I want evidence tied to the actual journey, so that
I can distinguish delivery, visible effect, persistence and reopen checks.

#### Acceptance Criteria

1. When a critical journey is recorded, the Browser Verification workflow shall associate its requirement references, source revision, fixture expectations, app/build, deployment, browser/profile, page/document generations and artifact identities with one run.
2. When the app is usable, the edit is verified, the file is persisted and the workbook is reopened, the Browser Verification workflow shall retain named screenshots associated with those checkpoints.
3. When a safe synthetic critical journey runs, the Browser Verification workflow shall retain a review video for success and failure, and verify its finalized content after the owned recording context closes.
4. When browser diagnostics are collected, the Browser Verification workflow shall retain stage-associated page, console and acceptance-critical request findings while excluding credentials and private content from public evidence.
5. If an unexpected page exception, acceptance-critical request failure or missing required recording occurs, the Browser Verification workflow shall record the failure and withhold verified-path acceptance.
6. When a result is inspected, the Browser Verification workflow shall distinguish app readiness, visible mutation, persistence, byte inspection, browser reopen and cleanup findings, including unexecuted checks.

### Requirement 6: Failure Sensitivity, Bounds and Recovery

**Objective:** As a developer, I want the verifier to detect a missing effect and
retain failures, so that a green run cannot hide broken interaction wiring.

#### Acceptance Criteria

1. When a run starts, the Browser Verification workflow shall expose the configured readiness, action and cleanup bounds used by that run.
2. If an action exceeds its bound after possible external interaction, the Browser Verification workflow shall record the last known target and an unresolved outcome without blindly replaying an edit or save.
3. When the critical reference action is deliberately disconnected in a controlled verification variant, the Browser Verification workflow shall fail the actual effect check and retain evidence of the unchanged or incorrect workbook.
4. When correct interaction wiring is restored after that challenge, the Browser Verification workflow shall run the reference journey again and independently verify its effect and saved-file round trip.
5. When a failed attempt is followed by recovery, the Browser Verification workflow shall retain the failed and recovered attempts as distinct run evidence instead of overwriting the failure.
6. If mandatory tooling, target access or file/control capability cannot be exercised, the Browser Verification workflow shall report the missing prerequisite and unverified stage without manufacturing passing evidence.

### Requirement 7: Owned Cleanup and Truthful Completion

**Objective:** As an operator, I want successful shutdown to be part of the
result, so that passing assertions do not leave unowned processes or incomplete
recordings behind.

#### Acceptance Criteria

1. When a run succeeds, fails or receives a supported cancellation request, the Browser Verification workflow shall retain and settle its resource acquisitions and perform bounded cleanup using exact owned handles and container identities. It shall record directly launched deployment subprocess shutdown and observed exit separately from completed public Playwright context, browser and driver closure. Public SDK closure shall be classified `sdk-closed` only for an identified Playwright SDK resource and shall not establish graceful native-process exit. Cleanup findings shall remain separate from the primary journey result.
2. When resources are externally owned, the Browser Verification workflow shall close only its own browser/verification resources without stopping or deleting the operator's deployment or unrelated files.
3. If cleanup explicitly requests force or observes force at any boundary, fails or times out, leaves acquisition or closure unsettled, observes an unexpected disconnection or surviving owned resource, or fails to finalize required evidence, the Browser Verification workflow shall retain that failure and withhold verified acceptance even if content assertions passed. Calling an approved public SDK close/stop operation alone is not an observation or assertion of native force. The declared inability to observe Playwright-internal force shall be recorded as an immutable capability limitation; it shall not excuse a per-run failed, timed-out or unresolved public close operation, missing resource identity or unfinished video.
4. When a run is finalized, the Browser Verification workflow shall declare a verified browser path only when all mandatory journey, saved-file, reopen, evidence and cleanup checks for its declared scope passed under the approved resource-specific closure contract. An `sdk-closed` finding may satisfy only the matching identified Playwright SDK resource's public closure check; it shall not satisfy a subprocess exit check or override any failed, blocked, unresolved or unexecuted mandatory check.
5. When scoped browser evidence passes, the Browser Verification workflow shall identify that scope and the declared SDK observation limitation without claiming graceful native browser/driver process exit, absence of SDK-internal force, live reporting, kernel-to-browser integration, production durability or financial-method assurance that the run did not establish.

### Requirement 8: Reproducible Adopter Example and Feature Demonstration

**Objective:** As an adopter, I want to run and adapt one complete example, so
that I can judge the browser workflow's value without an AI service or private
content.

#### Acceptance Criteria

1. When the feature is delivered, the Browser Verification workflow shall provide a repeatable executable Python entry point for the same supported reference browser journey without requiring AI, a private pack or the sibling reference project at runtime.
2. When that example is run, the Browser Verification workflow shall demonstrate the actual visible edit, saved XLSX, reopened result and owned cleanup rather than replace them with mock success responses.
3. When an adopter reads the feature quickstart, the Browser Verification workflow shall provide prerequisites, exact invocation, synthetic inputs, expected observations, evidence inspection, failure guidance and cleanup for the demonstrated profile.
4. When a reader evaluates the feature, the Browser Verification workflow shall explain the user benefit and distinguish the tested browser workflow from direct app MCP, static hosting and the future reporting facade.
5. When verification is repeated locally or in supported unattended automation, the Browser Verification workflow shall run the same declared assertions with isolated identities and produce inspectable results suitable for regression checks.
6. If the example or guide depends on a capability not yet delivered or verified, the Browser Verification workflow shall identify that limitation and keep the corresponding acceptance open instead of publishing it as working product behavior.

## Adjacent Requirement References

This child supplies scoped feasibility/evidence for umbrella criteria 6.1–6.2,
6.4–6.6, 6.8, 8.3–8.7, 11.7, 11.9 and 12.4–12.5, 12.7–12.9. Its fixture round trip
does not close those full-report criteria. Browser mutation of a complete bound
report, live updates, snapshot-consistent export during refresh and quality
release behavior remain in the downstream reporting scopes.

The planned guide is
`docs/quickstarts/Quickstart_How_to_verify_GridCraft_in_a_browser.md`. The proposed
executable entry point is `scripts/examples/verify_gridcraft_browser.py`; this
path is a planning reference and no implementation is created in this phase.
Exact code/verification ownership, supporting modules, interaction contracts,
dependencies and evidence layout are Design decisions under existing project
gates.
