# Shared adapter budget calibration proposal

Status: proposed for independent review and owner approval. This document does
not change an enforced limit or authorize production expansion.

## Decision requested

Raise only the existing `adapters` aggregate production budget from 1,500 to
1,800 logical lines for the already approved first-release report and runtime
interfaces. Keep function 50, module 300 and McCabe 10, all other capability
limits, ownership and acceptance requirements unchanged. No additional feature,
backend, generic serialization framework or app package is authorized.

## Why this decision is needed

Accepted source at `6811945` measures 1,455 adapter LLOC. The concrete isolated
report task 8 adapter candidate measures 74 additional LLOC, for 1,529 before
remaining runtime codecs. It reuses the existing durable guard through one
combined read callback, Pydantic typed projection and the existing atomic
preparation-fact retention/readback method. It adds no guard wrapper or journal.
The candidate is sizing evidence, not accepted task 8 implementation.

The previous 50–65-line report forecast underestimated these responsibilities.
The previous 55–75 runtime estimate covered only part of binding/inspection;
it did not cover the complete lifecycle/control/recovery boundary. Finishing
only report task 8 within today's allowance would not establish release fit.

| Shared adapter responsibility | LLOC basis |
| --- | ---: |
| Accepted source after report task 7.1 | 1,455 measured |
| Immutable report resources, health and fact conversion/retention adapter | 74 measured, unintegrated candidate |
| Shared tagged-parameter annotation using existing scalar codecs | 15–25 estimated |
| Binding/inspection and reusable durable binding/run wire representations | 65–105 estimated |
| Lifecycle/control request and state projections | 15–25 estimated |
| Reconciliation request/result projections | 25–45 estimated |
| Total before credited deletions | 1,649–1,729 planning range |

The proposed 1,800 cap leaves 71 above the upper planning estimate. Estimates
are not implementation or a guarantee of final fit. Every accepted task must
still satisfy the actual aggregate gate. Another overrun would require another
explicit decision. GridCraft-specific codecs remain in their already approved
app owner and add zero planned shared-adapter lines; their own budget still
applies. Runtime orchestration and persistence algorithms retain their existing
owners and limits.

## Reuse and alternatives considered

Existing `PydanticCodec`, `model_shape`, `construct`, `Reference`, `ServiceTime`
and exact tagged-scalar codecs already supply validation and conversion. Reuse
those library-backed paths; do not write another DTO/serialization framework.
The report candidate already delegates storage checks and readback to the
existing retained-fact method. These are current design savings, not future
line deletions that can be credited twice.

Small duplication remains in report snapshot-reference and parameter conversions.
A shared Pydantic scalar annotation may remove some explicit conversion code.
No unmeasured saving is included above. Retain exact success bytes, Decimal and
date meaning, null tags, closed schemas and error behavior when simplifying.
At the favorable forecast, keeping 1,500 would require at least 149 net deleted
lines; the upper forecast requires 229. No complete reviewed reduction of that
size has been established. Moving these conversions into composition, runtime
or the GridCraft package would conceal ownership rather than reduce complexity.

Dropping live controls, durable binding/run readback or recovery would reduce
scope but conflict with the agreed narrow release. This proposal retains those
features and avoids an unrelated serialization rewrite.

## Proposed task 7.2: enforce the approved adapter calibration

After owner approval, insert executable task 7.2 before report task 8. It depends
on accepted 7.1 and this approval. Existing task IDs remain unchanged; the report
spec then has 15 executable tasks. Task 8 depends on accepted 7.2 as well as its
existing prerequisites. Do not insert or mark this task accepted before approval.

Root-owned scope: `quality.toml`, the existing exact-limit policy loader and
quality gate, focused `tests/engineering` checks and matching steering/spec
approval metadata. Reuse the installed capability-limit mechanism. Add no new
gate framework. Prove adapters 1,800 passes and 1,801 fails; unexcepted owners
still fail at 1,501; browser 3,400 and snapshot-storage 2,000 remain exact.
Preserve strict scope/reference approval checks and local 50/300/10 limits.

Follow RED/GREEN/removal, independent review, matching canonical checks, a
selective hooked commit and push before resuming report task 8. Runtime codec
implementation remains in its approved task sequence. Approval changes only
the numeric allocation and prerequisite gate task, not the open implementation,
installed-client, guide/demo, visible-live or XLSX/reopen acceptance gates.

## Evidence

Local sizing and scope assessment: `artifacts/report-task8-budget/` including
`report_resources.py`, `report_facts.py` and `residual-assessment.md`. Record
final hashes, actual measurement commands/results and independent diagnosis
in the accompanying review before owner approval. No browser or production
report operation has been exercised by this budget investigation.
