# Proposed bounded stopped-host retention maintenance

Status: task 3.5 proposal for independent review under the owner-directed
overnight fast-track. It changes no implementation, phase approval, task status,
ledger or numeric limit. Task 3.4 must be accepted and its final storage shape and
measured budget reconciled before this proposal can authorize source work. The
scope is requirements 5.1, 5.5, 5.7 and 6.2 and the Design's explicit offline
purge; root owns integration and approval.

## Concrete retained representation

Use the existing schema after task 3.4's exact v5 transition. Do not change its
nonnullable constraints or add a v6 migration merely to represent removed
payloads. Reserve `b"\x00CRAFTREPORT-PURGED-CONTENT-V1\n"` as an exact binary
prefix followed by a small canonical JSON object. The zero byte cannot begin a
valid canonical producer/snapshot/result JSON object, including an arbitrary
result object. Recognize a tombstone only after full prefix, checksum, canonical
closed-envelope, row and retained-link validation; a prefix alone is corrupt.
The envelope is a closed local storage record, never a public wire value.

The snapshot envelope has exactly `kind="snapshot"`, `schema_version="1"`,
`deployment_identity`, `deployment_epoch`, `feed_id`, `producer_version`
(positive canonical decimal string), `subject`, `operation_id`, original
`content_digest` and original `snapshot_digest`. The result envelope has exactly
`kind="result"`, `schema_version="1"`, `deployment_identity`,
`deployment_epoch`, `identity` (opaque reference), `operation_id`, nullable
`command_operation_id`, `deployment_scope`, `subject` and original
`result_digest`. Require exact field types and keys, canonical decimal
and SHA-256 forms, the expected `kind`, and an exact match to every corresponding
retained row/deployment/feed field. For snapshots, also independently match the
unchanged original `content_digest`, feed/version and operation ID to the closed
retained `snapshot_persisted` fact and its journal linkage. For linked results,
verify the retained command/query operation and owner, plus its result reference
when the receipt already names one; staged
query results retain their explicit null link and are never described as
journaled. A transplanted tombstone whose bytes/checksum belong to another row
is Unavailable, not Missing.

Build the JSON body with existing `encode_object` under a 4 KiB envelope cap.
Store `prefix + body`; checksum those exact retained bytes with SHA-256 in the
existing digest column. On read, check this full-byte checksum first, then
canonical-decode the JSON suffix with existing `decode_object` and a derived
suffix digest, then verify its
closed shape and row/link matches. Reuse the existing canonical codec/hash
helpers or standard SHA-256 for the prefixed checksum; do not introduce a
serializer framework. A purged snapshot has **both** `producer_bytes` and
`snapshot_bytes` equal to the same complete envelope bytes. Its row
`snapshot_digest` changes to the envelope checksum; its `content_digest` stays
the original producer identity digest and is checked against the envelope and
retained fact. A purged result has `result_bytes` equal to its envelope;
`result_digest` changes to that envelope checksum. The original snapshot/result
digests survive inside their checked envelopes. Any one-sided snapshot envelope,
valid-hex checksum damage, noncanonical/oversized envelope, changed metadata or
broken link is Unavailable/corrupt. Already tombstoned rows receive the full
same validation as newly selected rows before an idempotent no-op.

Keep snapshot identity rows, result identity/owner/link rows, feed subject,
revision and high-water, original deployment identity/epoch/profile/settings,
complete command/query retry identities and original intents, current and
historical receipts, handoffs, and all evidence facts. Never delete or rewrite
these to make space. Do not purge binding/run state, prepared facts, receipt or
evidence bytes in this task. Original digests in tombstones describe removed
content; the changed digest columns check current envelope bytes. Define the
prefix and the two closed envelope operations once in `storage/serialization.py`
for existing snapshot/result/evidence readers. The marker must never be decoded
as original content or used to regenerate a value.

This is a content-removal change compatible with current nonnullable v4/v5
tables and foreign keys. It detects accidental changes to the retained checksum,
original digest or identity without claiming protection from a hostile writer
who rewrites both data and hashes. Before implementation, verify that task 3.4's
accepted schema still has these columns and that valid canonical content cannot
start with the reserved prefix. If either premise changes, return for review
rather than adapting the schema silently.

Removal here affects only the explicitly selected stored payload columns. An
unselected result or other retained fact may contain copied values; this API
does not discover or cascade to such copies. SQLite may also leave old bytes in
pages, rollback files or backups. The task makes no privacy-wide or secure
erasure claim, no backup-expiry claim, and adds no compaction/PRAGMA operation.

## Typed operator operation and lifetime

