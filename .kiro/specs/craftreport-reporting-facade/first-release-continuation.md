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

## Execution constraints

Continue the existing approved task dependency order, with independent review,
fresh task evidence, selective hooked commits and pushes to main. Preserve
unrelated worktree changes. Run Windows tests and headless browser verification;
Debian WSL supplies Docker hosting only. Use downloaded GridCraft releases,
without local Rust compilation. Existing ownership and numeric limits remain.
This continuation does not authorize new budget exceptions or silently changed
acceptance contracts. Prefer existing libraries and deletions over new generic
infrastructure; report concrete conflicts with a reviewable correction.

The accepted baseline is b0d4e3e, with 10/19 snapshot-runtime, 8/13 report-model
and 3/16 GridCraft tasks accepted. Task checklists remain the live status source.
The next dependency is snapshot-runtime 4.1, then its installed producer journey
and reporting operation registration. Existing GridCraft candidate work remains
unaccepted until its required implementation and real application proof pass.
