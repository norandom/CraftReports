# Research and Design Decisions

## Summary

- Feature: craftreport-snapshot-runtime; discovery: complex extension of the accepted operation kernel, with full persistence/concurrency investigation on 2026-10-15.
- Existing `GuaranteeProviders` already names nine production obligations. `open_application` and `settings.configure` supply composition seams; a new dispatcher, broker, generic repository hierarchy and plugin container are unnecessary.
- The pure snapshot and input-requirements seam was agreed directly with report-model planning. Runtime never imports report compilation.
- Read core steering plus overview/testing/engineering/breadth/documentation, ledgers, umbrella requirements, roadmap, requirements/design/tasks skills and their rules/templates. COBESY informs the planned task-oriented guide: integrator publishes and proves retained identity after restart; a receipt alone disproves nothing about actual storage.

## Research Log

### Existing implementation and recovery gap

Sources: `application/ports.py`, `dispatch_ports.py`, `journal_values.py`, `outcomes.py`, `execution.py`, `registry.py`, `composition/app.py`, `composition/settings.py`, `scripts/check_imports.py`.

Findings: journal owns retry admission and receipt CAS; resource/evidence readers independently verify declared effects; results are retained/read back by dispatcher. `outcome_update` already supports ambiguous reconciliation with new verified evidence. The current execution owner is ephemeral and no startup reconciler exists. Add a narrow runtime-owned trusted recovery use case using existing outcome/CAS rules, not receipt-writing handlers. Application measures 1,449/1,500 LLOC and remains unchanged. SnapshotReader belongs to data.ports with exact existing Missing/VersionConflict/ServiceUnavailable imports; pure data values/requirements remain stdlib/contracts only. Import checks currently accept only five kernel layers and browser tooling; exact data/runtime/storage activation must precede source.

### Durable storage selection

