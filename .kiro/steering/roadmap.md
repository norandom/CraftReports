# Roadmap

Updated: 2026-10-14. **Five-part decomposition approved** by the owner's contextual "ok"; the operation kernel is the first bounded spec. There are two real specs: the umbrella has approved requirements; the kernel has approved requirements, Design and Tasks, with implementation authorized on 2026-10-13. Its 36 Python source modules and all 26 executable tasks are accepted, including independent final synthetic-scope validation. The four downstream bounded specs are not initialized. Kernel evidence covers synthetic effects and temporary state, not the composed reporting application.

## Overview

CraftReport delivers a public modular reporting facade, beginning with supplied portfolio data/metrics, visible live GridCraft, XLSX export and app-to-app MCP. AI is optional. The wide horizon is handled through a stable shared operation/contract core and separately owned capability packages.

## Approach Decision

- **Approved direction:** stable kernel plus self-contained capabilities, developed one bounded spec at a time. Thin REST/MCP/UI entry points share typed command/query dispatch and common guards/evidence. Concrete contracts and implementation choices remain subject to each bounded Design review.
- **Why:** ownership, dependency contracts and evidence remain inspectable as apps/domains grow. Shared reporting meaning does not fork per app.
- **Alternatives:** one expanding umbrella implementation obscures ownership; making every utility a plugin adds indirection; microservices/brokers/event sourcing are not required by the foundation.

## Scope

- **In:** current approved foundation journeys, command/query middleware, versioned capability contracts, latest-release browser deployment and real end-to-end evidence.
- **Out:** implementing all future domains/apps, local portfolio/GIPS methods, designer clone, client SDK/Jupyter, arbitrary runtime plugin installation and enterprise distribution.

## Constraints

Use typed Python/Polars where processing is needed; avoid handwritten SQL in core logic; private packs stay separate. Database/ORM remain downstream Design decisions. The approved kernel dependencies and tools are locked and installed; task-local compatibility, installed-client checks and independent final synthetic-scope validation have passed. DuckDB remains excluded.

GridCraft is the latest official downloadable release, at least 0.6.1, with checksum/build recorded per deployment. No local GridCraft compilation. Docker runs in Debian WSL here; configured remote instances are an alternative. Playwright verifies the actual browser session, with screenshots, review videos, diagnostics and persisted artifact/reopen evidence.

## Boundary Strategy

The umbrella acceptance baseline is retained. Child requirements/designs reference its numeric criteria without duplicating ownership. Shared contracts are settled upstream; app/domain packages consume them. Each capability owns its settings, operations, implementation/tests and evidence. Activate only the next bounded scope; parked horizon items do not create empty source trees.

### Approved Decomposition and Activation Order

| Order | Candidate | Responsibility | Dependencies |
| --- | --- | --- | --- |
| 1 | [craftreport-operation-kernel](../specs/craftreport-operation-kernel/requirements.md) | Typed contracts, plugin/operation registration, shared command/query middleware, thin software interfaces and evidence/port contracts. Requirements, Design and Tasks approved; implementation and final synthetic-scope validation accepted. | Approved umbrella acceptance baseline. |
| 2 | `craftreport-browser-verification` | Latest web-release download/serve profile, owned Playwright environment, screenshots/videos/diagnostics and real save/reopen feasibility proof. | Kernel contract/evidence identities; may research browser feasibility independently. |
| 3 | `craftreport-snapshot-runtime` | Typed producer publication, ordered immutable snapshots, retained operations/binding state, scheduler and restart reconciliation. | Operation kernel; reviewed persistence choice. |
| 4 | `craftreport-report-model-packs` | Declarative compilation, semantic themes, public/private pack compatibility, scoped findings and draft/release rules. | Kernel data/model/evidence contracts. |
| 5 | `craftreport-gridcraft-web-reports` | App package: owned-region rendering, controls, live refresh, actual XLSX export and integrated browser journey. | Browser proof, snapshot runtime and report/packs capabilities. |

Kernel, snapshot, pack and app responsibilities have separate closure evidence. Browser feasibility is checked early; its harness later verifies the fully composed system. A successful UI-only feasibility test cannot claim a working facade/report flow.

Only the operation kernel has child spec.json metadata. The remaining four scopes are approved roadmap entries awaiting individual initiation, not existing specs or approved task sets. Do not run batch fast-track automatically. Preserve human Requirements -> Design -> Tasks approvals and register each actual spec as it is created.

## Existing Spec Updates

- `craftreport-reporting-facade`: retain the approved 110-criterion foundation baseline, architecture blueprint and researched decisions; reconcile child coverage and current approval metadata during the split. It is not an all-domain implementation spec.

## Direct Implementation Candidates

None authorized. Core steering and research documentation are current; production foundations require approved bounded Design/tasks.

## Specs (dependency order)

1. [craftreport-operation-kernel](../specs/craftreport-operation-kernel/requirements.md) — requirements, Design and Tasks approved; all 26 executable tasks accepted with final synthetic-scope validation. Upstream: approved umbrella baseline. Downstream: the remaining four scopes above, none initialized yet.

This is a sequential review plan, not authorization for batch generation or execution. Kernel acceptance supports shared contracts only; the umbrella stays open for the complete reporting journeys.

## Horizon and Activation Rules

Local portfolio-method/GIPS support, financial/forensic accounting, invoices, tax/books, DIN-style letters/assessments and other app packages remain parked. Each future activation establishes its methodology/standards scope, dependency compatibility, commands, output checks and code budget before work lands.

Root `breadth.toml` owns lifecycle/path decisions; Kiro metadata owns phase approvals; `quality.toml` owns engineering/budget status. Keep actual and planned counts separate. A new package under `packages/` also needs a capability owner, just as a new core module does.

References: [foundation requirements](../specs/craftreport-reporting-facade/requirements.md) and [browser deployment and verification](../../docs/gridcraft-setup.md). The formal Design gate's decomposition requirement is addressed by this approved split; finalized implementation designs follow within the bounded specs.
