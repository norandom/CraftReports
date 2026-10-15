# Proposed bounded result retention and schema version 4

Status: proposal for independent review; no source implementation, runtime tests,
phase approval or task acceptance is implied. Scope is snapshot-runtime task 3.3,
requirements 5.1, 5.5, 6.2 and 6.3, and Design's DurableSchema/provider contract
and trusted preparation-fact paragraph. Root owns integration and approval.

## Existing protocol constraint

`application/dispatch.py` `QueryDispatcher.execute` creates a fresh operation ID,
calls `_query_result` and `retain_result`, and only afterwards calls
`journal.record_query`. `retain_result` calls `ResultStore.write` and independent
`ResultStore.read`. The existing write signature supplies only trusted Principal,
operation ID and JSON result; a query key and resource/version set are unavailable
to that provider until the existing query observation reaches the journal.
Commands are already journaled before their result is retained.

A mandatory nonnullable result-to-command foreign key therefore contradicts the
current query order. This proposal preserves that order and application source:
trusted result bytes may be staged before query observation, then linked within
the existing `DurableJournal.record_query` transaction. Staging is not a receipt,
accepted query, completion fact or alternate journal.

The public read restriction is established by current code, not assumed:

- `interfaces/http.py` registers GET
  `/v1/operations/{operation_id}/result`; its `_Rest.read_result` authenticates
  and calls `facade.read_result(principal, operation_id)`. It accepts no result
  reference or result-store selector.
- `interfaces/mcp.py` exposes `craftreport.result.v1` with exactly an
  `operation_id` field; `_Mcp.invoke` calls that same facade method.
- `application/execution.py` delegates `Facade.read_result` to
  `Inspection.read_result`. The latter first calls `inspect`; `inspect`
  authorizes `ReceiptAccess(operation_id)`, then reads the journal. Missing
  receipt returns a rejection before result content can be read, even if the
  access policy permits that identity. `_result` obtains the reference only from
  the retained receipt. No public reference-based route exists in these adapters.

Thus an interrupted staged result without a query receipt cannot be retrieved
through the existing public facade. The internal ResultStore read intentionally
supports the trusted pre-journal readback with the original principal/opid/ref.
Task tests will prove this using the actual Inspection implementation with the
real durable journal/results, including an allow-access policy to ensure the
missing-journal check itself prevents disclosure. Public transport wiring remains
unchanged and is not claimed exercised by this provider task.

## Exact schema version 4

Leave all six v3 tables and their DDL unchanged. Add only `results`:

| Column | SQLAlchemy type and constraints |
| --- | --- |
| identity | String primary key; generated opaque UUID hex |
| operation_id | String, nonnull, unique; original trusted operation identity |
| command_operation_id | String, nullable, unique, non-cascading foreign key to commands.operation_id |
| deployment_scope | String, nonnull; authenticated deployment identity |
| subject | String, nonnull; authenticated subject |
| result_bytes | LargeBinary, nonnull; exact canonical result JSON bytes |
| result_digest | String, nonnull; SHA-256 of those exact bytes |

Add the SQLAlchemy CheckConstraint
`command_operation_id IS NULL OR command_operation_id = operation_id`.
The nullable link is the sole staging marker. No additional pending table, timer,
queue, cleanup service, inferred receipt or secondary operation identity exists.
Results are immutable: a second identical write for the same operation/owner
returns the same opaque reference; a different value/owner fails closed. Linking
changes only the nullable foreign key, never retained bytes, digest or owner.

New databases create exactly v4. Opening a validated exact v3 creates `results`,
validates the complete v4 schema, and updates only deployment.schema_version to 4
inside the existing opening transaction. Exact v1/v2 execute their already
reviewed explicit transitions, followed by this explicit v3-to-v4 step. The v3
inventory must remain explicitly recognized now that metadata includes results.
Validate the entire known pre-transition schema before writes. Preserve identity,
epoch, settings, all journal observations, snapshots and evidence byte-for-byte.
Unknown versions, extra objects and partial/wrong results schemas fail untouched.
Use SQLAlchemy Core table/constraint/query expressions only; no handwritten SQL,
migration registry, schema parser or generic migration framework.

