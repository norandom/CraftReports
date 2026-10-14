# CraftReport documentation

CraftReport is a Python reporting project for turning externally supplied data
and metrics into reusable reports in Craft applications. Its intended first
workflow connects a visible GridCraft report, a snapshot-consistent XLSX file,
and ordinary software automation through the same reporting contract.

Report owners should be able to review what changed and what was checked.
Integrators should be able to supply data from Python or Jupyter without moving
their calculation logic into the reporting service. AI is an optional caller.
The checkout is named `GridDash`; the Python package is `craftreport`.

## Current readiness

The repository has an operation kernel with typed operations, capability
registration, shared guards, REST/MCP interfaces and result readback. Its installed
verification uses synthetic capabilities and providers. It does not yet provide
a production reporting service or the complete report workflow described above.

A separate GridCraft deployment probe rendered the official downloaded web
application. That establishes browser hosting and rendering, not a verified
bridge from CraftReport to the visible workbook or a verified XLSX reporting path.
See [GridCraft setup and its evidence limits](gridcraft-setup.md).

Use the [kernel task list](../.kiro/specs/craftreport-operation-kernel/tasks.md)
for accepted work and open checks, and
[specification metadata](../.kiro/specs/craftreport-operation-kernel/spec.json)
for phase approvals. Kernel verification and reporting acceptance are separate
gates; a passing synthetic service check does not close the reporting foundation.

## Choose your starting point

| Your role and immediate task | Read next |
| --- | --- |
| Report owner: understand the intended workflow and decide what to evaluate | [Product strategy](product-strategy.md), then [roadmap](roadmap.md) |
| Integrator: reproduce the current kernel and inspect its evidence | [Quickstart](quickstart.md), then [kernel host assembly](kernel-host.md) |
| Capability author: add behavior through the shared operation contract | [Capability authoring](capability-authoring.md) and [developer guide](development.md) |
| App evaluator: open the downloaded spreadsheet application | [GridCraft setup](gridcraft-setup.md) |

The [quickstart](quickstart.md) offers two separate evaluation paths: kernel
verification and the GridCraft browser preview. Choose the one that answers
your question.

## Technical references

| Question | Reference |
| --- | --- |
| How do software callers discover and invoke operations? | [REST client](rest-client.md), [MCP client](mcp-client.md) |
| How do I inspect an operation after a response is lost? | [Result readback](result-readback.md) |
| Which app session does an operation actually control? | [Craft app protocols](craft-app-protocols.md) |
| How do I develop, verify and diagnose the kernel? | [Developer guide](development.md) |
| What must the complete reporting foundation deliver? | [Foundation requirements](../.kiro/specs/craftreport-reporting-facade/requirements.md) |

Public code and examples must work without private packs. Private templates,
branding, policies, credentials and data stay in their deployment environment.
Imported metrics retain their producer and validation status; accepting their
schema does not independently validate their financial method.

For scope changes, follow [project instructions](../AGENTS.md),
[capability ownership](../breadth.toml) and [engineering policy](../quality.toml).
The [roadmap](roadmap.md) separates the approved decomposition from future domains.
