# Task 3.1 durable journal reuse and schema amendment

Accepted plan: 2026-10-15 under the owner's bounded overnight fast-track. Scope: snapshot-runtime task 3.1, its existing requirement references and the storage foundation from task 1.2. Independent reviewer `/root/review_journal_reuse_plan` returned PASS for proposal SHA-256 `10C7AF16CB7799599DA8106D1AF92F43FAD7642B7BF7E4395EDFE12AA0092F1E`. Task 3.1 implementation remains dependent on acceptance of task 2.3 and root's explicit start. No engineering limit increases, new journal authority or general migration framework are authorized.

## Existing library and contract reuse

Use explicit `TypeAdapter(Receipt)` and `TypeAdapter(CommandIntent)` instances in `src/craftreport/adapters/storage/serialization.py`. These derive the retained representation from the existing immutable contract dataclasses; do not add duplicate receipt/intent models or a reflective dataclass registry. Use `validate_json(..., strict=True, extra="forbid")` on retained bytes, followed by existing immutable-value checks. Encode their JSON views with the existing canonical JSON facility, retaining its numeric and JSON-value restrictions. Enum, tuple and nested contract reconstruction belongs to Pydantic, not handwritten recursive conversion. Receipt and CommandIntent contain references and a fingerprint, not a nested producer payload; arbitrary JSON retention is outside this task.

The ignored preflight probe at `artifacts/snapshot-runtime/task-3.1-preflight/typeadapter_probe.py` ran with exit 0 using `uv.exe run --frozen python`. Its result file verifies exact typed equality and recursive immutability for nontrivial receipts/intents, optional fields, nested enums/evidence/resource pins, strict rejection of unknown fields and invalid revisions, and equality with the existing public receipt serializer under the existing canonical profile. Probe SHA-256: `0C63474C59BE9876F79FEB099DFEEC9868CD7267962513492577A819033755FB`. This is feasibility evidence, not task completion or migration evidence.

Retained decoding verifies the declared record type, canonical bytes and retained digest before returning the existing typed object. Compare decoded receipt operation ID/revision/operation with the selected relational row, and compare decoded intent scope/operation/caller key with its relational identity. Verify current receipt bytes against the observation at its current revision. Corrupt, mismatched or undecodable retained data is unavailable; never reconstruct a replacement successful receipt. The digest detects accidental retained-content damage, not hostile database rewriting. Serializers expose only concrete receipt/intent operations and small shared canonical-byte helpers required by those operations; no public serializer framework is introduced.

## Exact import allowance and ownership

The existing snapshot-storage boundary forbids both Pydantic and sibling adapter imports. Amend the gate only for module `craftreport.adapters.storage.serialization`, allowing these exact imported symbols:

- `pydantic.TypeAdapter`
- `pydantic.ValidationError`
- `craftreport.adapters.canonical.canonical_bytes`

All other storage dependencies keep their current rules. Do not allow broad `import pydantic`, wildcard imports, another Pydantic symbol, or general imports of `adapters.canonical`, `transport_wire` or `transport_models`. Existing standard-library imports and inward contract/application imports remain governed by the current boundary. No core contract or application source changes are needed.

Root owns the precise gate change in `scripts/check_imports.py`, positive and negative fixtures in `tests/engineering/test_boundary_gates.py`, and ledger/approved-plan integration. Fixtures must accept the three exact imports only from the named module and reject the same imports from journal/schema/runtime/data, unapproved symbols and wildcard/module imports. Keep the exception before the general layer/external-library rejection without weakening another owner. The serializer remains counted under the most-specific snapshot-storage owner, not the general adapters aggregate.

Task 3.1 owns `storage/journal.py`, `storage/serialization.py` and the necessary journal tables/initialization in `storage/schema.py`; the existing `Database.transaction` remains the transaction and mutex owner. Tests belong in `tests/snapshot_runtime/test_journal.py` and existing `tests/snapshot_runtime/test_database.py` for migration/open behavior. This bounded file addition is recorded before source expansion. No source implementation is authorized by this proposal.

## One journal with command and query records

Retain the Design's existing `commands` and `observations` table names. The commands table is the common retained operation header and current receipt, distinguished by `record_kind` equal to `command` or `query`. There is no second query journal or synthetic CommandIntent for queries.

The commands table has the following minimal retained fields:

| Field | Meaning |
| --- | --- |
| `operation_id` | Primary key; generated once for a command, supplied by the trusted QueryObservation for a query |
| `record_kind` | Closed command/query discriminator |
| `deployment_scope`, `subject` | Trusted ownership scope; nonempty and nonnull |
| `operation_name`, `contract_version` | Exact OperationKey; nonnull |
| `caller_key`, `intent_bytes`, `intent_digest` | Nonnull for commands, all null for queries |
| `revision` | Current positive receipt revision |
| `receipt_bytes`, `receipt_digest` | Exact canonical current Receipt and SHA-256 |
| `handoff_ref` | Optional retained prior handoff identity needed for journal transition invariants |

