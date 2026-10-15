# Bounded headless continuation after the feasibility checkpoint

Status: proposed on 2026-10-15; owner approval pending. This document does not
change approved tasks, authorize implementation, or close missing coverage.

## Decision requested

Authorize tasks **4.1 and 4.2 only** to continue after task 3.4 acceptance, using
headless tests and diagnostics. Keep every existing acceptance criterion and
the 2,800 source-LLOC cap. Reassess before task 5.1; this decision does not
authorize foreground windows, waive either required profile, or approve a
budget increase.

## Reason for the amendment

Task 3.4 requires expansion to stop when required routes are blocked. Its
paired evidence establishes the Windows headless download-fallback route:
suppressed edit dispatch leaves B3 at 20 and is rejected; restored dispatch
completes edit, actual XLSX Save, byte inspection and fresh-context reopen.
The evidence is indexed in
`artifacts/browser-verification/task-3.4/review-index.json`.

The reviewed visual profile currently supports Windows headless only. Full
headed and Linux journeys required by task 5.1 remain unverified. The owner's
2026-10-15 instruction prohibits automated windows entering the foreground.
That instruction remains binding. Historical headed startup evidence does not
establish the complete workbook journey.

Tasks 4.1 and 4.2 finish evidence and lifecycle accountability at their existing
boundaries. They can improve the established route without claiming the missing
profile coverage. Their acceptance must still satisfy their own requirements,
including real platform ownership evidence where specified; this amendment
does not convert unavailable checks into passes.

## Exact plan change upon approval

Append this qualification to task 3.4's expansion-stop rule:

> After independent acceptance of the Windows headless sensitivity/recovery
> checkpoint, tasks 4.1 and 4.2 may proceed under the approved headless
> continuation amendment. Retain unsupported profile findings explicitly.
> Stop again before task 5.1 for the required profile/verification decision.

Retain task numbers, dependencies, boundaries and requirement mappings.
Record the approved amendment in `spec.json` and the implementation notes.
No other task, requirement, design boundary or numeric limit changes.

## Conditions and limits

- Run all automated checks headlessly. Do not activate native windows.
- Use existing typed adapters and the same real workbook/file path; retain
  independent review, source-bound evidence and task-by-task commits.
- Keep primary failures, cleanup failures and unexecuted stages separate.
  Unsupported profiles cannot receive a verified result.
- Do not publish full-feature completion or the adopter workflow before the
  remaining mandatory tasks and verification pass.
- Current measured source is 2,496/2,800 LLOC. The remaining estimate is
  uncertain; do not raise the cap, relocate ownership or weaken checks to fit.
  Stop for a separately reviewed correction if implementation cannot fit.
- Before task 5.1, present the concrete route to Linux calibration and headed
  review that respects the owner's environment constraints. Missing mandatory
  coverage remains open until evidenced or explicitly amended by the owner.

## Review and approval

Independent review: PASS on 2026-10-15 by
`/root/review_browser_sensitivity_3_4`. The reviewer confirmed the bounded
4.1/4.2 exception preserves all criteria, profile blockers and numeric limits.
This review is not owner approval.

Owner decision: pending. Approval applies only to the bounded continuation
above; elapsed time or general resume instructions do not approve this change.
