# First-release GridCraft budget calibration approval

On 2026-10-28 the owner explicitly approved the independently reviewed
GridCraft-only 2,600-LLOC calibration and prerequisite gate task 12.0.

- Proposal: [first-release-budget-proposal.md](first-release-budget-proposal.md).
- Exact reviewed SHA256: `3f8c8b5268cebc7759f403627c7d189d45ae7dff82da329234009d5bb1d54472`.
- Independent review: [first-release-budget-review.md](first-release-budget-review.md), PASS for presentation to the owner.

This approves the bounded specification/policy update and implementation of the
exact gate in task 12.0. It changes only the `gridcraft` production aggregate
from 2,000 to 2,600 LLOC; local function/module/complexity 50/300/10, all other
capability owners, import boundaries and acceptance gates remain unchanged.
Implementation acceptance of task 12.0 requires reviewed enforcing tests and a
hooked commit before task 12 expansion resumes. This approval does not accept
the unverified publication subset or close task 12.
