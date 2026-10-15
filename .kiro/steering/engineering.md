# Typed Python and Engineering Gates

Updated: 2026-10-15. Kernel tool selections and numeric budgets are approved; browser-verification tooling has its own approved scope using 50/300/3,400/10 limits; its bounded aggregate amendment gate is implemented and independently verified in task 4.0 (following historical task 2.3), with implementation now authorized by Tasks approval. Tasks 1.1–1.2 installed the locked tools and verified the standalone size/branching gate; task 1.4 has passing fast-check, installed-hook and clean-checkout evidence. CI uses the same command; [hosted run 38617747132](https://github.com/norandom/CraftReports/actions/runs/38617747132) passed fast checks and installed-wheel synthetic conformance on 2026-10-14 at commit 44d3101 (verified 2026-10-15). Browser CI remains pending.

## Typed Contracts and Boundaries

Use typed Python for the core, public operations, adapters, results and errors. Explicitly validate untrusted runtime inputs and dataframe schemas at ingress. Static typing does not validate financial methodology or serialized input values.

Use the approved Pyright strict selection for the kernel, pin its version/configuration and check its complete source/scripts/tests scope. Avoid broad unknown/Any types in business contracts or blanket ignores that erase boundary checks.

Keep domain/report contracts independent of app sessions, frameworks and storage handles. Check allowed imports mechanically once source exists. Boundary-safe extraction is required; passing size checks does not permit hidden shared ownership.

The user prefers avoiding handwritten SQL. Candidate structure uses functional validation/calculation/compilation and small OOP repositories/adapters/runtime boundaries. Typed ORM/query expressions belong in persistence/source adapters; domain functions and report definitions do not receive ORM sessions or arbitrary SQL. Isolate unavoidable engine-specific operations with rationale and tests. ORM/database selection remains a design decision; see the spec's data architecture options.

## Ruff and Pre-Commit

Ruff linting and formatting are mandatory. Ruff is not the static typechecker. Pin tool versions and apply the same configuration locally and in CI.

Pre-commit hooks are mandatory before implementation changes land. The approved foundation implementation must provide/install the hook configuration and its canonical checks; a prose requirement or hook file alone is not proof that it runs.

Required check families: Ruff lint/format, selected strict typing, complexity/size budgets, breadth/ownership ledger validation, and focused fast checks appropriate to the change. Repository-wide aggregate checks cannot rely only on staged Python filenames.

CI executes the same checks over the relevant complete scope, so skipping a local hook cannot make unvalidated work acceptable. Slow Compose/browser/artifact verification runs as a dedicated integration stage rather than blocking every local edit unnecessarily.

## Separate Size and Branching Budgets

LLOC measures logical source size; branching complexity measures control-flow difficulty. Track both independently. Proposed measurement direction is pinned Radon raw LLOC plus Ruff C901/McCabe branching checks.

Feature/capability budgets reference stable IDs in `breadth.toml`. Module and function budgets complement them. Count each owned source file once in its capability's aggregate; keep test size separately visible and declare generated/vendor exclusions.

Do not game caps by moving a feature across many tiny files. Extraction follows a responsibility seam, and the feature/capability aggregate still applies.

`quality.toml` owns tool/measurement definitions, inclusion policy, numeric limits and narrowly scoped exceptions. Kernel Design approval adopted 50 function LLOC, 300 module LLOC, 1,500 capability LLOC and function McCabe complexity 10 for its listed capabilities. The standalone size/branching gate now enforces these limits; the installed local hook invokes the complete fast pipeline, and CI is configured with that same command. Hosted fast and synthetic integration execution is verified by the run above. Its approved extraction policy includes decorators through function end and checks nested functions without double-counting files in capability totals. Calibrate against the first vertical slice; changes require review. Browser-verification tooling adopted 50/300/1,500/10 through owner Design approval on 2026-10-14; a subsequently approved calibration amendment changes only its aggregate cap to 2,800. The exact numeric override is implemented in task 2.3, with other defaults unchanged. See `.kiro/specs/craftreport-browser-verification/budget-amendment.md`; task 2.3 accepted enforcement of that exact override while all other capabilities retain the global 1,500 default. On 2026-10-15 the owner explicitly approved the resource-specific lifecycle
contract and browser-only 3,400 aggregate cap in
`.kiro/specs/craftreport-browser-verification/lifecycle-evidence-budget-amendment.md`,
following independent proposal review PASS. New Development-gates task 4.0 owns
implementation and independent verification; it is now accepted, with exact
3,400 enforcement and 848 tests/93 subtests passing independent canonical checks.
Accepted task 4.1 source is now measured 2,798/3,400,
leaving 602. The unchanged planning allocations forecast 3,403, 3 above the approved
3,400 maximum; these are estimates, not caps or proof of infeasibility, and imply
no further cap increase or hidden refactor savings. All other capabilities retain
1,500 and local 50/300/10 limits remain unchanged. SDK closure is `sdk-closed`
only for the identified public Playwright boundary; directly owned subprocess
shutdown still requires observed non-forced exit. Observable cleanup failures
remain acceptance-blocking and the immutable SDK observation limitation stays
scoped to its boundary/version. Other future capability budgets require their own activation review. An omitted override in approved scope means the approved default, not unlimited or zero.

Exceptions need an exact capability/path/rule, rationale, accountable owner, approval reference and expiry. Expired or overbroad exceptions fail; they do not silently renew. Core library/application code and externally maintained Craft/Rust code have separate ownership.

## Agent Work Allocation

Owner-confirmed on 2026-10-15: at each task start and material bottleneck,
consider parallel agents, model selection and workflow changes to shorten delivery.
Delegate independent work when useful; do not add agents merely to fill slots.
Choose available models to fit the work: a coding model for implementation and
routine evidence audits, stronger reasoning for difficult contracts and adversarial
review, and a lightweight model for narrow inventories. Model overrides are
authorized for this purpose; use fresh contexts and focused task inputs.

Assign nonoverlapping file or responsibility ownership. Run read-only contract
and evidence audits alongside implementation so findings arrive before expensive
runtime verification. Freeze source after known fixes, then collect matching
runtime evidence. Serialize heavy browser, platform and canonical checks when
shared resources would cause contention. All automated browser work remains
headless under the owner's current instruction.

Keep Kiro task acceptance sequential: independent final review, fresh evidence,
selective commit with installed hooks, then push. Parallel support within a task
does not activate unapproved tasks or replace the required final review. The
parent owns integration and commits; workers preserve each other's changes.

## Git Delivery Workflow

Owner-confirmed on 2026-10-14: work directly on `main`; do not create feature
branches or worktrees for routine tasks. After each task passes its required
review and fresh checks, selectively stage its owned files, run the installed
pre-commit hooks through the commit, and push the accepted task to `origin/main`.
Do not batch unrelated tasks into one commit or include unfinished work in a
push. Existing unrelated local changes remain untouched. The configured remote
is `https://github.com/norandom/CraftReports.git`.

## Verification and Release

Fast engineering checks, runtime/browser behavior, numerical evidence and artifact fidelity answer different questions. None substitutes for the others.

Use the project's documented canonical commands and record their real results. Until tools/scripts are implemented, list them as pending rather than inventing a passing run. Engineering policy does not waive the Kiro approval workflow or authorize publishing/merging.

Sources: [Ruff integration](https://docs.astral.sh/ruff/integrations/#pre-commit), [Ruff FAQ](https://docs.astral.sh/ruff/faq/), [Ruff C901](https://docs.astral.sh/ruff/rules/complex-structure/), [Radon metrics](https://radon.readthedocs.io/en/stable/api.html), [pre-commit](https://pre-commit.com/).
