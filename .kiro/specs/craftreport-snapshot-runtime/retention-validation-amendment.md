# Proposed existing-codec validation for offline retention

Proposal only; production remains frozen pending independent review. The approved module amendment SHA256 `D152DF4B50450724A64CC54AA947704EA44A77BA8456F7E54267709208DFFE74` is unchanged.

## Finding and exact signature

The preserved `artifacts/snapshot-runtime/task-3.5/red-contract.log` shows that a selected snapshot with canonical JSON and a matching rewritten checksum but an invalid `received_at` was removed. Existing `snapshot_evidence` verifies canonical bytes, producer identity, original fact and journal linkage; it does not run the full snapshot wire codec. A trial direct import of `adapters.snapshot_wire.snapshot_codec` into storage was rejected by the import gate and removed. This is a known limitation of the currently frozen candidate, not passing acceptance evidence. The runnable negative probe is retained separately under the same artifact directory.

Require the trusted caller to supply the already approved codec explicitly:

```python
async def purge_retained(
    path: Path,
    deployment_id: str,
    selection: PurgeSelection,
    *,
    snapshot_codec: Codec[Snapshot],
) -> PurgeReport | ServiceUnavailable:
    ...
```

The keyword is mandatory, including result-only selections; no default codec, alternate decoder, registry or boundary exception is introduced. Trusted operator composition and the focused tests supply the existing `craftreport.adapters.snapshot_wire.snapshot_codec()` from outside storage. This internal API is not yet accepted or exposed through REST/MCP, so no compatibility shim is needed. Storage depends only on the existing inward `application.registry.Codec` and `data.values.Snapshot` contracts, as its live snapshot reader already does.

## Exact reuse and owned changes

In existing `storage/snapshots.py`, extract the current `SnapshotStore.prepare` implementation into concrete module function `prepare_publication(codec: Codec[Snapshot], change: JsonObject) -> Publication`; preserve the existing instance method as a direct delegate. Extract only the normal, non-tombstone part of `SnapshotStore._content` into `read_retained_snapshot(codec: Codec[Snapshot], row: RowMapping) -> ResourceSnapshot`. It performs the existing `decode_object`, `prepare_publication`, original feed/version/content digest comparison, original producer-byte and finalized snapshot-byte comparisons, then returns the existing resource snapshot. `SnapshotStore._content` keeps its current tombstone/evidence branch and delegates normal content to this same function. This moves the existing validation logic; it does not copy it or change codec semantics.

In existing `storage/retention.py`, pass the required codec through `_purge` and `_purge_payload`. Retain the selected SQLAlchemy `RowMapping` alongside the current metadata dictionary. After existing `snapshot_evidence` proves Available original supporting content, call `read_retained_snapshot(snapshot_codec, stored_row)` before preparing a tombstone. Existing validated tombstones remain on their full paired-envelope/original-fact/journal path and are never decoded as snapshots. Result validation remains `DurableResults.read_retained`. Length-only preflight still completes for all selections before any BLOB load, and every selected row still validates before any update. The codec does not add a second engine, transaction, effect, lease or await inside the transaction.

Only `snapshots.py`, `retention.py`, and focused retention tests change for this seam. No new module, schema, public endpoint, ledger owner, import permission or live composition change is requested. `evidence.py` retains its existing narrow responsibilities. The existing live resource reader and offline remover use the same concrete retained snapshot validation function.

## Evidence and capacity

Restore the preserved negative probe as a normal regression with the required injected codec. It must return Unavailable and leave all rows unchanged for invalid typed snapshot content despite valid canonical encoding/checksum. Also retain the actual file/reopen, retry/no-rehydration, staged result, transplant, preflight, rollback, uncertain acknowledgement, competing process and repeated worker/close cancellation cases; update every operator invocation with the real codec. Test a missing mandatory keyword as a Python contract error, without opening storage. Rerun all focused tests, scoped Pyright/Ruff/format and actual quality/import/breadth gates; freeze hashes after success.

The current candidate measures 1,384/1,500 storage LLOC (116 remaining), with providers 210 and retention 144. Moving validation with small delegates and codec parameters is estimated at 9–14 net LLOC, approximately 1,393–1,398 total; measure it rather than claim a fit. This does not change the cap or the earlier complete 315–450 forecast risk. Later publication/query and binding work remains dependent on measured reuse or a scope halt before any cap excess. Independent review remains required before this seam is implemented and before task 3.5 acceptance.
