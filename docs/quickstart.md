# Quickstart: evaluate the current project

Start with the [current readiness summary](index.md#current-readiness).
This guide gives developers a reproducible kernel check and gives app evaluators
a route to the downloaded GridCraft preview. These are separate evaluations;
neither starts a complete CraftReport reporting service.

## Verify the Python kernel

You need Git, CPython 3.12.10, uv 0.13.0 and a checkout of this repository.
Run from the checkout root. The first sync needs access to the locked packages.
The fast checks need no database, Craft app, AI service or private pack.

In PowerShell on the Windows development workstation:

```powershell
uv.exe --version
uv.exe sync --frozen --group dev
uv.exe run --frozen python --version
uv.exe run --frozen python scripts/check.py --fast
```

On Linux or another environment with a normal uv installation, use `uv` instead
of `uv.exe`. Create a separate environment for a Linux/WSL checkout; do not reuse
a Windows `.venv`.

Expect uv 0.13.0, Python 3.12.10 and a zero exit from the fast check. That command
runs lint, format, strict typing, engineering budgets, ownership/import checks and
focused tests. If it fails, use the named failing stage and its diagnostics;
a partial run does not establish a passing environment. The
[developer guide](development.md#create-the-locked-environment) covers environment
selection and required contributor hook setup.

## Exercise installed REST and MCP clients

For a fuller evaluation, run the installed verification harness:

```powershell
uv.exe run --frozen python scripts/check.py --integration
```

The harness builds and installs the kernel and a synthetic capability in isolated
environments. It runs ordinary REST and MCP clients against owned loopback
services, observes a synthetic target independently, checks retained results and
retries, and closes its resources. It also tests expected failures. It does not
leave a production server running.

The command prints an `artifacts/<run-id>/` directory. Require a zero exit for
the complete command, then inspect:

| File | Verify |
| --- | --- |
| `kernel-manifest.json` | Tested identities, cases, scope and cleanup belong to this run |
| `verification.json` | Derived status references the exact persisted evidence packet |
| `cases.json` and `junit.xml` | Expected cases ran; failures have retained diagnostics |
| `catalog-proof/results.json` | Fresh-host verification checked the completed packet |

Use [run and result inspection](development.md#run-the-installed-harness) for the
full evidence contract. A failed or pending result needs diagnosis, not a success
claim based on a responding port. Keep failed-run diagnostics before retrying.

Your next step is to trace one operation through [REST](rest-client.md) or
[MCP](mcp-client.md), then [result readback](result-readback.md). To assemble your
own host, read [kernel host assembly](kernel-host.md): a deployment must supply
providers and authentication; there is no default production provider bundle.

## Preview GridCraft in a browser

Use [GridCraft setup](gridcraft-setup.md) for the complete download, checksum,
Compose, browser verification and shutdown commands. It requires Linux or Debian
WSL, a running Docker daemon with Compose, curl, unzip and sha256sum. It serves
the official compiled web archive; no local Rust build is needed.

The recipe uses its own Compose project on port 8872, separate from the existing
development probe on 8871. Expect a rendered spreadsheet interface after opening
the recipe's URL. If the page stays blank, follow the setup guide's asset,
graphics and networking diagnostics. HTTP 200 alone is insufficient.

This preview establishes app hosting. Before attempting automation, read
[Craft app protocols](craft-app-protocols.md): a browser workbook and a native or
headless MCP workbook have different identities unless a verified bridge joins
them. The [roadmap](roadmap.md) describes the remaining work to connect producer
data, visible updates and inspected XLSX artifacts.