Provide a trusted, offline-only `async def purge_retained(path: Path,
deployment_id: str, selection: PurgeSelection) -> PurgeReport |
ServiceUnavailable`, not a REST/MCP command or host background job.
`PurgeSelection` contains exact tuples of
`SnapshotRef(feed_id, producer_version, content_digest)` and
`ResultContentRef(operation_id, opaque_reference)`; `PurgeReport` contains the
unchanged deployment epoch and exact affected snapshot/result references in
selection order. It lists only references whose original payload bytes changed
in the committed transaction. An already purged selected reference is a valid
idempotent no-op and is absent from the affected list. An unknown reference or
one mismatched to its selected retained identity rejects the batch before any
write. No wildcard,
age filter, TTL, feed-wide selector, implicit referenced-content cascade or
silent best-effort batch is supported.

Validate nonempty selection, concrete immutable input types, at most 32 total
references, canonical identifiers/digests and no duplicates before opening
storage. Inside the same locked SQLAlchemy transaction, first select only
identity/owner/link/digest metadata and `func.length` of each selected BLOB;
do not select BLOB values at this stage. Count **both** snapshot payload columns
and each result payload. Null/negative or over-profile per-row lengths indicate
unavailable retained data; more than 64 MiB in aggregate is an invalid batch.
Reject either before materializing any selected payload. A larger valid request
fails unchanged and can be split by the operator.
Then fetch only the selected, length-accepted rows and independently validate
their canonical original payload/digests or the complete tombstone envelope,
the exact selected identity, deployment/feed ownership and retained journal
relationship where present. A malformed giant BLOB must fail on the lengths-only
preflight without decoding or loading its bytes into Python.

Select and validate **all** rows before writes. Update only the selected payload and their checksum columns
in one short SQLAlchemy Core transaction, with conditional predicates that still
match the selected identity and original digest/bytes; a lost match aborts the whole
transaction. Re-read envelope state and retained identity/checksum before returning
the affected list. Do not hold an await or external I/O inside that transaction.
Malformed, duplicate, unknown or mismatched selections, including the bounded
size rejection, raise `InvalidPurgeSelection(ValueError)` and leave the file
unchanged. Host lock, I/O, wrong deployment, unsupported schema, close and
uncertain commit return `ServiceUnavailable("retention")`; the caller must
reopen/read back before deciding whether to repeat a request whose
acknowledgement was lost. Retained corruption is Unavailable, never converted to
a validation error or a known Missing tombstone.

Maintenance must require an existing database file, the exact configured
deployment and the **accepted current v5 schema**. Add a narrow maintenance
open option to the current `Database`: after acquiring its existing OS lifetime
lock and before engine initialization, reject a missing file; then run the
existing exact schema validation in a nonmigrating mode that rejects recognized
older versions before `_upgrade`. No database bytes or schema change merely
because maintenance was attempted. A missing file must never be created by a
purge request. A populated valid v4 file with an invalid selection must remain
byte/logically unchanged at v4. Keep the lock from validation through transaction
and close. If a host
owns the lock, maintenance fails closed without touching its database. If
maintenance wins, a host cannot open until it closes. Reuse Database's mutex,
engine, schema validation and explicit transaction. Do not duplicate the OS
locking code, open a second engine beside a live Database, change PRAGMA policy,
use raw `sqlite3` writes, or add handwritten SQL for this operation. Only the
bounded operator API receives a path; ordinary capability callers do not. This
is a trusted local operator action authorized for the configured deployment by
explicit invocation and local file access, not a per-subject public operation.
Selection checks prove retained subject/operation/link consistency; they do not
pretend that a nonexistent Principal authorized every subject. Public result
reads still check the actual caller's Principal before exposing availability or
protected content.

Run the transaction in a task protected from outer cancellation. If cancellation
or another failure arrives after worker dispatch, wait for the worker to finish
or fail, then await database close to completion while retaining the OS lock;
only then propagate cancellation or return Unavailable. Do not cancel
`asyncio.to_thread` and release the lock while its SQLite transaction continues.
Use shield-and-drain behavior for both the worker and close, including repeated
cancellation. A successfully committed but unacknowledged purge is reconciled by
reopening and validating the selected envelopes; it is never assumed rolled
back merely because the async caller was cancelled.

## Read, retry and historical truth after purge

Snapshot lookup distinguishes three states from a validated row: canonical bytes
decode and match all identity fields as today; the exact paired, fully verified
envelope is known Missing content; any partial prefix, one-sided envelope or
other invalid bytes is Unavailable. A
missing snapshot identity row remains Missing. A feed read stays authoritative
from its retained high-water snapshot **identity row** and digest even when that
row's content is purged. It must no longer require latest content to build feed
metadata. A missing/corrupt high-water identity row is Unavailable; do not search
backward to an older, still-present snapshot. `snapshot.read` for a purged exact
reference returns Missing. A new higher valid version may advance the same feed
and become readable normally.

