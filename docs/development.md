# Develop the CraftReport kernel

Start by reproducing the engineering checks, then choose an approved kernel task.
The installed harness provides an isolated synthetic service for verification.
The current executable work includes [host assembly](kernel-host.md), operation registration, capability
activation, shared guards and REST/MCP interfaces; the
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

# Contract coverage, installed client journeys, then catalog verification.
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
execution has not yet been verified. The separate integration command records
synthetic conformance evidence. Both phases must pass; hosted CI execution remains unverified.

## Run the installed harness

From the locked development environment, run:

```powershell
uv.exe run --frozen python scripts/check.py --integration
```

Use `uv` in place of `uv.exe` outside the Windows workstation. The harness builds
wheels for the kernel and synthetic capability, then installs them offline in an
isolated environment. The composed service owns one loopback listener. Generated
credentials travel through pipes only. REST and official MCP clients exercise discovery, commands, query readback,
retained retries, permissions and limits without an AI service or private pack.
The run also exercises deliberate startup and cleanup failures, disconnects after
admission, twenty concurrent retries, unavailable guarantees, post-effect uncertainty,
capacity and bounded shutdown.

Inspect the run directory printed by the command:

| Artifact under `artifacts/<run-id>/` | What to inspect |
| --- | --- |
| `kernel-manifest.json` | Immutable packet: installed identity, cases, cleanup, scope and artifact hashes |
| `verification.json` | Derived status and SHA-256 of the exact persisted packet bytes |
| `coverage.json`, `required-cases.json` | All 36 criteria linked to required actual pytest node IDs |
| `inventory.json`, `source.json` | Installed wheel/lock/package identities and checkout provenance |
| `catalog-proof/results.json` | Separate fresh-host REST/MCP catalog verification |
| `cases.json` | Each case's observed result, phase and duration |
| `junit.xml` | Machine-readable case results |
| Per-case diagnostics and cleanup transcripts | Failure details and evidence that owned resources closed |

The first phase executes kernel contract checks, installed activation and socket
journeys. Its finalizer requires every registered setup, call and teardown result
and every owned runtime cleanup. Missing, duplicate, foreign-run or wrong-build
results cannot pass. The packet is written before its digest-backed evidence
reference, avoiding a self-referential hash.

The second phase starts fresh hosts and loads that completed packet through a
typed test/operator adapter. Expectations come independently from installed
plugin Python bytes, package versions, the approved suite and installed dependencies.
The operator binds both complete fixture-helper import trees (`tests/fixtures`
and `tests/kernel`, including transitive modules and conformance registries) to
their recorded file names and bytes. Changed, added or removed helpers leave an
old packet pending. The catalog proof boots isolated copies with changed provider
and target implementations and checks the untouched packet; matching copies pass.
This intentionally invalidates evidence after any change within those helper trees.
The operator also compares current installed core Python content with the packet's
core digest. Each installed fixture case names its own retained build inventory;
separate wheel archives retain their exact hashes while matching core/plugin content.
Contract cases execute in the locked development environment and retain checkout
provenance. Metadata matching in the production catalog resolver does not parse files
or establish packet integrity; the test/operator adapter performs that check first.
The packet names the tested normal fixture profile. A host explicitly selecting
a disposable defect remains pending even if given the normal profile packet.
REST and MCP must agree: matched passing evidence is passed, matched failed
evidence is failed, and missing, stale, wrong-build or tampered evidence is pending.
Existing access policy filters evidence references. A fresh host does not recover
prior temporary receipts. Its catalog proof is separate from the packet it checks.
An expected injected failure passes only when its case observes the expected
failure and cleanup; an unexpected startup, discovery or cleanup failure fails
the run. Read the failing case's diagnostics before rerunning. Missing cleanup
evidence cannot support a successful cleanup claim.

Sensitivity cases explicitly select disposable disconnected-command and mutating-query
variants. A child process evaluates independent target observations and must fail
with the intended assertion. The failed child packet remains retained even when
the outer disproof test passes. Fresh normal variants must pass the same oracle.

The boundary cases opt into `synthetic.probe` in the independently installed fixture.
Its recursive input reaches depth 8, padding reaches 4096 decoded envelope bytes,
and a sized result reaches 4096 output bytes. Each cap is also exceeded by one.
Successful commands and oversized post-effect results are checked against the
independent target; rejected inputs leave its value, version and effect count unchanged.
Per-case `purpose.json` states the requirement references, and sanitized transcripts
retain actual requests and responses. The default fixture still exposes two operations.

This harness establishes installed-service behavior with synthetic providers. Production durability, Craft browser behavior and saved or reopened
XLSX artifacts require their own evidence.

## Resolve an interrupted call

Retry with the original key and equivalent content, or inspect the known operation
identity. A disconnected response does not establish cancellation. The installed
journeys pause the synthetic target after atomic admission, close the real HTTP or
MCP client, and use a new client to observe the retained identity. Releasing the
barrier must produce exactly one independently observed target change.

Use the receipt and retained-content diagnostic together:

| Observation | Interpretation |
| --- | --- |
| Pending after a post-effect journal outage | The target changed, but completion was not recorded; retry must not execute again. |
| Partial with missing or unavailable evidence | An effect was observed, but required completion evidence was not established. |
| Ambiguous with `effect_unknown` | The outcome remains unresolved; an equivalent retry must not replay it. |
| `evidence_missing`, `evidence_unavailable` or `result_unavailable` on inspection | Retained content cannot currently support readback; this is not a successful result. |

Private checkpoint/control transcripts record admission identity, revision, epoch
and active target lease. They inject failures and observe providers; business calls
still use public HTTP/MCP. Shutdown observations are saved during owned cleanup,
not fetched from an endpoint after it has closed. Each restarted temporary fixture
has a new epoch, initial target state and no retained prior operation. These tests
make no production recovery or durability claim.

When reviewing a failed journey, compare its public response with target value,
version and effect count before rerunning. A second effect for an equivalent retry,
a complete outcome without required evidence, or an orphaned owned process
invalidates the tested guarantee. Preserve that run's diagnostics.

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