Test real rollback after results-table creation and after version update; reopen
must expose the exact original v3 inventory/version/content. Test v1/v2 upgrade,
v3 upgrade with retained commands/query receipts/snapshot facts, v4 read-only
reopen, constraints and unknown/partial schema rejection.

## Result linkage and readback

`DurableResults.write` validates the deployment against Database's retained
identity and checks whether the original operation already exists. Existing rows
must pass `DurableJournal.retained` integrity validation and match trusted subject
and deployment; command results are linked immediately. A missing journal row is
allowed only as trusted staging under the unchanged query protocol. Values are
copied/frozen and canonicalized with an explicit 8 MiB result bound, supporting
the already reviewed reporting output limit without changing snapshot limits.

`DurableJournal.record_query` continues to insert the exact supplied query
observation through its existing path. If its result reference identifies a
staged result, the same transaction validates reference, operation and trusted
owner, and sets command_operation_id to the just-inserted operation. A mismatched
owner/opid, already foreign-linked reference or competing conditional linkage
rolls back the whole query observation. Missing result or failed/unavailable
result observations remain valid existing journal outcomes: do not demand an
available result to record a truthful failed query. An observation claiming AVAILABLE must resolve its exact matching result row
inside the same transaction and independently decode the bytes and match their
digest before linkage. Absent, mismatched or corrupt content rolls back both
query insertion and linkage. This does not rewrite historical receipts when
content later becomes missing or corrupt: later reads report current availability
truthfully while retaining the original observation. No query observation or arbitrary result is synthesized here.

`DurableResults.read` checks principal/opid/ref ownership before decoding protected
bytes. A wrong deployment/subject/opid returns INACCESSIBLE without content.
Absent content is MISSING; closed/I/O/corrupt storage is UNAVAILABLE. Linked rows
must independently validate the retained journal's key, resources, versions,
epoch and ownership using the existing reader, and the exact retained reference
when the receipt already names one. Commands can legitimately be read back before
their final receipt names the result; queries can legitimately be read back while
staged. The original query key and version pins become bound by atomic journal
linkage; the ResultStore signature cannot establish them earlier. No provider
claims that pre-journal staging already has those unavailable fields.

The operation link resolves immutable declared pins through the sole journal;
there is no duplicate mutable version authority. Later local resource changes
do not change old result bytes or reconstruct old results. Staged rows left by a
crash remain inaccessible through public receipt-based reads. Offline explicit
purge stays task 3.5; this task creates no background retention behavior.

## Existing evidence table and preparation seam

`DurableEvidence.inspect` resolves exactly one status per requested EvidenceRef in
input order. It decodes existing canonical reference/fact bytes, independently
checks their digests and original command operation/key/resource set, and requires
the supplied reference to match every stored pin and field. It never regenerates
fact content. Missing, inaccessible/mismatched and corrupt/unavailable outcomes
remain distinct, with PENDING verification whenever not AVAILABLE. Whole provider
failure returns UNAVAILABLE for each input. The protocol supplies no principal:
kernel authorization precedes inspection and inspection returns status rather
than protected fact content. A separate public arbitrary fact reader is excluded.

Supported initial evidence is the real `snapshot_persisted` fact already retained
atomically by SnapshotStore, and the two bounded trusted preparation stages.
Snapshot verification independently matches its closed fact, snapshot row,
content digest, original publication operation and exact retained reference;
later feed advancement does not invalidate a historical persisted snapshot.
Unsupported scopes and non-existent app/artifact/reopen observations cannot be
reported PASSED merely because bytes or a caller-supplied flag exist.

The narrow trusted method remains
`retain_preparation_fact(reference: EvidenceRef, canonical_fact: JsonObject)`
returning EvidenceRef or ServiceUnavailable in `results.py`. It accepts only a
real retained `reports.prepare` command of contract version 1, derives its trusted
deployment/subject, and writes only the existing evidence table. Reference scope
and fact stage must identify `prepared` or `quality_evaluated`. Every reference
contains exactly the full original declared resource set: snapshot plus report
pack source and artifact-scope observations. Reject omitted/extra/duplicate pins,
wrong command/key and conflicts with any actually declared precondition.

