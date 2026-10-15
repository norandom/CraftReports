# Agent Verification and Interaction Standards

Updated: 2026-10-13. Applies to implementation and validation; no runtime verification is claimed by creating this file.

## Test Oracle and Ownership

Use approved observable requirements as the oracle. Each business action has a typed operation owner, preconditions, target identity, pending/success/failure behavior and a defined external effect.

API, menu, control, keyboard and agent entry paths for the same operation share its contract. Execution rechecks preconditions; UI availability is not the only guard.

Identify canonical, draft, derived and persisted state explicitly. A task or downstream adapter cannot repair shared contract defects by duplicating state or logic at a different boundary.

## What Success Means

Keep these receipts separate: input accepted, calculation validated, report compiled, target mutated, artifact persisted, artifact reopened, quality policy evaluated.

A job accepted response, toast, mocked return value, dispatched event or existing button is not proof of the promised external effect. Save verification includes actual bytes/read-back after reopen. Numerical accuracy requires independent references, not only app rendering.

## Reference Feature First

Before expanding app breadth, prove one small vertical feature through real wiring: accept a synthetic grid, render/update the selected app, invoke a real control, save/export, reopen and compare the identified content.

Include success and the highest-risk failure/recovery path. Test pause/resume or duplicate/disabled invocation where promised. A second small feature should reuse the same ownership and verification pattern before generalizing it.

The initial required paths are visible live dashboard refresh, snapshot-consistent XLSX export and app-to-app MCP. Exercise them with a deterministic external-producer fixture and ordinary MCP client while AI is disabled. Reconcile one version across displayed cells/charts, exported bytes and receipts. Imported metric schema acceptance is distinct from independent numerical validation. Include export-during-refresh and late/out-of-order/rejected updates under the selected update contract.

A bounded test-sensitivity check can deliberately disconnect the reference control/adapter in a disposable test variant. Its critical test must fail. Restore the correct wiring and verify success; do not ship the deliberate defect or turn this into unrelated mutation-test infrastructure.

## Verification Layers

1. Domain/data/method checks: applicability, independently known numerical results, edge inputs and explicit tolerances.
2. Contract/integration checks: real internal collaborators and selected adapters, result schemas, target identity and persistence.
3. Runtime smoke: the built service and app session reach a usable state, beyond process or health-port existence.
4. Browser/user-path checks: real input/click/key/upload/save in the target app and its resulting business effect.
5. Artifact checks: actual downloaded/saved bytes, report content/layout and reopen/read-back.
6. Feature validation: current suite results, coverage, boundary/design alignment, blocked work and evidence freshness.

Mock only at the boundary needed to simulate an external failure. Do not mock away the facade, internal wiring or persistence adapter in the test meant to prove that path works.

## Per-Project Browser and Compose Isolation

Owner instruction on 2026-10-15: run automated tests and diagnostics headlessly
so browser windows never come into the foreground. Do not launch headed windows
or activate native windows during unattended development. Retain existing headed
evidence with its original scope; any new visible review requires an explicit
owner request. This overrides the earlier local headed default for agent-run
checks, while preserving the separate headed capability and its honest coverage.

Use project/run-specific Compose identity, configured endpoints, synthetic fixtures, output/download directories and browser profile/context. Record the selected browser/page/session identity before operating it. Do not attach verification to the user's ordinary browser profile.

Craft web builds can be served from separate app services where supported. Pin app bundle/build and browser versions. A web bundle's engine lives in its browser session; native TCP control and a headless MCP engine are different sessions unless a verified bridge explicitly connects them.

Chrome DevTools MCP or another supported browser driver can perform agent checks. Confirm available tooling and target-page routing. Canvas-rendered apps need suitable input/screenshot capabilities; ordinary DOM controls cannot be presumed.

Playwright is the primary requested browser verification flow, adapted from `D:/Source/because-security-quant-terminal`. Retain screenshots, safe reference-journey review videos and console/network diagnostics. That reference's default recordings are off; Craft's selected critical journeys must enable them explicitly. Flush videos by closing owned contexts before finalizing evidence. Unexpected critical diagnostics or failed owned cleanup fail acceptance even if assertions passed.

Download/serve the latest official GridCraft release, at least 0.6.1, without compiling it. Record its checksum/version and prove the actual browser file route. Use Debian WSL Docker here or configured operator-owned remote instances. A headed isolated browser supports live owner review; headless CI records the same browser path. Neither substitutes for a separate native profile.

Browser automation should become repeatable test cases for CI. Tool presence or an agent's manual pass alone does not establish reusable regression coverage.

## Evidence and Diagnostics

Record code revision, spec/requirement references, app/build/mode, Compose project, endpoint/page identity, fixtures/snapshots, commands, exit codes, console/network failures, artifact identities, read-back assertions and relevant screenshots.

Unexpected application exceptions, failed acceptance-critical requests or broken output fail the affected path. Retain useful diagnostics instead of replacing failure with a successful rerun that hides the cause.

Public CI uses public/synthetic fixtures. Private pack/data evidence remains within its configured private environment and visibility policy.

## Kiro Completion Gate

Task-local checks precede task acceptance. Feature GO requires fresh tests, usable runtime boot, critical end-to-end and persistence evidence, requirements coverage, cross-task integration, design/boundary alignment and blocked-task assessment.

Use `kiro-verify-completion` before success claims and `kiro-validate-impl` for feature-level validation. Report `NO-GO` for established failures and `MANUAL_VERIFY_REQUIRED` where a mandatory environment/check is unavailable. Do not mark unavailable browser/native checks passed.

Classify failures as local, upstream or unclear. Fix at the owning boundary and revalidate affected consumers. Re-run checks when relevant code, contracts, app versions or evidence changed; do not repeat unchanged successful checks merely for ceremony.
