# Independent facade amendment design review

- VERDICT: APPROVED (design/task proposal only)
- TASK: Repaired frozen facade-integration-amendment.md design/task proposal, reviewed 2026-10-16.
- REVIEWED_SHA256: EF79A5C361EB58052BBE618446E753F1962DE480410949617D7D0452D0520ECB
- MECHANICAL_RESULTS: Source/spec inspection only; no tests, Git, browser, process or platform checks run. RED phase N/A. No production changes reviewed or accepted. Reviewer owns only this artifact.

## Resolved correction

The initial frozen proposal was rejected because its failure result had no supported output bound. `data/requirements.py:127` and `:147` produce one issue per null cell/value. A compact admitted snapshot can expand into many repeated dataset/field names and issue wrappers. The success-result 6S bound does not bound these failures. The revised hash above resolves this concern explicitly.

The revision defines `ReportFailure = {stage, code, recovery, issues, total_issue_count, omitted_issue_count}`. It returns the first at most 64 issues in existing checker order, preserves included codes/locations, reports the exact total, and validates the omitted count and included length. Its declared detail sample, 4096-byte per-issue bound, eight location components, 128-byte canonical string components, bounded integers and 263168-byte envelope fit the unchanged validation/preparation limits. Existing report name and resolved-reference checks establish the location string bound; selected names match those requirements, so arbitrary unused upstream names are not copied into these issues. This does not introduce new source input restrictions. The checker is reused once with no new accumulator or pagination subsystem. Required verification now covers zero/64/65/many issues, maximal names/indices, typed roundtrip, count consistency and truthful overflow. No mandatory remediation remains for this proposal.

The three existing issue vocabularies are disjoint (`DefinitionCode`, `BindingCode`, `ThemeCode`). Their common two-field shape is therefore not intrinsically ambiguous. Specify code-discriminated decoding using those exact Literal vocabularies, with unknown codes/fields rejected and typed roundtrip checks; no extra issue tag is necessary.

## Findings without required redesign

- **Guard identity:** The single concrete `DurableGuard` assembled before activation addresses the real `DurableResources.apply` owner check and `DurableGuard.capture` active-task/original-lease requirement. The proposal correctly distinguishes caller preconditions from independently observed full completion pins. No wrapper lease or second guard authority is needed.
- **Ordering:** The proposed callback follows both authorization checks, health/capability checks, retained retry lookup, reserve/acquisition and second retry lookup, immediately before journal admission. This preserves equivalent/conflicting retry handling. The required post-await original-lease check and ordinary rejection cleanup are necessary and correctly specified. The callback remains an explicit upstream scope amendment, not already authorized kernel behavior.
- **Minimality:** Reuse of the selected-theme resolver is justified by its conditional decimal/date property handling. A payload-only blanket rejection would overreject supported unused optional mappings. This bounded callback does not require a general middleware framework.
- **Diagnostic privacy:** Fixed public root locations and exact operator allowlists avoid promoting private field names into reusable receipt diagnostics. Detailed issue locations remain behind both source/artifact authorization and scoped reads. Missing/inaccessible packs remain indistinguishable. Unexpected exceptions remain kernel failures.
- **Import direction:** Moving `DiagnosticPolicy` to `application/service_values.py` is acyclic in the inspected source: that module depends on contracts and standard library, not registry/outcomes. Retaining the outcomes re-export preserves existing imports. Registry must import the new defining module, never the compatibility re-export.
- **Failure evidence:** Checking explicit stage state before missing evidence corrects the current failed-to-pending classification without making failure complete. The proposal preserves required passed-stage evidence, exact pins, independent readback and absent-stage pending status. Release-blocked preparation retains both real facts and its prepared result; no fabricated evidence is introduced.
- **Compatibility:** Version 1 is acceptable for this repository's unactivated operations, with updated catalog schemas and simultaneous ordinary-caller updates. Inspected `composition/reporting.py` contains only the compatibility callable and explicitly reserves capability activation for task 8; no report registration is present in composition or package entry points. Any external publication contrary to this repository state would reopen the version decision.
- **Capacity:** Unchanged engineering caps remain a separate unresolved blocker. This review authorizes no increase, ownership evasion or speculative savings. Whole-candidate and residual consumer measurement must precede expansion.

## First-release continuation assessment

The latest delivery-focus prose correctly prioritizes the existing visible producer/chart/XLSX outcome, identifies report task 8 and snapshot task 5.1 dependencies, and retains controls, exact visible session, export/reopen and installed adopter gates. It distinguishes accepted caller behavior from component experiments and explicitly withholds contract/budget approval. No correction to that new prose is required. Its dated baseline count is historical, with task checklists expressly authoritative; this review does not independently certify those acceptance counts or the referenced commit.

## Summary

The repaired proposal is approved as a coherent, bounded design/task correction; explicit owner scope approval, authoritative Design/Tasks updates, engineering capacity and production/runtime acceptance remain separate open gates.
