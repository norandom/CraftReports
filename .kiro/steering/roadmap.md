# Roadmap

Updated: 2026-10-15. **Five-part decomposition approved** by the owner's contextual "ok". Six actual specifications now exist: the umbrella retains approved foundation requirements; the kernel has all 26 executable tasks accepted within its synthetic scope; browser verification remains in progress with 15 of 20 tasks accepted at the overnight-run baseline; and the three downstream bounded specs are initialized with discovery briefs and registered ownership. Phase status remains authoritative in each `spec.json`; initialization is not phase approval or a working capability.

## Overview

CraftReport delivers a public modular reporting facade, beginning with supplied portfolio data/metrics, visible live GridCraft, XLSX export and app-to-app MCP. AI is optional. The wide horizon is handled through a stable shared operation/contract core and separately owned capability packages.

## Approach Decision

- **Approved direction:** stable kernel plus self-contained capabilities. Thin REST/MCP/UI entry points share typed command/query dispatch and common guards/evidence. Concrete contracts and implementation choices remain subject to each bounded Design review. The bounded overnight continuation below allows independent upstream work in parallel.
- **Why:** ownership, dependency contracts and evidence remain inspectable as apps/domains grow. Shared reporting meaning does not fork per app.
- **Alternatives:** one expanding umbrella implementation obscures ownership; making every utility a plugin adds indirection; microservices/brokers/event sourcing are not required by the foundation.

## Scope

- **In:** current approved foundation journeys, command/query middleware, versioned capability contracts, latest-release browser deployment and real end-to-end evidence.
- **Out:** implementing all future domains/apps, local portfolio/GIPS methods, designer clone, client SDK/Jupyter, arbitrary runtime plugin installation and enterprise distribution.

## Constraints

Use typed Python/Polars where processing is needed; avoid handwritten SQL in core logic; private packs stay separate. Database/ORM remain downstream Design decisions. The approved kernel dependencies and tools are locked and installed; task-local compatibility, installed-client checks and independent final synthetic-scope validation have passed. DuckDB remains excluded.

GridCraft is the latest official downloadable release, at least 0.6.1, with checksum/build recorded per deployment. No local GridCraft compilation. Docker runs in Debian WSL here; configured remote instances are an alternative. Check the actual selected release's supported embedding/control/file capabilities; prefer mature released capabilities to custom automation where their semantics suffice. Historical UI-only assumptions do not constrain newer releases. Playwright verifies the actual browser session, with screenshots, review videos, diagnostics and persisted artifact/reopen evidence. Unattended automation remains headless; separate missing headed evidence stays open.

## Boundary Strategy

The umbrella acceptance baseline is retained. Child requirements/designs reference its numeric criteria without duplicating ownership. Shared contracts are settled upstream; app/domain packages consume them. Each capability owns its settings, operations, implementation/tests and evidence. Activate only the next bounded scope; parked horizon items do not create empty source trees.

### Approved Decomposition and Activation Order

| Order | Candidate | Responsibility | Dependencies |
| --- | --- | --- | --- |
| 1 | [craftreport-operation-kernel](../specs/craftreport-operation-kernel/requirements.md) | Typed contracts, plugin/operation registration, shared command/query middleware, thin software interfaces and evidence/port contracts. Requirements, Design and Tasks approved; original implementation and final synthetic-scope validation accepted; owner-approved facade correction task 10.1 is accepted. | Approved umbrella acceptance baseline. |
| 2 | [craftreport-browser-verification](../specs/craftreport-browser-verification/requirements.md) | Latest web-release download/serve profile, owned browser verification, screenshots/videos/diagnostics and real edit/save/reopen feasibility proof. Requirements and Design approved; 20 approved tasks after bounded amendments; implementation in progress. | Kernel contract/evidence identities; browser feasibility is verified independently of a complete report workflow. |
| 3a | [craftreport-snapshot-runtime](../specs/craftreport-snapshot-runtime/tasks.md) | Typed producer publication, ordered immutable snapshots, retained operations/binding state, scheduler and restart reconciliation. Requirements, Design and 20-task plan independently reviewed and accepted; implementation started. | Operation kernel; reviewed SQLite/SQLAlchemy persistence choice. Independent of report-model planning and browser closure. |
| 3b | [craftreport-report-model-packs](../specs/craftreport-report-model-packs/tasks.md) | Declarative compilation, semantic themes, public/private pack compatibility, scoped findings and draft/release rules. Requirements, Design and 14-task plan after the owner-approved failure-result correction independently reviewed and accepted; implementation awaits its declared prerequisites. | Operation kernel and shared snapshot contracts; public preparation activation also requires the retained-size invariant and real durable providers. |
| 4 | [craftreport-gridcraft-web-reports](../specs/craftreport-gridcraft-web-reports/tasks.md) | App package: owned-region rendering, controls, live refresh, actual XLSX export and integrated browser journey. Requirements, Design and 16-task plan independently reviewed and accepted; early real-browser feasibility gates production expansion. | Both upstream reviewed designs/contracts; actual browser capability evidence for each claimed app path. Full browser closure remains separate. |

