# Independent storage calibration proposal review

Reviewed 2026-10-16 by `/root/release_budget_review` using
`.agents/skills/kiro-review/SKILL.md`. This is proposal review, not task acceptance
or owner approval of a numeric change.

## Review Verdict
- VERDICT: APPROVED
- TASK: Proposed snapshot-runtime task 4.0 and storage budget calibration
- REVIEWED_SHA256: `5354B5E93315E8A7395DEAA675AF43BAD0C01ED2DA132C394805E56F1B1E4237`
- REVIEWED_FILE: `storage-budget-calibration-amendment.md`
- MECHANICAL_RESULTS:
  - Tests: N/A; documentation-only proposal, no behavioral implementation under review. No whole suite or future gate result is claimed.
  - Measurements: PASS; installed `uv.exe run --frozen python` with `radon.raw.analyze` independently measured current storage source at 1,393 LLOC and the unintegrated `storage-candidate.py.txt` at 176 LLOC (exit 0).
  - Arithmetic/task count: PASS; Python independently reproduced 1,804–1,949, and counted 19 existing executable tasks; inserting 4.0 yields 20 (exit 0).
  - TBD/TODO grep: CLEAN; no placeholder matches in the proposal.
  - Secrets grep: CLEAN; no concrete credential matches in the proposal; manually inspected text.
  - Static checks: SPOT_CHECKED; read actual `scripts/quality_policy.py`, existing browser budget fixtures, `quality.toml` and ownership ledger. No executable changes to lint.
  - Boundary: WITHIN; this reviewer writes only this report. Existing unrelated working changes were inspected by diff summary and left untouched.
  - Boundary audit: CLEAN; snapshot-storage remains the most-specific owner of `src/craftreport/adapters/storage`; tooling remains development-gates. No runtime ownership reassignment is authorized.
  - RED phase: N/A for proposal; required for future enforcing task 4.0.
- FINDINGS:
  1. FYI — The measured baseline and partial candidate are reproducible. The remaining allocations are planning estimates, not measured implementations. Neither the 51-line upper-range margin nor the proposed 2,000 cap proves all remaining release work will fit. The proposal states this honestly, credits none of the 34 potential deletions, and preserves blocking enforcement if the cap is exceeded. This is an explicit bounded owner choice, not a demonstrated mathematical minimum.
  2. FYI — Current enforcement cannot accept a snapshot override merely by editing TOML. `validate_capability_limit` permits only browser-verification/3,400, and `validate_limit_approval` hardcodes its exact approval reference and singular scope metadata. The proposed task explicitly owns this loader as well as policy and tests, so its scope can implement the change. Its implementation must add the exact snapshot-storage/2,000 pairing and approval-reference/scope validation while preserving the browser pairing, duplicate/type/unknown-owner rejection, and global fallback. The snapshot scope currently has plural `capability_ids`; that difference must be handled explicitly rather than weakening metadata checks.
  3. FYI — Task ordering is consistent: accepted 3.5 precedes proposed 4.0, and blocked 4.1 retains its current prerequisites plus 4.0. After owner approval, integration must update the actual task list, Design budget text, scope/approval metadata and executable count together; this document does not perform those updates or invalidate historical review hashes by pretending they cover revised text.
  4. FYI — Existing tasks 5.1–5.4 and requirements 3–6 retain binding/run persistence, conditional progress, lifecycle and recovery obligations. All later storage changes, including persistence needed by effect observation/control, count against the same cap regardless of the table's task labels. The proposal does not authorize omitting these responsibilities. Actual saved XLSX/browser verification remain downstream release obligations, not newly claimed snapshot-runtime evidence.
  5. FYI — The optional selection responsibility amendment is expressly excluded. Continue the accepted publication/query contract, including operation-specific decision evidence, authorization, retained identities and bounded latest-complete selection. Reuse reductions require their stated serialization, rollback and corrupt-schema regressions; no savings are accepted in advance.
- REMEDIATION: None required for this proposal. Owner approval of the numeric increase is still required before activation. Future task 4.0 must deliver its specified boundary tests, independent review and installed-hook evidence before task 4.1 resumes.
- SUMMARY: The narrow 1,500-to-2,000 storage-only proposal is internally consistent and suitable for an explicit owner decision; it neither implements the increase nor proves complete-release fit.

Review inputs included AGENTS.md, core and CraftReport steering, breadth/quality
policy, actual snapshot requirements/Design/tasks/spec metadata, the sizing and
debug artifacts cited by the proposal, and existing policy-loader/test source.
Independent debug's STOP_FOR_HUMAN remains consistent with this review: general
release authorization does not approve the numeric increase.