Do not require all declared resources to have caller preconditions: the existing
protocol permits omission for commands that do not change business state. Storage
retains the complete observed tuple supplied by trusted reporting composition;
the composed guard/reader and kernel completion independently check authoritative
report-owned observations. Storage imports no reporting/theme/policy modules and
does not invent their current state.

The exact closed six-field envelope is adopted from report-model's
`../craftreport-report-model-packs/preparation-scope-amendment.md`, SHA256
`12A88B1ACFADCD718791B44E6F0EDE097641F6AE9B553F97F77A9A7BBA536300`, independently
approved for this storage seam by `/root/review_results_staging`. Its required
fields are schema_version, stage, prepared_digest, validation_scope_digest,
checks and decision; apply its exact stage-specific closed shapes, strict types,
ordered check sets and <=16,384 canonical-byte bound. No generic writer is added.
Prepared facts contain the three actual passed internal source checks; quality
facts retain the evaluator's nine findings and actual decision, including false
eligibility. Verification PASSED proves those retained bytes/facts were inspected,
not that release was permitted. Reporting owns actual evaluation/typed conversion;
storage owns closed wire validation and original command/full-pin integrity.

Before return, independently reread exact fact bytes/digest, reference and all
original pins from the existing table using the same evidence reader semantics;
reuse an identical existing ref/fact, reject identity collisions with different
content. An interrupted fact-only write never establishes a complete prepared
result or receipt. There is no public writer, CommandContext extension, second
completion authority, new evidence table or source-body retention.

## Files, reuse and bounded forecast

Proposed new `src/craftreport/adapters/storage/results.py` owns result retention
and the narrow trusted preparation write. Proposed new sibling `evidence.py` owns
independent retained-fact verification/readback, a separate concrete provider
responsibility that prevents result/purge methods and two fact validators from
crowding one module. Both use existing Database.transaction/mutex,
DurableJournal.retained, canonical bytes and TypeAdapter(EvidenceRef). No new
provider framework or custom serialization engine is justified.

Before new source, root must add this exact evidence.py path to the Design file
plan and most-specific snapshot-storage ownership planning, and increase the
ledger's actual module count only when each real module is created. All existing
caps and import rules remain unchanged. Existing parent ownership already covers
the storage directory; this is explicit module accounting, not a new capability.

| Owned change | Planning delta LLOC |
| --- | ---: |
| results.py new | 130-150 |
| evidence.py new | 140-160 |
| serialization.py bounded existing codec reuse | 10-20 |
| schema.py exact v4 table/transition | 30-40 |
| journal.py atomic query result linkage | 15-20 |
| Total production delta | 325-390 |

Storage baseline is 697/1,500 LLOC; forecast is 1,022-1,087, leaving 413-478 for
later providers/bindings. This is a proportionality target, not a waiver or proof
of feasibility. Keep function/module/McCabe limits 50/300/10. If exact schema or
evidence semantics exceed the target, simplify within the reviewed seam and bring
measured growth to root before expanding. No speculative future provider code.

Tests belong to `tests/snapshot_runtime/test_results.py` and `test_evidence.py`,
with narrow existing database/journal test updates for schema/linkage regressions.
Reuse existing pytest fixtures where practical. Tests must prove real file bytes,
opaque immutable references, large supported result profile, no mutable aliases,
owner/operation isolation, truthful missing/unavailable/corrupt distinction,
staged public-read rejection, atomic query linking and crash cutpoints, exact
pin/ref preservation, unsupported-scope refusal, preparation boundedness and
failed quality decision preservation, plus close/reopen persistence.

After explicit GO, use actual behavioral flag OFF/RED, ON/GREEN and removed/GREEN
with captured logs. Run scoped canonical
`uv.exe run --frozen python -m pytest` checks, Ruff lint/format, strict Pyright and
the actual import/breadth/quality gates. Root coordinates shared checks and the
installed commit hook; no redundant whole-suite run or browser acceptance is
part of this task. Freeze source hashes before final checks and record actual
commands, exit codes, source/test LLOC and file-backed identities/readback under
`artifacts/snapshot-runtime/task-3.3`. Root owns tasks/spec metadata, acceptance,
selective commit and push.
