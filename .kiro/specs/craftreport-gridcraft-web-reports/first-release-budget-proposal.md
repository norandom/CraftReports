# First-release GridCraft budget proposal

Status: proposed, not approved. Date: 2026-10-25.

## Decision requested

Raise only the `gridcraft` production aggregate from 2,000 to 2,600 LLOC
for the already approved first-release scope. Keep function 50, module 300,
McCabe 10, all other capability limits and all acceptance requirements unchanged.
No quality policy changes are authorized by this proposal alone.

The fresh quality gate reports 2,185 LLOC and exactly one violation:
`gridcraft: 2185 > 2000`. Task 12 remains open and export unavailable.
The ownership amendment approved today explicitly did not increase this budget.

## Evidence and allocation

The read-only [reuse audit](../../../artifacts/task12-repair-2026-10-25/budget-reuse-audit.md)
identifies concrete simplifications, existing library use and remaining work.
Pydantic, Playwright, openpyxl, XlsxWriter and the existing kernel already supply
their respective infrastructure. The audit found no credible complete fit at
2,000 without removing required behavior. Estimates are planning allocations,
not completed implementation or an entitlement to add code.

| Allocation | LLOC |
| --- | ---: |
| Current measured source | 2,185 |
| Planned concrete simplification | -35 |
| Remaining task 12, including review corrections and shared two-pass export | 220 |
| Task 13 recovery using existing runtime/kernel | 120 |
| Reusable app lifecycle/composition for task 15 | 40 |
| Installed acceptance correction allowance | 70 |
| Proposed maximum | 2,600 |

Simplifications should use existing Playwright waiting, standard-library lock
cleanup and shared workbook/staged-byte inspection where they demonstrably
reduce duplication. Do not change canonical fact bytes for convenience. Do not
move app logic to another owner or JavaScript, minify, or remove safety checks.
If the assumed savings or remaining allocations prove inadequate, stop and
report the measured delta; no automatic increase is granted.

## Enforcement and acceptance

If approved, add a prerequisite development-gate task to enforce exactly 2,600
with regression checks that other limits remain unchanged. Record approval in
quality.toml and specification tracking before further task 12 expansion.
Independent review and canonical checks remain required before committing.
Any cohesive module extraction must stay under GridCraft aggregate ownership
and respect the import map. No new feature scope is activated.

The publication contract subset still needs independent correctness review.
Budget approval does not accept that subset, task 12, or the release. Actual
final designation, composed REST/MCP export, retained trustworthy evidence,
fresh-context XLSX reopen, screenshots/video and recovery proof remain required.
Task 13 starts only after task 12 acceptance. Example scripts retain their
existing separate ownership and budget; reusable lifecycle code stays here.

Accountable owner: project maintainer. Scope: GridCraft first-release production
capability only. Review this allocation again at first-release acceptance;
later scope expansion requires a separate decision.
