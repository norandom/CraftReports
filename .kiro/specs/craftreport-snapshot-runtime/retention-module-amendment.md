# Proposed cohesive offline retention module

Proposal only for task 3.5. No new source module is created by this amendment.

## Measured reason and boundary

The first implementation measures 1,373 storage LLOC against the unchanged 1,500 cap, up 221 from the accepted 1,152 baseline. `providers.py` measures 343 against the 300 module cap. The earlier 90–130 estimate for task 3.5 was too low. The current 127 remaining LLOC does not establish that later publication/query and bindings work will fit; later work requires measured reuse or a scope halt before exceeding the cap. The complete earlier 315–450 remaining-work forecast remains a risk record, not a guarantee.

Move the complete privileged offline removal operation into `src/craftreport/adapters/storage/retention.py`, within the same storage owner, import boundary and aggregate cap. This is a cohesive operation with explicit selection, metadata-only preflight, atomic replacement, readback and cancellation cleanup. It does not place unrelated purge logic into existing readers to evade a module limit.

## Exact symbols and imports

Move these symbols from `providers.py` without changing their approved retention semantics:

- `InvalidPurgeSelection`, `ResultContentRef`, `PurgeSelection`, `PurgeReport`.
- `_purge_key`, `_purge_preflight`, `_purge_payload`, `_purge`.
- `_drain_purge`, `purge_retained`.

The temporary RED-phase `_RETENTION_ENABLED` flag is removed before delivery. The canonical trusted operator import becomes `craftreport.adapters.storage.retention.purge_retained`; the new, unaccepted retention tests import this module directly. There is no public reexport shim, REST/MCP endpoint, provider registry or additional capability.

The module reuses existing `Database` lifetime/transactions, `StorageUnavailable`, SQLAlchemy expressions and existing schema tables, `DurableResults.read_retained`, `snapshot_evidence`, and the fixed serialization tombstone helpers. It introduces no schema, engine, locking mechanism or boundary exception. `providers.py` retains concrete resource, handoff and health providers and loses only the complete offline block and its unused imports.

## Owned files and measured follow-up

The implementation ownership is the existing `database.py`, `snapshots.py`, `results.py`, `providers.py`, `evidence.py`, `serialization.py`, proposed `retention.py`, and focused retention tests. `schema.py` remains unchanged. Fixed tombstone encoding stays in serialization; current reads and evidence remain with their existing owners; current-schema maintenance opening stays with `Database`.

Before the move, the offline block is approximately 132 LLOC including the temporary flag. The expected split is approximately 211 in providers and 140 in retention, with roughly 5–12 additional aggregate import/documentation lines. These are estimates pending an actual measurement, not a fit guarantee or cap increase. All new-module LLOC still counts against storage's 1,500 cap. Root registers the module inventory only after independent approval.

Existing raw RED and flag-off logs remain evidence. Verification retains real-file removal/reopen, unchanged identity rows, mixed-selection atomicity and rollback, metadata-only size preflight, corruption rejection, repeated cancellation and lock lifetime. After approval and the move, run focused tests, scoped typed/lint/format checks, current quality/import/breadth gates, and freeze actual source hashes for independent review. Root retains specification, ledger and commit ownership.
