# CraftReport Work Lines

Updated: 2026-10-15. This overview distinguishes current implementation from scope direction; phase approvals remain in the specifications.

## Four Work Lines

| Line | Responsibility |
| --- | --- |
| `shared-reporting` | Declarative report/API contracts, external data ingestion, Polars-backed processing, optional domain methods and reproducible report content. |
| `craft-app-integration` | Versioned app adapters, visible native/web sessions, report-owned bindings, supported output and live-update operations. |
| `quality-verification` | Independent calculation checks, applicable policy evidence, end-to-end interaction/persistence verification, typed code and mechanical engineering gates. |
| `template-packs` | Configurable themes/templates, public examples, external private packs, compatibility and publication boundaries. |

The initial portfolio reporting use case cuts across these lines. Required delivery paths are visible live dashboards, snapshot-consistent XLSX export and app-to-app MCP. AI is an optional consumer of the same contracts; required paths work without an LLM.

Financial/forensic accounting, invoices, book reports, tax sheets, and WordCraft DIN-style letters/assessments are future orientation. Domain meanings, standards and lifecycle behavior require bounded specs before activation. Other Craft apps remain capability candidates until activated with a bounded use case.

## Current Reality

- Three specifications exist: the umbrella has approved foundation requirements; the operation kernel has accepted implementation and final synthetic-scope validation for all 26 tasks; browser verification has owner-approved requirements and Design, with all implementation tasks approved (19 after the bounded budget amendment) and execution in progress. The owner approved the five-part split, and the remaining three bounded specs are not initialized. Browser implementation is authorized but not yet accepted.
- Existing GridCraft prototype files demonstrate a narrow historical live-update workflow. They are not the Python core or a financial validation engine.
- The kernel now has 36 Python source modules across contracts, application, adapters, interfaces and composition. Tasks 1–9 have accepted engineering, activation, guarded execution, public result readback, installed REST/MCP conformance and independent final synthetic-scope validation. Local fast-command and installed-hook evidence exists; [hosted run 38617747132](https://github.com/norandom/CraftReports/actions/runs/38617747132) passed fast checks and installed-wheel synthetic conformance on 2026-10-14 at commit 44d3101 (verified 2026-10-15). Browser CI remains pending. The installed harness uses synthetic effects and temporary state, without production persistence. On 2026-10-14 a separate Compose probe served the official GridCraft web release; Playwright captured the rendered sample dashboard and video. Reporting operations and the reusable browser/artifact acceptance harness remain pending.
- `breadth.toml` is the draft lifecycle ledger. Its actual and planned paths are deliberately separate.
- `quality.toml` records approved kernel tool/limit decisions with explicit scope. Locked tools and the standalone size/branching gate are verified; local hook enforcement is verified and CI uses the same configured command; hosted fast and synthetic integration execution is verified by the run above. The browser tooling owner is approved with its Design; a reviewed owner-approved amendment sets its aggregate budget to 2,800 LLOC while preserving local limits and other capability defaults. Task 2.3 implemented and independently verified that bounded gate before browser expansion; its implementation is authorized by Tasks approval. Other future capability budgets remain subject to review.

## Stable Product Boundaries

CraftReport is a public project; private template packs and deployment data stay outside public distribution. Jupyter and the user's Python allocation/metrics framework are external callers; this project implements server contracts, not notebooks, a client SDK or the allocation framework. Imported metrics retain calculation ownership, provenance and validation status.

Python/Polars and Docker Compose are the requested direction. The earlier conditional PostgreSQL preference is under reconsideration alongside persistence workload needs; no replacement is selected. Avoid handwritten SQL where possible through typed ORM/query expressions confined to adapters. Functional calculations and OOP boundaries are the architectural recommendation, not an approved design. JSON pushes need no mandatory Polars-to-SQL round trip. DuckDB, including dbt-duckdb, is excluded. dbt and full CQRS infrastructure require an actual need.

The core supports structured report content with optional domains. Portfolio methods/GIPS are not mandatory dependencies of letters or generic assessments.

The first spec is the reporting foundation using supplied datasets/metrics, not local portfolio calculations or a built-in GIPS rule pack. Pause resumes with the highest complete producer snapshot version in the bound feed; older arrivals are rejected and duplicate retries do not reapply old content. Failed/unevaluated required quality checks permit marked drafts and block release as validated output; draft status does not bypass input/access or persistence validation.

## Development Decisions

Active ledger status permits only the work authorized by the current Kiro phase. It never substitutes for requirements/design/tasks approval. Split the umbrella discovery into bounded specs when executable scope warrants it; do not create fictitious specs just to fill a ledger.

Every implemented capability needs a responsible code boundary and evidence. Documentation, native command counts and a screenshot alone do not establish implemented feature coverage.

Use a stable operation/contract core and self-contained capability packages. Shared command/query middleware guards all REST/MCP/UI entry points. Follow the approved five-part roadmap one bounded spec at a time; the kernel and browser verification are initialized, and every phase retains human review. The primary browser workflow serves the latest downloaded GridCraft release through Debian WSL Docker or operator-provided remote instances, with Playwright screenshots/videos and artifact/reopen checks. No local GridCraft compilation.

Read `testing.md`, `engineering.md`, and `breadth.md` for the recurring rules. Detailed capability and module proposals remain in the feature spec rather than being duplicated here.