Publication fully validates an existing `(feed_id, producer_version)` row as
original content or a checked tombstone, then compares its retained original
`content_digest` **before** attempting current content readback. Equal content returns its original
identity with no apply, including if that content was purged; different content
conflicts. An unseen lower version remains stale against retained high-water.
The old retry key remains in the journal with its original receipt/result ref and
can never be admitted as new merely because payload bytes were purged. An equal
producer-version republication through a new retry key must not refill purged
content. A new higher version follows ordinary validation, atomic acceptance and
readback. Repeated result writes for a purged operation must fail closed rather
than refill its original result row. The unchanged receipt may say its result was
AVAILABLE when recorded; a current result read returns MISSING after ownership
and reference checks. An unknown reference is Missing; a corrupt marker, digest
or linked journal is Unavailable; a wrong owner remains Inaccessible.

Keep historical receipt revisions and evidence facts byte-for-byte. They prove
what was recorded then, while current content availability is checked now. A
retained `snapshot_persisted` fact cannot newly return PASSED by trusting only
its stored digest after the backing snapshot bytes are purged. Its inspection
must report Missing supporting content (and no passed verification); malformed
retained fact/identity instead remains Unavailable. Preparation evidence may
still verify its own retained fact bytes and original pins, but cannot claim that
the purged snapshot or result can be reproduced. No past PASSED observation is
rewritten and no new success fact is synthesized. Retention inspection should
continue to describe the `retain-all` default plus explicit offline removal and
current Missing-versus-Unavailable behavior; the purge report supplies the exact
affected list. No new retention epoch is minted.

## Ownership, budget and acceptance evidence

Reuse `storage/database.py` for the existing-file lock/open seam,
`storage/snapshots.py` for tombstone-aware snapshot/feed/publication behavior,
`storage/results.py` for result reads/writes, and `storage/providers.py` for the
small typed operator/report values. The snapshot evidence check in
`storage/evidence.py` also needs the narrow Missing behavior above; task 3.5's
file list should be reconciled by root before source expansion. If a cohesive
operator callback cannot fit an existing module's 300-LLOC cap, propose a
responsibility-named module and ledger entry for separate review rather than
splitting solely to move LLOC. No other capability or generic retention layer is
activated.

The independently reviewed task 3.4 plan measured storage at 949/1,500 LLOC and
forecast 170-230 for 3.4, 90-130 for this task and 170-220 for task 5.1. This
would leave 1,379-1,529/1,500, with the upper case over by 29. During active
3.4 edits, a provisional local measurement was 1,129 LLOC; it is not an accepted
baseline and excludes possible unfinished work. Task 3.5 must remeasure after
3.4 acceptance. To preserve 170-220 for binding/run persistence, its maximum
available growth is `1,500 - accepted_3.4_storage_LLOC - 220` on the cautious
forecast. Target at most 90-130 net storage LLOC using existing SQLAlchemy and
codecs; simplify or return to root if the measured implementation cannot meet
50/function, 300/module, 1,500/capability and McCabe 10. No cap raise, waiver,
ownership move or future-task borrowing is approved here.

Behavioral tests must use an actual file, a competing host process/owned lock,
and close/reopen. Prove active-host rejection and no change, missing-file and
wrong-deployment rejection, exact selected/affected lists and idempotent repeat,
all-or-nothing invalid batch and injected transaction/acknowledgement failure,
exact original epoch/identity/settings/high-water/journal history, and byte
removal with checked envelopes/original digests. Prove valid-hex checksum or
original-digest corruption and transplanted envelopes report Unavailable after
reopen; an oversized malformed BLOB is rejected by lengths-only preflight
without payload materialization. Prove a populated recognized older schema plus
an invalid selection remains at its original version with unchanged rows. Prove
cancellation and lost acknowledgement keep the lifetime lock until the worker
and close finish. Prove purged latest feed metadata with no
older fallback; old retry and equal-version republication cannot re-execute or
rehydrate; different same-version conflicts; unseen lower is stale; new higher
works. Verify protected result reads, Missing versus Unavailable for partial or
corrupt envelopes, historical evidence without regenerated PASSED, and exact
current health-probe behavior: a valid tombstone is structurally healthy with
Missing content, while damaged retention is Unavailable. Verify exact
reopen/readback. Tests must compare independent original and post-purge file
facts, not merely paired operator return values. Use focused tests and scoped
Ruff/format/Pyright/import/breadth/quality gates; root coordinates the canonical
hook/fast check and independent review. Retain commands, exit codes, file/row
identities and source hashes under `artifacts/snapshot-runtime/task-3.5/`. This
proposal is not implementation evidence or a task completion claim.
