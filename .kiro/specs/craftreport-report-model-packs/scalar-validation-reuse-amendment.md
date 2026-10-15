# Prepared scalar validation reuse

Accepted under bounded overnight authorization. Independent plan PASS by
`/root/review_report_projection_4` for SHA-256
`29EBCD6828C221B41D4893020BB2D2FC2BCC90A8D479E9CBC07A6660B9F5DEA2`;
implementation delta independently APPROVED after real gate verification.
The task4 whole-scope hook rejected reporting.prepared importing the existing
pure data.validation.validate_scalar. Focused tests/type checks had passed, but
this import was outside the implemented exact reporting dependency boundary.
No commit landed and all unrelated work was restored.

Permit only craftreport.reporting.prepared to import the exact function
craftreport.data.validation.validate_scalar. Keep whole-module, wildcard, other
validation symbols and imports from other reporting modules forbidden. Implement
this two-field exception in the existing reporting_forbidden data branch; add
positive and adversarial negative fixtures to the existing boundary-gate tests.
This is a reused inward pure value invariant, not a wire parser, app effect,
calculation, new dependency, re-export or second validation implementation.

No production code changes are proposed: prepared values already call the
existing validator for exact values against their original Field schemas. The
shared validator remains owned by snapshot-runtime data; its behavior is not
modified. No numeric budget or application-core change is allowed.

Root owns scripts/check_imports.py and tests/engineering/test_boundary_gates.py
for this repair. Run failing-before then passing focused gate cases, real import
gate and independent review before retrying the installed whole-scope hook.
Task4 remains incomplete until that hook and selective commit succeed.
