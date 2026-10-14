# Quickstart: how to verify the kernel

Run the locked engineering checks and installed REST/MCP journeys, then inspect
their evidence. The journeys use synthetic capabilities, temporary providers and
an independently observed synthetic target.

## Before you start

You need Git, CPython 3.12.10, uv 0.13.0 and a checkout. Run from its root in
PowerShell. The first sync needs locked-package access. No database, Craft app,
private pack or AI service is required. On other systems use `uv` for `uv.exe`;
a Linux/WSL checkout needs its own environment.

## Run the checks

```powershell
uv.exe --version
uv.exe sync --frozen --group dev
uv.exe run --frozen python --version
uv.exe run --frozen python scripts/check.py --fast
uv.exe run --frozen python scripts/check.py --integration
```

Check each command's exit code before continuing. Expect uv 0.13.0, Python
3.12.10 and zero exits for both check commands. The integration command builds
and installs isolated wheels, starts owned loopback hosts, exercises ordinary
REST/MCP clients and closes its resources. It leaves no interactive server running.

## Verify the result

Open the `artifacts/<run-id>/` directory printed by integration. Check:

| File | Expected observation |
| --- | --- |
| `kernel-manifest.json` | Installed identities, actual cases, synthetic scope and owned cleanup |
| `verification.json` | Status tied to the exact persisted evidence packet |
| `cases.json` and `junit.xml` | Required cases executed with expected outcomes |
| `catalog-proof/results.json` | Fresh hosts checked the completed packet through both catalogs |

The journeys compare retained responses with independent target value, version
and effect count. Expected injected failures pass only when their expected
diagnostics and cleanup are observed. See the
[full evidence contract](../development.md#run-the-installed-harness).

## If it does not work

| Observation | Next action |
| --- | --- |
| Wrong Python or uv version | Follow [locked environment selection](../development.md#create-the-locked-environment) |
| Fast checks fail | Read the named stage's diagnostics and resolve it before integration |
| Integration fails or evidence stays pending | Retain the run directory; inspect case and cleanup diagnostics before retrying |

## Next action

Read [host assembly](../kernel-host.md) before supplying your own providers and
authentication. With an assembled host, [invoke through REST](Quickstart_How_to_invoke_an_operation_with_REST.md)
or [MCP](Quickstart_How_to_invoke_an_operation_with_MCP.md). These synthetic checks
establish no production durability, visible report refresh or saved XLSX artifact.
