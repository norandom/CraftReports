# CraftReport

CraftReport is a Python reporting project for turning external datasets and
metrics into reports in Craft applications. The intended product combines live
views, reusable templates, exported files and evidence of what was checked.
The repository directory is named `GridDash`; the Python package is `craftreport`.

Development currently centers on the operation kernel: typed operations,
capability packages, shared guards and evidence contracts. It is not yet a
complete reporting service. REST/MCP service integration, lifecycle completion
and full installed-system conformance still have open tasks. See the
[kernel task list](.kiro/specs/craftreport-operation-kernel/tasks.md) for current
progress and [approval metadata](.kiro/specs/craftreport-operation-kernel/spec.json)
for the authorized phase.

## Start with the task you have

| You want to | Start here |
| --- | --- |
| Open GridCraft in a browser without building Rust | [GridCraft setup](docs/gridcraft-setup.md) |
| Work on the Python kernel | [Developer guide](docs/development.md) |
| Write a capability package | [Capability author contract](docs/capability-authoring.md) |
| Understand hosting, MCP, browser sessions and WOPI | [Craft app protocols](docs/craft-app-protocols.md) |
| Check planned reporting scope | [Reporting requirements](.kiro/specs/craftreport-reporting-facade/requirements.md) |

The GridCraft setup serves the official application archive through a static
container. Its WebAssembly file contains the spreadsheet application. Hosting
that application does not connect its browser workbook to CraftReport's Python
kernel; the [protocol guide](docs/craft-app-protocols.md) explains that boundary.

## Python quick start

Use CPython 3.12.10 and uv 0.13.0 from the repository root:

```sh
uv sync --frozen --group dev
uv run --frozen python scripts/check.py --fast
uv run --frozen pre-commit install
```

On the Windows development workstation, use `uv.exe` in place of `uv` to bypass
the PowerShell wrapper. Dependencies and tool versions are pinned in
[pyproject.toml](pyproject.toml) and [uv.lock](uv.lock).

The fast command runs Ruff, strict Pyright, size and branching checks, ownership
and import checks, and focused tests. Passing it establishes those checks only.
The separate integration command currently exits nonzero because its harness is
pending; a skipped CI integration job is not a passing result.

## Scope and contribution rules

External producers own portfolio calculations and imported metrics. AI may call
the planned public interfaces, but it is not required to run reporting
operations. Database selection, further app integrations and domain-specific
checks remain subject to their own approved scope.

Before expanding a feature, read [AGENTS.md](AGENTS.md), the
[steering overview](.kiro/steering/overview.md), and the owning specification.
[breadth.toml](breadth.toml) assigns capability ownership and lifecycle;
[quality.toml](quality.toml) defines engineering requirements. A planned path or
an active ledger entry does not mean the feature is implemented or approved for
every phase. Keep private data and packs outside public source and artifacts.
