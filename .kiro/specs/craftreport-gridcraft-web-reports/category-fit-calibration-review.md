# Independent category-fit calibration review

- **VERDICT: APPROVED** as a bounded Design correction proposal only.
- Reviewer: `/root/review_category_fit`; date: 2026-10-16.
- Reviewed proposal: `category-fit-calibration-amendment.md`.
- SHA-256: `79e134485806815705d7e07bf3ffe20f31534c69f162c87c802fc6fdf1e91504`.
- Owner approval is still required. This review grants no implementation GO, supported-profile status, task-4 completion or production acceptance.

## Review basis and scope

Read the project instructions, core steering and overview/testing/engineering/breadth/documentation guidance, ownership/budget declarations, GridCraft requirements, WorkbookMapping Design, task 4, profile-support amendment and the exact proposal. Applied the Kiro review protocol to this proposal/evidence review. The canonical publication hook temporarily isolated tracked WIP; original profile amendment and retained run sources supplied the proposed-profile context. No production source, proposal, metadata, tests or retained evidence was changed by this review.

The change remains within GridCraft admission and disclosure ownership. It narrows category admission to 16 serialized UTF-8 bytes and retains literal admission at 32. Equal table/chart categories, no truncation/coercion, fixed geometry, exact theme, supplied-descriptor semantics and existing engineering caps remain intact. This is consistent with requirements 1.1–1.5, 2.1–2.7, 4.3–4.5 and 6.4–6.6: visible omissions must defeat mechanical equality, and unsupported requests must reject before mutation.

## Mechanical and visual results

- Read-only `git diff` and direct proposal/source inspection; no implementation diff acceptance was attempted.
- Independently recomputed the proposal hash and all five evidence hashes printed in its table: all match.
- Inspected the failed update screenshot, narrowed update screenshot and narrowed fresh-reopen screenshot at 1600 by 1100. The failed case shows the first long label and Gamma, omitting the second label and Delta. The narrowed update and reopen show all four labels, without visible overlap or clipping in these screenshots.
- Both property manifests contain 481 records per checkpoint: 480 comparisons with expected values, plus informational `chart.gap_encoding` (absent OOXML `dispBlanksAs`, interpreted as the gap default). All recorded equality flags are true. The proposal's 480-comparison count is correct under this distinction. The failed run has five checkpoints and the diagnostic four.
- Independently read actual saved drawing XML: both update artifacts retain `(0,0,17,0,5,161925,34,57150)`, consistent with A18 through F35 plus offsets inside the reservation.
- The proposed Delta region has zero dark neutral pixels in the failed update and positive ink in narrowed update/reopen. Reproduced 45 pixels in the narrowed update with RGB `max(channel) < 220` and `max(channel)-min(channel) < 30`, using half-open crop `(475,574,520,585)`. A stricter threshold gives a different count but the same absence/presence result.
- Retained logs report one pass in 358.64 seconds for the failed visible-profile run and one pass/one deselection in 224.03 seconds for the narrower diagnostic. These are retained mechanical outcomes, not newly executed tests or a visible-profile pass.
- Retained diagnostic source explicitly labels `category_diagnostic_only`, takes only the first update in the 16-byte case and uses the ordinary candidate admission path. Boundary inputs preserve 32-byte literal cases and evaluator-produced paired quality. Thus the proposal correctly does not claim that the diagnostic completed the two-update revised-profile acceptance journey.
- Read-only hash/manifest/XML/pixel checks exited zero. No browser, canonical suite or installed-package test was launched for this documentation review. Those implementation acceptance checks remain open. No new placeholder or credential content was found in the proposal.

## Findings and remaining gates

1. **FYI — byte count is not a universal text-width proof.** The 16-byte rule is a precise admission bound, including JSON quotes/escapes, not a mathematical width bound. Fourteen ASCII W characters and seven accented letters do not exhaust admitted Unicode, shaping, combining sequences or fallback glyphs. The proposal correctly keeps the profile untested, freezes theme/browser/geometry and calls for independent full-label review. Future acceptance must not describe this diagnostic or the Delta oracle as proving every permitted string. Any observed fit failure still requires rejection/unavailability or another reviewed narrowing; a font, geometry or rendering-profile change requires new evidence.
2. **Suggestion — freeze the pixel predicate with its oracle.** Include the exact channel threshold and neutrality rule, crop coordinates, screenshot identity and positive controls in the eventual retained measurement. The number 45 is reproducible, but the proposal does not specify its threshold. This does not block the correction proposal because the oracle is prospective and manual inspection independently confirms this failure. Delta ink alone cannot establish correct text or all four labels.
3. **FYI — fixture and profile identities must stay distinct.** The diagnostic exercised narrower inputs under the existing admission/profile pin; it establishes feasibility only. After owner approval, change the canonical profile declaration/digest, category and literal admission checks, rejection expectations and disclosures together. Freeze that candidate before collecting revised evidence; never relabel old evidence as a passing revised production profile.
4. **FYI — acceptance remains open.** Preserve the failed 32-byte run. Require independent ASCII/non-ASCII/escaped boundary and above-limit checks, both same-document updates, real Saves, matching artifact/property/outside signatures, fresh reopen and separate visible-fit verdicts. Installed-package proof, applicable actual quality-summary/presentation evidence, accepted runtime 5.1 for RunPins integration, later guarded operations/publication, executable quickstart/demo and independent headed verification remain mandatory. Constructor-only maximum-summary diagnostics cannot establish policy support.

## Remediation and summary

No blocking proposal remediation. The small oracle reproducibility clarification can be incorporated when implementing the prospective regression. Approve presenting this exact bounded correction to the owner; retain the public profile as untested and task 4 as incomplete until its separately required acceptance evidence and reviews pass.
