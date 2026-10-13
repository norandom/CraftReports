# Typed Python and Engineering Gates

Updated: 2026-10-13. Kernel tool selections and numeric budgets are approved. Tasks 1.1–1.2 installed the locked tools and verified the standalone size/branching gate; task 1.4 has passing fast-check, installed-hook and clean-checkout evidence. CI uses the same command but has not run remotely.

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

`quality.toml` owns tool/measurement definitions, inclusion policy, numeric limits and narrowly scoped exceptions. Kernel Design approval adopted 50 function LLOC, 300 module LLOC, 1,500 capability LLOC and function McCabe complexity 10 for its listed capabilities. The standalone size/branching gate now enforces these limits; the installed local hook invokes the complete fast pipeline, and CI is configured with that same command. Hosted CI remains unverified. Its approved extraction policy includes decorators through function end and checks nested functions without double-counting files in capability totals. Calibrate against the first vertical slice; changes require review. Future capability budgets require their own activation review. An omitted override in approved scope means the approved default, not unlimited or zero.

Exceptions need an exact capability/path/rule, rationale, accountable owner, approval reference and expiry. Expired or overbroad exceptions fail; they do not silently renew. Core library/application code and externally maintained Craft/Rust code have separate ownership.

## Verification and Release

Fast engineering checks, runtime/browser behavior, numerical evidence and artifact fidelity answer different questions. None substitutes for the others.

Use the project's documented canonical commands and record their real results. Until tools/scripts are implemented, list them as pending rather than inventing a passing run. Engineering policy does not waive the Kiro approval workflow or authorize publishing/merging.

Sources: [Ruff integration](https://docs.astral.sh/ruff/integrations/#pre-commit), [Ruff FAQ](https://docs.astral.sh/ruff/faq/), [Ruff C901](https://docs.astral.sh/ruff/rules/complex-structure/), [Radon metrics](https://radon.readthedocs.io/en/stable/api.html), [pre-commit](https://pre-commit.com/).