Kernel, snapshot, pack and app responsibilities have separate closure evidence. Browser feasibility is checked early; its harness later verifies the fully composed system. A successful UI-only feasibility test cannot claim a working facade/report flow.

### Bounded overnight continuation

The owner's 2026-10-15 instruction authorizes eight hours of unattended progress
across the three existing foundation scopes. Its exact deadline, operating
constraints and checkpoint record are in
[overnight-run-2026-10-15.md](../specs/craftreport-reporting-facade/overnight-run-2026-10-15.md).
This is intentional fast-track authority for those scopes only; record its
provenance in new phase metadata. It supersedes sequential human pauses within
that bounded run while preserving independent phase/task/implementation reviews,
ownership registration, installed hooks and fresh acceptance evidence. It does
not authorize future domains/apps, financial methods, GIPS assurance or higher
numeric budgets.

Initialization/registration is complete for the three downstream scopes. Wave 1
reviews snapshot-runtime and report-model-packs requirements/designs independently.
Agree one small immutable snapshot,
binding-requirements and prepared-report seam; do not create a circular dependency
or parallel source of canonical state. Wave 2 freezes app Design/tasks against
both reviewed contracts and current released-browser capabilities. Independent
data/model tasks may proceed while browser feasibility remains open. Actual app
acceptance still needs matching external-effect and artifact evidence; a missing
headed profile remains `MANUAL_VERIFY_REQUIRED` and cannot be silently waived.

The first deliverable is a thin external producer -> reusable table/line-chart
report -> identified live GridCraft -> snapshot-pinned XLSX flow. Defer optional
ingestion formats, multiple storage backends, generic report languages and
cross-app infrastructure. Before new source lands, reviewed tasks must apply the
existing default budgets to exact owners and narrowly extend import-boundary
rules/tests; root coordinates shared gate edits. Discovery alone performs none
of these phase or implementation actions.

## Existing Spec Updates

- `craftreport-reporting-facade`: retain the approved 110-criterion foundation baseline, architecture blueprint and researched decisions; reconcile child coverage and current approval metadata during the split. It is not an all-domain implementation spec.

## Direct Implementation Candidates

None outside the bounded specs. Production foundations require reviewed bounded
Design/tasks under the explicit overnight authority.

## Specs (dependency order)

- [x] [craftreport-operation-kernel](../specs/craftreport-operation-kernel/requirements.md) -- all 26 executable tasks accepted with final synthetic-scope validation. Dependencies: approved umbrella baseline.
- [ ] [craftreport-browser-verification](../specs/craftreport-browser-verification/brief.md) -- approved phase plans, implementation/profile acceptance remains open; proves released-browser interaction/file boundaries. Dependencies: craftreport-operation-kernel.
- [ ] [craftreport-snapshot-runtime](../specs/craftreport-snapshot-runtime/brief.md) -- typed publication, immutable ordered snapshots and retained lifecycle/restart behavior. Dependencies: craftreport-operation-kernel.
- [ ] [craftreport-report-model-packs](../specs/craftreport-report-model-packs/brief.md) -- reusable prepared reports, semantic packs and scoped draft/release findings. Design proceeds independently of snapshot implementation/browser closure; implementation depends on craftreport-operation-kernel and craftreport-snapshot-runtime shared contracts, then its durable snapshot/evidence providers and production host for public preparation/adopter acceptance (exact task dependencies are in the report-model plan).
- [ ] [craftreport-gridcraft-web-reports](../specs/craftreport-gridcraft-web-reports/brief.md) -- integrated live report and actual snapshot-consistent XLSX/reopen journey. Dependencies: craftreport-operation-kernel, craftreport-snapshot-runtime, craftreport-report-model-packs, craftreport-browser-verification (matching path evidence; full profile closure remains open).

Kernel acceptance supports shared contracts only; the umbrella stays open for
the complete reporting journeys. Each new brief names the required quickstart,
runnable adopter example and owning boundary; those delivery tasks and their
execution validation travel through the bounded phase plans.

## Horizon and Activation Rules

Local portfolio-method/GIPS support, financial/forensic accounting, invoices, tax/books, DIN-style letters/assessments and other app packages remain parked. Each future activation establishes its methodology/standards scope, dependency compatibility, commands, output checks and code budget before work lands.

Root `breadth.toml` owns lifecycle/path decisions; Kiro metadata owns phase approvals; `quality.toml` owns engineering/budget status. Keep actual and planned counts separate. A new package under `packages/` also needs a capability owner, just as a new core module does.

References: [foundation requirements](../specs/craftreport-reporting-facade/requirements.md) and [browser deployment and verification](../../docs/gridcraft-setup.md). The formal Design gate's decomposition requirement is addressed by this approved split; finalized implementation designs follow within the bounded specs.
