# First user release continuation

On 2026-10-16 the owner agreed to finish the narrow first release after reviewing
the overnight handoff and remaining delivery gaps: "I agree. We should finish
this narrow release". This authorizes continued implementation of the already
reviewed snapshot-runtime, report-model-packs and GridCraft web-report scopes;
the earlier overnight deadline remains historical and is not extended.

## Release outcome

An external Python producer supplies portfolio data and metrics through the
public facade. One supported reusable report displays a table and line chart in
GridCraft, refreshes at ten-second opportunities, and exposes shared
start/pause/resume/stop controls. Resume selects the latest complete ordered
snapshot. REST and MCP callers use the same operations without requiring AI.
Actual saved XLSX bytes are independently checked and reopened. Required quality
failures permit clearly marked drafts and block validated release.

Delivery includes documented setup, runnable public Python examples and verified
feature quickstarts. Supplied metrics retain their producer provenance and
validation status; this release does not calculate portfolio methods or claim
GIPS compliance. Other Craft applications and accounting/domain extensions stay
outside this release.

The owner subsequently selected the [local Windows browser launcher](../craftreport-gridcraft-web-reports/local-browser-decision.md)
for live viewing: the visible window must be the exact session controlled by
CraftReport. Automated tests remain headless; separate visible acceptance stays
open until exercised. The static hosting URL alone does not share a workbook
session with another browser tab.

## Execution constraints

Continue the existing approved task dependency order, with independent review,
fresh task evidence, selective hooked commits and pushes to main. Preserve
unrelated worktree changes. Run Windows tests and headless browser verification;
Debian WSL supplies Docker hosting only. Use downloaded GridCraft releases,
without local Rust compilation. Existing ownership and numeric limits remain.
This continuation does not authorize new budget exceptions or silently changed
acceptance contracts. Prefer existing libraries and deletions over new generic
infrastructure; report concrete conflicts with a reviewable correction.

As of 2026-10-16, the accepted baseline is 019112c, with 13/20 snapshot-runtime,
8/13 report-model and 3/16 GridCraft tasks accepted. Browser verification has
15/20 accepted tasks. Task checklists remain the live status source. Installed
REST publication and MCP readback after restart are accepted. Existing GridCraft
candidate work remains unaccepted until its required implementation and real
application proof pass.

## Owner-confirmed delivery focus

After reviewing the remaining work, the owner agreed to prioritize one complete
visible producer-to-chart-to-XLSX workflow. This prioritizes the existing release
scope; it does not approve unreviewed contract changes or waive acceptance gates.

The next dependency is report-model task 8: resolve the shared guard and typed
failure contracts, then register report preparation through the existing facade.
Snapshot task 5.1 supplies retained binding identities and exact run pins. These
allow GridCraft task 4's candidate to consume real inputs rather than test-only
run metadata. Subsequent lifecycle and app tasks must establish ten-second
updates and shared controls in the exact visible session, followed by verified
export, interruption handling and the installed adopter journey.

Use read-only parallel analysis for independent integration questions; serialize
shared provider/schema changes and task acceptance. Prefer existing library and
guard reuse over additional frameworks. Measure concrete changes against current
budgets before seeking any calibration. Automated browser work stays headless;
visible operator acceptance remains a separate required check.

Progress reports should distinguish accepted producer/report/app behavior from
component experiments. Count a milestone only when the ordinary caller can use
it through the intended interface and its required effects have been verified.
