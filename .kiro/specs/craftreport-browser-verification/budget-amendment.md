# Browser verification budget calibration amendment

Status: owner-approved on 2026-10-14. Existing limits remain enforced until
new task 2.3 implements and independently verifies the bounded override.

## Decision requested

Approve a browser-verification capability source cap of **2,800 LLOC**, together
with the bounded gate task below. Retain **50 function LLOC, 300 module LLOC and
McCabe 10**, the global **1,500** default for all other capabilities, and every
approved browser acceptance requirement. No waiver is proposed.

## Why calibration is needed

The accepted foundation through task 2.1 measures 943 source LLOC. The unfinished
2.2 deployment snapshot measured 205, leaving 352 for browser startup, actual UI
interaction, visual observations, evidence, orchestration and the public recipe.
The original Design estimated 200 for values/configuration, 250 for inspectors,
and 250 for release/deployment combined. Accepted implementations already require
314, 409 and 220 respectively, before deployment. Retained task reviews establish
that these implement required identity, bounded-input and artifact checks.

A read-only independent calibration by `/root/browser_budget_calibration`
projects approximately 2,300–2,750 source LLOC. The concrete planning target is
2,493; 2,800 leaves 307 above that target. Canvas calibration and process/video
ownership remain uncertainties. Further expansion still requires review.

## Proposed Design allocation

| Responsibility | Measured accepted LLOC | Completed planning allocation |
| --- | ---: | ---: |
| Values/configuration/resource registry | 314 | 314 |
| Fixture records and bounded OOXML inspector | 409 | 409 |
| Official release acquisition | 220 | 220 |
| Deployment | — | 250 |
| Browser startup/lifecycle | — | 240 |
| Real UI interactions/readback/download | — | 290 |
| Visual profiles and comparisons | — | 220 |
| Evidence/finalization | — | 280 |
| Additional Journey orchestration/cleanup | — | 210 |
| Adopter CLI | — | 60 |
| **Total** | **943** | **2,493** |

Allocations are planning estimates, not separate allowances. Journey's existing
61 LLOC are included in the 314 subtotal; its planned completed module is 271.
Inspector ownership includes fixture records 134, xlsx 191 and xlsx_parts 84.
Every owned helper and recipe counts once across the whole capability; tests
remain separately measured. Moving files does not reset the budget.

Reuse existing typed values/results, the same observation path for before/after/
reopen, and the same Journey for CLI and both execution profiles. Keep geometry
and visual expectations declarative. Do not build a general automation framework
or weaken build/document identity, fresh clipboard, exclusive download,
independent live chart, finalized video or cleanup guarantees to meet the cap.

## Proposed task-plan amendment

After task 2.2 is accepted, insert a new executable **2.3: Implement the reviewed
browser capability budget amendment**, under Development-gates integration.
Renumber the existing browser startup task 2.3 to **2.4** and update task 3.1's
dependency to 2.4. The new 2.4 depends on 1.2, 2.2 and 2.3. There will be 19
executable tasks; prior accepted task numbers and commits remain unchanged.

The new 2.3 depends on task 2.2 and explicit owner approval of this amendment.
It owns the gate changes in scripts/quality_policy.py and scripts/check_quality.py,
quality.toml and focused tests under tests/engineering. It must:

- Parse a typed, approved capability-specific numeric limit for exactly
  browser-verification / capability-lloc / 2800, with accountable owner,
  rationale and approval reference. Do not take limits from CLI, environment
  or browser run configuration.
- Enforce that numeric maximum in whole-scope aggregate checks; all other
  capabilities retain the global default, and all local/branching limits stay.
- Reject unknown/unapproved capabilities, unsupported rules, wildcard/blanket
  scope, zero/negative/bool/noninteger values, duplicate entries and absent
  approval metadata. Approval reference must identify the owner decision.
- Prove browser 2,800 passes / 2,801 fails and another capability still fails
  at 1,501. Preserve 50/300/10 checks, complete owner accounting and separate
  test reporting. Use flag-off RED, GREEN and flag removal for changed behavior.
- Run focused engineering regressions and canonical fast checks; parent runs
  the installed hook through selective staging/commit. Required independent
  task review and one commit/push apply as usual.

Boundary: Development-gates budget enforcement integration. Requirements retain
2.6, 6.6 and 8.1; no product behavior or acceptance criterion changes. Design
references: Proposed Ownership and Budgets; File Structure Plan; Allowed
Dependencies. No source is relocated into tests/artifacts or another owner.

## Approval and application

AGENTS.md requires human review of Design/task changes. Engineering steering and
quality.toml require review before numeric budget changes. Once approved, record
the owner decision here, update Design's allocation, Tasks and metadata/counts,
and engineering/quality scope records; the new gate task is implemented and
reviewed before browser expansion. Do not change the enforcing default globally.

Task 2.2 can finish within the current limit. Until amendment approval and gate
acceptance, implementation remains subject to the existing 1,500 cap. This
amendment does not establish browser, reporting, financial or hosted-CI success.

## Independent proposal review

Reviewer `/root/review_browser_budget_amendment` returned PASS on 2026-10-14:
allocation arithmetic, existing module seams, Development-gates ownership,
acyclic task dependencies and bounded override regressions align. No required
fixes were found. This review is not owner approval or runtime acceptance.

## Owner decision

Approved on 2026-10-14 through the explicit amendment question: “Approve the
bounded amendment.” Approval covers the browser-only 2,800 aggregate cap and
task-plan changes described above. It retains all other limits and acceptance
checks. The gate task must be accepted before further browser source expansion.