Use a unique constraint on `(deployment_scope, subject, operation_name, contract_version, caller_key)` for retry admission. The closed discriminator and an explicit check constraint require either the complete command identity/intent group or the entirely null query group; mixed shapes fail at the database boundary. Query rows have no caller key and are never selected by `find(RetryKey)` or command admission. Multiple queries with identical ownership/operation are permitted. Operation IDs remain globally unique within the database, including command/query collisions.

The observations table has `(operation_id, revision)` as its primary key, an operation foreign key to commands without cascading deletion, exact `receipt_bytes`/`receipt_digest`, and optional `handoff_ref`. It retains the complete receipt at every committed revision, including revision 1. This historical representation deliberately preserves exact independently readable receipts; it is not another state authority. Updates append a new observation and change the commands current pointer/content in the same transaction. No API updates or deletes an older observation. A losing CAS writes neither current content nor history. Missing current-history rows or disagreement are unavailable, not a request to regenerate history.

`record_query(observation)` takes ownership exclusively from `observation.principal.deployment_scope` and `.subject`, and checks the configured deployment identity. It builds the revision-1 receipt directly from the actual observation: operation ID/key, correlation ID, capability versions, resources, expected versions, input reference, and update state/stages/diagnostics/evidence/result reference/result availability. Deployment epoch and retention profile come from the opened database. Retain an update handoff reference in the journal field if present; do not fabricate an execution handoff. Insert the query header and revision-1 observation atomically. Duplicate operation IDs cannot overwrite either a query or a command.

Ownership retention does not persist `Principal.permitted_scopes` as future authorization: current trusted access policy still authorizes reads. The existing provider interface returns receipts rather than QueryObservation objects, so no redundant whole-query serialization is needed. Public query invocation creates no command admission, initial accepted command receipt, or retry reservation. Protected access remains outside this journal's principal-free `read(operation_id)` method and uses the retained scope in the later principal boundary.

## Admission, append and failure behavior

Reuse SQLAlchemy expressions/constraints and `Database.transaction` for short synchronous callbacks under its existing process mutex. No transaction spans an await or external I/O. There is no second asyncio admission lock, unit-of-work framework or SQL string implementation.

Admission compares existing CommandIntent values using the kernel's established equivalence: correlation ID and observed capability versions may differ, while fingerprint, normalization policy, resources and expected versions remain significant. Preserve the original intent and receipt when an equivalent retry arrives. Insert command identity, initial ACCEPTED revision-1 receipt and initial observation atomically; return Admitted only after the transaction returns successfully. Scope comes from the trusted RetryKey and must match the configured deployment. A changed subject or operation/key dimension remains a distinct identity within its authorized deployment.

Record compares `expected_revision` and returns the existing RevisionConflict on a loss. It preserves immutable identity fields, appends stages/diagnostics/evidence, advances exactly one revision and uses the existing receipt update semantics for result fields. Reuse `application.outcomes.validate_recorded_update` to check the candidate/readback. Keep only the required storage invariants locally: no terminal overwrite or regression to ACCEPTED; PENDING-to-PENDING requires a new retained handoff identity; AMBIGUOUS resolution requires terminal state and new reconciliation evidence. Full outcome/evidence verification stays in existing `outcome_update` and its trusted caller. Do not import test fixtures or duplicate the complete outcome policy.

Provider failures retain the existing interface distinction: `admit` returns ServiceUnavailable; other journal methods raise ServiceUnavailableError; known missing `record` raises ReceiptMissingError. Parsing/digest/schema failures also mean unavailable. A callback may commit after caller cancellation; uncertain or lost acknowledgement requires retained lookup/readback and never a replacement operation or silent retry of an effect. No failure path deletes retained rows to make a retry appear new.

## Explicit deployment-only v1 to journal v2 migration

Task 1.2 currently creates schema version 1 with only the deployment table. Task 3.1 introduces schema version 2 containing exactly deployment, commands and observations. This amendment authorizes a proposed single known transition, not automatic future schema evolution.

For a genuinely new database, create the complete v2 schema and deployment row in the existing initialization transaction. For an existing database, inspect and validate it before issuing any DDL or writes. Recognize only the exact supported table/column/primary-key/foreign-key/unique/check-constraint structures, expected nullability/types, and allowed indexes for v1 or v2. Reject unexpected user tables, columns, indexes, views and triggers; SQLite-owned internal objects are distinguished from user schema. Use SQLAlchemy metadata/Inspector and expressions, not a homegrown schema language or arbitrary SQL execution. Keep any backend-specific initialization text under the existing database.py restriction.