The official [SQLAlchemy 2.1 SQLite dialect](https://docs.sqlalchemy.org/en/21/dialects/sqlite.html) reports current release 2.1.4 dated 2026-10-07. Python 3.12 supports explicit nonlegacy transaction control through `connect_args={"autocommit": False}`. Foreign-key enforcement needs per-connection initialization. [Engine transactions](https://docs.sqlalchemy.org/en/21/core/connections.html) provide commit/rollback contexts and typed query expressions.

The [SQLite locking reference](https://sqlite.org/lockingv3.html) describes file locks and rollback recovery. This bounded local deployment has one process owning all writers, serialized short commits and small complete payloads. A network filesystem, multiple hosts/workers and a database server are excluded. Startup holds a standard OS file lock for host lifetime, using `fcntl` on Linux and `msvcrt` on Windows. SQLAlchemy handles persistence; the lock only rejects unsupported second hosts.

Decision: pin SQLAlchemy 2.1.4, use stdlib sqlite3, a local disk/Compose named volume, rollback journal default, synchronous FULL and foreign keys ON. Bounded synchronous work runs via `asyncio.to_thread` with a process-wide storage mutex; connections are created/closed inside each worker call. No database connection crosses awaits. A resource guard may span an effect, but holds no SQL transaction. SQLite configuration statements are the only backend-specific text, isolated in storage/database.py with tests and rationale. Never interpolate caller data into SQL.

### Precision and canonical content

[Python Decimal](https://docs.python.org/3.12/library/decimal.html) supports exact decimal representation. Wire decimals are finite nonexponent strings at declared scale, constructed directly as Decimal, never through binary float. Schema/value validation precedes persistence; canonical UTF-8 JSON bytes preserve ordered arrays and schema tags while sorting object keys. SHA-256 is an identity digest, not a claim of source authenticity. Accepted/received times and operation IDs are excluded from producer content digest. Decimal signed zero normalizes to zero at its declared scale; no quantization may round a value. Exact roundtrip fixtures establish behavior.

Kernel wire canonicalization bounds JSON integers to safe magnitude. Therefore all int64 cells and ordered producer versions use exact canonical decimal strings on the wire while inward values stay int; the single shared scalar codec serves report-model too. Timestamp lexical checks reject submicrosecond precision rather than permit parser truncation. Preadmission request codecs compute the full snapshot.read result bound including fixed service-field overhead, preserving the requirement to reject exceeded limits before accepting work.

## Architecture Pattern Evaluation

| Option | Strength | Limitation | Decision |
| --- | --- | --- | --- |
| SQLAlchemy Core with SQLite | Mature transactions, constraints, typed expression API, no separate service | One bounded local writer and filesystem durability assumptions | Selected |
| PostgreSQL with SQLAlchemy | Multiple concurrent writers and deployment maturity | Additional service not needed for reference workload | Deferred; separate future design |
| Custom JSON/file store | Few initial dependencies | Reinvents atomic journal, retry indexing and crash recovery | Rejected |
| Generic multi-backend repositories/queue | Potential breadth | No second workload; obscures one useful slice | Rejected |

## Design Decisions

### One authoritative persistence representation

Tables retain canonical schema-tagged bytes for immutable content/results and use relational identity/revision columns for uniqueness and compare-and-set. They do not infer numeric types in SQLite or transform JSON through Polars into SQL. No Polars dependency is needed for these bounded complete publications; future processing can consume the validated value seam.

### Concrete providers, not another kernel

One storage lifetime constructs nine explicit provider implementations and purpose-specific snapshot/binding stores. Providers share transactions only where atomic behavior requires it; domain code sees plain values and narrow ports. Resource updates store operation-linked committed facts before returning. A postcommit crash is resolved by inspection, not replay. Existing `OperationJournal` remains the only receipt authority.

### Reviewed first slice

Implement owner/import activation, values, storage/journal and publish/read composition before scheduler breadth. Prove installed REST publish -> exact read -> host restart -> MCP read with duplicate/stale/conflict behavior. This is useful without a browser and does not close runtime lifecycle or real-app acceptance.

### Independent design remediation

The first review required explicit metric kind/shape/nullability completeness, dataset label/source provenance, preparation of a new selected snapshot before immutable run pins, default-budget-safe ownership, exact reader conflict typing and lexical datetime precision checks. Shared generic VersionPin lives in contracts.pins, never themes, avoiding a runtime-to-report-model dependency cycle. Real reporting composition implements RunPreparer by invoking public reports.prepare; runtime validates returned generic pins and rechecks generation, lifecycle revision and running intent before starting target effects. Standalone runtime verification uses a clearly synthetic prepared fixture through real durable providers; no report-model completion cycle is introduced. No compiler import enters publication/runtime.

COBESY guide structure: the reader is an existing Python producer; target behavior is publishing and proving restart read-back; the practical barrier is reconstructing host/auth/cleanup setup. Lead with retained exact identity, put commands beside expected observations, and treat differing recovered bytes or duplicate effects as the disproof condition. The public producer recipe is the anchor example; no organizational rollout is implied.

## Risks and Mitigations

- Provider recovery touches kernel guarantees: independent contract review and crash cutpoints around admission/effect/result/receipt; reuse existing kernel conformance fixtures.
- SQLite lock contention: serialize one process, short transactions, bounded configured timeout; surface unavailable without fake missing or volatile fallback.
- Different complete requirements per binding: persist immutable requirements with a digest/generation; latest accepted and latest complete are separate queries.
- A stale target may be reachable after restart: recovered lifecycle is suspended for inspection; app-owned session proof is required before activation.
- Storage owner size: use the reviewed default 1,500 LLOC for most-specific `snapshot-storage`; data/runtime each default 1,500; preserve 50 function/300 module/10 complexity. Review actual first-slice size before growth, with no assumed limit raise.
- Dependency resolution remains unperformed: task 1 resolves the exact lock and CPython 3.12 compatibility; this research does not claim installation or runtime proof.
