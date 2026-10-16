# Independent review of shared adapter calibration

- Reviewer: `/root/review_adapter_budget`.
- Date: 2026-10-16.
- Verdict: **PASS for owner consideration; owner approval pending**.
- Proposal: [adapter-budget-calibration-amendment.md](adapter-budget-calibration-amendment.md).
- Exact reviewed proposal SHA256: `60C0F34477BCBD66B071459FDCB73CE56546EF68F16B0FCB859514B9178D62FD`.
- Implementation acceptance: **not granted**. Task 8 remains blocked until an owner decision and, if approved, accepted task 7.2 enforcement.

## Findings

The proposal correctly distinguishes accepted adapters (1,455 LLOC), the unintegrated report adapter candidate (74 LLOC), and unimplemented runtime estimates (120–200 LLOC). I independently measured the baseline and candidate with pinned Radon through `uv run python -c`, exit 0. The resulting complete-owner planning range is 1,649–1,729 with no credited deletions. The proposed 1,800 limit includes 71 lines above the upper estimate; that allowance is explicit contingency, not measured implementation or a guarantee. A new overrun still requires a new decision.

The candidate reuses the actual immutable pack reader, existing canonical serialization and atomic durable evidence retention/readback. The existing combined-read DurableGuard seam is approved. Pydantic/model_shape, Reference, ServiceTime and scalar codecs are existing paid-for reuse, not prospective line savings. Small duplicated reference conversions exist, but no measured behavior-preserving reduction establishes the 149–229 lines needed for complete fit at 1,500. The proposal does not claim impossibility, conceal app/runtime ownership or invent a generic framework.

I inspected the current task headings: there are 15 checked/unchecked headings including nonexecutable grouping task 2, therefore **14 executable tasks**. Adding executable task 7.2 gives **15 executable tasks**. Its proposed order after accepted 7.1 and before task 8 is coherent. The approval-dependent insertion and task-8 prerequisite preserve the existing task IDs and all other dependencies.

The root-owned gate scope maps to the existing `scripts/quality_policy.py` exact capability-limit allowlist and current engineering tests. Those files retain development-gates ownership; the new 1,800 value applies only to adapters. The proposed exact boundary tests, default-owner 1,500 enforcement, browser 3,400, storage 2,000, approval/reference checks and unchanged local 50/300/10 limits appropriately constrain enforcement. The proposal authorizes neither moving adapter algorithms nor relaxing required behavior.

No blocking proposal finding remains. Owner approval is required because the previously approved facade amendment expressly retains the 1,500 cap and requires a separate scope/design decision when fit is not established. This review approves the proposal's coherence for that decision, not the numeric change itself.

## Evidence and limitations

Ignored evidence under `artifacts/report-task8-budget/`:

| Artifact | SHA256 |
| --- | --- |
| report_resources.py | `816417C8802F7544F58E34500C77BD2BC694436F22E5CDD19361A08F945CDD09` |
| report_facts.py | `B776E9262C866B22671C212FE35206D217138E0FE073597FF9F7BFE130084CF9` |
| measurements.json | `E9C7DBB1BFA2A4BBFC4014ED1743A356199423C51ECE7C3D3481C3DEB8A29F23` |
| residual-assessment.md | `FA44FE84EC72B77141BD76C2E268ED42143477DEBB6F0C9488E30F79CD687DB7` |
| probes.txt | `FE358231D17DB8263D3B96F9740F182AD63F260BD3D9B8034A1BDA1231BFD2F8` |

The prototype's report-owned immutable value helper adds 48 reporting LLOC, not zero production code. The separately counted probe has 72 test LLOC. Its helper/source separation follows existing responsibility boundaries. Root/worker probe output reports five passing tests, with clean scoped typing/lint/branching logs. I inspected the probe and logs; I did not rerun them. They exercise real pack and storage collaborators but manually prepare command/guard context and do not prove public facade activation, authorization, original handoff flow, full lifecycle failures or installed REST/MCP acceptance. No browser/native/visible-live or XLSX saved-byte/reopen evidence is claimed.

The detailed ignored diagnosis is `artifacts/report-task8-budget/independent-review.md`: `CATEGORY: SPEC_CONFLICT`, `NEXT_ACTION: STOP_FOR_HUMAN`, high confidence in the present unmet fit prerequisite and medium confidence in the future estimate. Actual source expansion, exact gate verification, independent task review, hooked delivery, runtime codecs, guide/demo and final feature acceptance remain future work.