The v1 migration preconditions are the known deployment-only structure, exactly one singleton row with singleton=1, schema_version=1, and exact configured identity. Require nonempty retained identity/epoch, the supported `retain-all` profile, and configured_limits bytes encoding a finite JSON object. The current v1 initializer writes `b"{}"`; this migration neither interprets additional settings as enabled capabilities nor supplies new settings defaults. Preserve the retained settings bytes unchanged rather than normalizing or rewriting them. Existing partial journal tables, a claimed v2 missing a table/constraint, unknown version, mismatched identity or unexpected schema fail closed without repair. Validation cannot adopt an unrecognized database merely because its deployment row looks plausible.

Within the same `Engine.begin()` transaction and already-held database lifetime lock, create exactly commands and observations, validate the resulting expected v2 structure, and update only deployment.schema_version from 1 to 2. Retain deployment identity, epoch, retention profile and configured_limits byte-for-byte. Do not drop/recreate deployment, generate a new epoch, copy records into a replacement database, or call unrestricted create_all over an unvalidated existing file. The transaction commits both journal tables and the version change or neither. Opening already-valid v2 is read-only validation, not another migration.

Require fault-injection proof after the first table creation and after the version update before commit: reopen the same file and establish the original v1 version, original retained row/settings, and absence of both journal tables. Also prove successful migration and exact reopen, and rejection of unknown/partial/mismatched schemas without changes to retained logical schema/data. Read/open may create a lifetime lock file; this does not authorize modification of rejected database content. If transactional DDL rollback is not established on the installed supported SQLite/Python environment, migration cannot be accepted. Existing explicit `autocommit=False` is necessary but not sufficient evidence.

Future results/evidence/handoff/snapshot/binding tables require their own reviewed version transition. They cannot land through a generic migrate-to-latest loop or a changed v2 schema under the same version. No Alembic dependency or general migration registry is introduced for this one transition.

## Verification and growth forecast

Independent review confirmed that Inspector alone cannot enumerate SQLite triggers or expression indexes. The implementation must supplement it with one fixed `sqlite_schema` inventory using SQLAlchemy `table`/`column`/`select` expressions. This fits the existing expression allowance; no SQL parser or generic schema-comparison framework is authorized. The reviewer reran both TypeAdapter feasibility and this catalog-query probe successfully; production migration still needs the real rollback and compatibility tests below.

Required behavioral evidence covers concurrent equivalent admission with one operation; changed content/preconditions and every scoped retry dimension; correlation/capability-version retry equivalence; simultaneous CAS with exact surviving history; terminal/pending/reconciliation invariants; query ownership, exact observation receipt and absence of a retry reservation; command/query identity collision; exact close/reopen of receipt/intent/history; corruption and missing distinctions; lost acknowledgement; migration success/rollback and unknown-schema rejection. Use real file-backed SQLAlchemy SQLite. Existing synthetic provider tests inform the oracle but do not establish durability. Verify serializer output against independent expected fields/bytes and existing public encoding, rather than only paired encode/decode tests.

Behavioral TDD and task review requirements remain unchanged. Run focused journal/database and import-boundary tests, scoped Ruff lint/format and Pyright, then whole-scope import/breadth/quality gates. Retain commands, exit codes, source identities and evidence under `artifacts/snapshot-runtime/task-3.1/`. Root owns independent review, fresh completion verification, task acceptance and selective commits/hooks/push. This proposal supplies no completion checkmarks.

The measured existing snapshot-storage baseline is 134 LLOC: database.py 102, schema.py 31 and __init__.py 1. Planning estimates for net production growth are serialization 45-75, journal 180-240 and schema/initialization 105-155 LLOC, totaling 330-470 and yielding approximately 464-604/1,500 for storage. That leaves approximately 896-1,036 for later providers and snapshot/binding persistence; it is a reserve estimate, not a promise that all later work fits. Root must reconcile actual source and remaining feature needs before acceptance. Schema/initialization responsibilities remain cohesive and each module stays under 300 LLOC; split only with a separately reviewed responsibility seam if measured implementation cannot fit.

The exact import exception and fixtures add an estimated 10-20 production LLOC to development-gates, counted under that owner's existing aggregate; tests are reported separately. Contracts/application/general-adapters source growth is zero. All existing function 50, module 300, capability 1,500 and McCabe 10 limits remain binding with no waivers or raises. Review actual additions/removals and simplify before accepting any forecast overrun.
