# Technology Stack

Updated: 2026-10-15. This file records confirmed direction and distinguishes design proposals from installed/implemented infrastructure.

## Architecture

Use one coherent Python reporting core with explicit interfaces for data, report preparation, execution, persistence and app integration. Keep calculation/report transformations functional and runtime/repository/app boundaries cohesive. Contracts do not contain framework, database, dataframe or live-app handles.

Transport, processing and persistence are separate responsibilities. A JSON push can become a validated snapshot and report without a Polars-to-SQL round trip. The first foundation consumes supplied metric results; no portfolio method engine is implied.

## Core Technologies

- **Language:** typed Python is user-confirmed. The approved kernel runtime range is >=3.12,<3.13; record the installed patch version and verify the locked environment during implementation.
- **Data:** Polars is the requested dataframe direction. Validate schema, precision and metadata before construction; do not rely on inference as financial validation.
- **Deployment:** Docker Compose is user-confirmed for the core and supported separate web-app hosting. Native visible Windows apps need an interactive connector outside containers.
- **Craft app acquisition:** use the latest official downloadable GridCraft release, minimum 0.6.1; verify archive checksum and record exact release/asset hash. Do not compile GridCraft locally or substitute unreleased source features for the released bundle.
- **Persistence:** PostgreSQL was a conditional preference and remains under review. No default database/ORM is approved; DuckDB and dbt-duckdb are excluded.
- **Interfaces:** ordinary app-to-app MCP and external data push are required. AI is optional and cannot be required for these operations.

## Key Library Decisions

The approved kernel uses framework-independent values, Pydantic boundary codecs, thin FastAPI and official MCP interfaces, standard installed-package discovery and Pyright strict. Exact selected versions are in its Design and uv.lock. Task 1.1 resolved and installed them, built the minimal wheel and verified its import; installed runtime compatibility passed final synthetic kernel validation on CPython 3.12.10. Database/ORM selection remains downstream. Avoid handwritten SQL in reporting/domain code; isolate unavoidable backend-specific operations behind the persistence/source boundary.

Use upstream protocols and SDKs rather than create a custom general-purpose reporting language, database engine, queue broker or identity provider. dbt, full CQRS infrastructure, independent workers and analytical databases need a concrete workload/use case.

## Development Standards

Runtime input validation and static typing serve different purposes. A single selected strict checker accompanies mandatory Ruff lint/format and pre-commit/CI parity. Pin versions/configuration in the approved foundation and record actual check execution.

Engineering size/branching budgets and exceptions are governed by `engineering.md` and root `quality.toml`. The owner approved the kernel values with its Design; enforcement and broader capability approval remain separate.

Real adapter/session behavior, actual saved bytes and reopen checks are mandatory for acceptance-critical reporting. Numerical-method validation is distinct from transport/schema checks and output equality. See `testing.md`.

## Development Environment

The repository has a Python kernel package and resolved dependency lock. Task 1.4 verified the complete local fast pipeline and installed project hook, including an isolated candidate checkout. CI uses the same command; [hosted run 38617747132](https://github.com/norandom/CraftReports/actions/runs/38617747132) passed fast checks and installed-wheel synthetic conformance on 2026-10-14 at commit 44d3101 (verified 2026-10-15). Browser CI remains pending. Tasks 8.1–8.4 implemented and individually verified isolated installed-wheel REST/MCP clients, synthetic target readback, failure/concurrency journeys and scoped conformance packets. Task 9 passed independent final feature validation within the synthetic kernel scope; see the implementation-validation assessment and task checklist. These temporary test providers establish no production durability or reporting acceptance. The Windows `python` command resolves to the Store alias on this workstation; use `uv.exe` and the project environment.

Observed on 2026-10-13: Windows `docker` is a PowerShell function invoking WSL; Debian WSL's daemon returned Docker 29.7.2 on Debian GNU/Linux 13 and Compose 5.4.0. Use explicit Debian WSL commands/paths and published browser origins, or operator-provided remote instances. This probe establishes Docker availability, not a tested Craft deployment.

Observed on 2026-10-14: the official GridCraft v0.6.1 web archive includes its compiled Rust WASM engine and renders through a static nginx Compose service without a local Rust build. The project-owned `craftreport-gridcraft-probe` in Debian WSL publishes `0.0.0.0:8871`; the owner confirmed Windows `http://localhost:8871` works. An isolated Playwright context loaded the sample dashboard, with screenshots, flushed video and console/network diagnostics retained under ignored `artifacts/gridcraft-deployment-probe/browser`. WASM returned HTTP 200 with `application/wasm`; software WebGL2 fallback warnings were retained. This is hosting/rendering evidence only. The released browser build has no native TCP control channel; live browser MCP mutation, export/read-back and LAN access are not established by this smoke test. The reusable setup recipe belongs in developer documentation; this probe does not close the reporting acceptance work.

Canonical checks are `uv.exe run --frozen python scripts/check.py --fast` and `uv.exe run --frozen python scripts/check.py --integration` on this workstation. Integration runs the complete kernel suite, then starts fresh installed hosts to verify the resulting conformance packet through REST/MCP catalogs. Record each invocation's exit code and evidence directory; an earlier task pass does not close a later feature gate.

## Key Technical Decisions

- Native, browser/WASM and headless sessions have distinct identities and control contracts.
- Snapshot/run/version pins define consistency; app command batching does not create a cross-app transaction.
- Private packs are configured runtime input, not public source/image contents or executable-code permission.
- Required persistence retains identities/evidence and truthfully reports unavailable or ambiguous state after interruption.
- Dependency and capability ownership follows `structure.md` and the breadth ledger; parked extensions do not land under a general parent's ownership.
