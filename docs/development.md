# Develop the CraftReport kernel

Start by reproducing the engineering checks, then choose an approved kernel task.
There is no completed CraftReport server quick start yet. The current executable
work covers value contracts, operation registration, capability activation,
guards and related kernel collaborators; the
[task list](../.kiro/specs/craftreport-operation-kernel/tasks.md) records the
remaining implementation and review gates.

## Create the locked environment

Use Git, CPython 3.12.10 and uv 0.13.0. Run from the checkout root:

```sh
uv --version
uv sync --frozen --group dev
uv run --frozen python --version
uv run --frozen python scripts/check.py --fast
uv run --frozen pre-commit install
uv run --frozen pre-commit run --all-files
```

In PowerShell on the development workstation, replace `uv` with `uv.exe`.
The workstation's `uv` wrapper and Windows Store `python` alias are not reliable
ways to select this environment. Use the project environment through uv. A
Linux/WSL checkout should create its own environment; do not reuse a Windows
`.venv` in Linux.

`--frozen` preserves the dependency lock. If a dependency needs changing, treat
the manifest and lock update as part of the reviewed change. No database, Craft
app, AI service or private pack is needed for the fast kernel checks.

## Find the owner before editing

| Location | Responsibility |
| --- | --- |
| `src/craftreport/contracts/` | Immutable identities, operations, capabilities and outcomes |
| `src/craftreport/application/` | Registry, shared guards, evidence and execution contracts |
| `src/craftreport/adapters/` | Boundary validation and canonical wire values |
| `src/craftreport/composition/` | Explicit capability selection, settings and activation |
| `tests/kernel/` | Kernel behavior and installed fixture checks |
| `tests/fixtures/kernel_plugin/` | Separately packaged synthetic capability |
| `scripts/` | Whole-scope engineering checks |

Read the core steering files (`product.md`, `tech.md`, `structure.md`) and the
scope/verification files (`overview.md`, `testing.md`, `engineering.md`,
`breadth.md`) in [.kiro/steering](../.kiro/steering/). Consult
[breadth.toml](../breadth.toml) for actual and planned owners. Register new scope
before expanding tasks or code; parked extensions require their own activation.
Requirements, design and tasks retain separate human approval gates.

Keep framework, database and live-app handles out of value contracts. App and
storage adapters implement narrow application ports. Interfaces must use shared
guards rather than creating another authorization, retry or completion path.
Use the [capability author guide](capability-authoring.md) for the executable
packaging example and its installed-wheel verification command.

## Choose the check that answers your question

```sh
# Whole-scope local engineering gate; also used by the hook and CI.
uv run --frozen python scripts/check.py --fast

# Focused feedback while editing a capability contract.
uv run --frozen python -m pytest -q tests/kernel/test_fixture_packaging.py
uv run --frozen python -m pytest -q tests/kernel/test_activation.py

# Reserved integration entry point: currently reports unavailable and exits 1.
uv run --frozen python scripts/check.py --integration
```

The fast gate runs Ruff lint/format, Pyright strict, approved size and branching
budgets, breadth and retirement aging, import boundaries and tests excluding the
`integration` marker. It checks the whole declared scope, including unstaged
files. Missing tools and failed checks stop the pipeline with a nonzero exit.
Tests have separate size accounting from production code.

The installed hook takes no staged filenames and runs the whole-scope gate.
Install it for each clone. [CI](../.github/workflows/kernel.yml) uses the same
command on pushes, pull requests, manual runs and a daily schedule. Hosted CI
execution has not yet been verified. Its separate conformance job is explicitly
skipped pending the installed-system harness.

## Verify the effect you promise

A typed result or successful request can establish acceptance without proving a
workbook changed. Keep input acceptance, target mutation, file persistence,
reopen verification and numerical validation separate in results and tests.

For an app path, record the exact app build, execution mode, page/session,
document, fixture and output file. Use an isolated project browser context and
Compose project. Capture browser screenshots/video and console/network failures
for critical journeys, then inspect actual exported bytes and reopen them where
the requirement promises it. A native or headless engine result cannot establish
the state of a browser workbook.

Start with [GridCraft hosting](gridcraft-setup.md) to obtain a real browser app.
That guide establishes how to serve the release; app control and report
integration still need their own contracts and evidence. If a check cannot run,
record the missing environment or capability and leave that claim pending.

## Make a change reviewable

Describe the observable problem, the owning task and the resulting behavior.
Include the checks actually run and any remaining limits. Check
[quality.toml](../quality.toml) before changing budgets or exceptions, and keep
source, tests, ownership and documentation aligned. The
[completion rules](../.kiro/steering/testing.md#kiro-completion-gate) require fresh
evidence before task or feature completion claims.

For onboarding, a useful first review is one existing synthetic capability test:
trace its descriptor, typed input, handler and observed effect together. If that
trace reveals an undocumented dependency or requires private data, this guide's
claim that a contributor can reproduce the kernel checks is wrong; fix the
environment or instructions before treating the contributor's setup as a failure.
