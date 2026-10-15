"""Trusted stopped-host removal of explicitly selected retained content."""

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Table, and_, func, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.sql.dml import Update
from sqlalchemy.sql.elements import ColumnElement

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.evidence import STORAGE_FAILURES, snapshot_evidence
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import feeds, results, snapshots
from craftreport.adapters.storage.serialization import ContentKind, TombstoneLimit, encode_tombstone
from craftreport.adapters.storage.snapshots import read_retained_snapshot
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import Availability, Principal
from craftreport.contracts.values import require_text
from craftreport.data.values import Snapshot, SnapshotRef


class InvalidPurgeSelection(ValueError):
    """An explicit offline selection cannot be applied as one bounded batch."""


@dataclass(frozen=True, slots=True)
class ResultContentRef:
    operation_id: str
    opaque_reference: str

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")
        require_text(self.opaque_reference, "opaque_reference")


@dataclass(frozen=True, slots=True)
class PurgeSelection:
    snapshots: tuple[SnapshotRef, ...] = ()
    results: tuple[ResultContentRef, ...] = ()

    def validate(self) -> None:
        if (
            type(self.snapshots) is not tuple
            or type(self.results) is not tuple
            or not 0 < len(self.snapshots) + len(self.results) <= 32
            or any(type(ref) is not SnapshotRef for ref in self.snapshots)
            or any(type(ref) is not ResultContentRef for ref in self.results)
        ):
            raise InvalidPurgeSelection("Select 1..32 concrete immutable references")
        try:
            for ref in self.snapshots:
                SnapshotRef(ref.feed_id, ref.producer_version, ref.content_digest)
            for ref in self.results:
                ResultContentRef(ref.operation_id, ref.opaque_reference)
        except (ValueError, TypeError) as error:
            raise InvalidPurgeSelection("Invalid removal identity") from error
        if len({(ref.feed_id, ref.producer_version) for ref in self.snapshots}) != len(
            self.snapshots
        ) or len(set(self.results)) != len(self.results):
            raise InvalidPurgeSelection("Duplicate removal identity")


@dataclass(frozen=True, slots=True)
class PurgeReport:
    deployment_epoch: str
    snapshots: tuple[SnapshotRef, ...]
    results: tuple[ResultContentRef, ...]


def _purge_key(
    ref: SnapshotRef | ResultContentRef,
) -> tuple[Table, ContentKind, ColumnElement[bool]]:
    if isinstance(ref, SnapshotRef):
        return (
            snapshots,
            "snapshot",
            and_(
                snapshots.c.feed_id == ref.feed_id,
                snapshots.c.producer_version == ref.producer_version,
            ),
        )
    return (
        results,
        "result",
        and_(
            results.c.identity == ref.opaque_reference, results.c.operation_id == ref.operation_id
        ),
    )


def _purge_preflight(connection: Connection, selection: PurgeSelection) -> None:
    total = 0
    for ref in (*selection.snapshots, *selection.results):
        table, kind, predicate = _purge_key(ref)
        blobs = ("producer_bytes", "snapshot_bytes") if kind == "snapshot" else ("result_bytes",)
        columns = [column for column in table.c if column.name not in blobs]
        row = (
            connection.execute(
                select(
                    *columns, *(func.length(table.c[name]).label(name + "_size") for name in blobs)
                ).where(predicate)
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or isinstance(ref, SnapshotRef)
            and ref.content_digest != row["content_digest"]
        ):
            raise InvalidPurgeSelection("Selected identity is missing or differs")
        for name in blobs:
            size = row[name + "_size"]
            if type(size) is not int or not 0 <= size <= (
                1_048_576 if kind == "snapshot" else 8_388_608
            ):
                raise StorageUnavailable("Retained payload exceeds its profile")
            total += size
    if total > 67_108_864:
        raise InvalidPurgeSelection("Split batches above 64MiB")


def _purge_payload(
    connection: Connection,
    database: Database,
    ref: SnapshotRef | ResultContentRef,
    snapshot_codec: Codec[Snapshot],
) -> tuple[bytes, str] | None:
    table, kind, predicate = _purge_key(ref)
    stored = connection.execute(select(table).where(predicate)).mappings().one()
    row = dict(stored)
    if kind == "snapshot":
        status = snapshot_evidence(connection, database, row["operation_id"])
        if status.availability is Availability.AVAILABLE:
            read_retained_snapshot(snapshot_codec, stored)
        row["subject"] = connection.execute(
            select(feeds.c.subject).where(feeds.c.feed_id == row["feed_id"])
        ).scalar_one()
    else:
        status = DurableResults(database).read_retained(
            connection,
            Principal(row["deployment_scope"], row["subject"], frozenset()),
            row["operation_id"],
            row["identity"],
        )
    if status.availability not in (Availability.AVAILABLE, Availability.MISSING):
        raise StorageUnavailable("Selected retained content is unavailable")
    return (
        None
        if status.availability is Availability.MISSING
        else encode_tombstone(kind, database.deployment, row)
    )


def _purge(
    connection: Connection,
    database: Database,
    selection: PurgeSelection,
    snapshot_codec: Codec[Snapshot],
) -> PurgeReport:
    _purge_preflight(connection, selection)
    changes: list[Update] = []
    affected: list[SnapshotRef | ResultContentRef] = []
    for ref in (*selection.snapshots, *selection.results):
        replacement = _purge_payload(connection, database, ref, snapshot_codec)
        if replacement is None:
            continue
        table, kind, predicate = _purge_key(ref)
        row = connection.execute(select(table).where(predicate)).mappings().one()
        payload, digest = replacement
        values = (
            {"snapshot_bytes": payload, "producer_bytes": payload, "snapshot_digest": digest}
            if kind == "snapshot"
            else {"result_bytes": payload, "result_digest": digest}
        )
        changes.append(
            update(table)
            .where(*(column == row[column.name] for column in table.c))
            .values(**values)
        )
        affected.append(ref)
    for statement in changes:
        if connection.execute(statement).rowcount != 1:
            raise StorageUnavailable("Selected content changed during removal")
    if any(
        _purge_payload(connection, database, ref, snapshot_codec) is not None for ref in affected
    ):
        raise StorageUnavailable("Removal readback differs")
    return PurgeReport(
        database.deployment.epoch,
        tuple(ref for ref in affected if isinstance(ref, SnapshotRef)),
        tuple(ref for ref in affected if isinstance(ref, ResultContentRef)),
    )


async def _drain_purge[T](task: asyncio.Task[T]) -> T:
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


async def purge_retained(
    path: Path, deployment_id: str, selection: PurgeSelection, *, snapshot_codec: Codec[Snapshot]
) -> PurgeReport | ports.ServiceUnavailable:
    if type(selection) is not PurgeSelection:
        raise InvalidPurgeSelection("A concrete removal selection is required")
    selection.validate()
    try:
        database = Database(path, deployment_id, maintenance=True)
        try:
            worker = asyncio.create_task(
                database.transaction(lambda c: _purge(c, database, selection, snapshot_codec))
            )
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                try:
                    await _drain_purge(worker)
                except Exception:
                    pass
                raise
        finally:
            await _drain_purge(asyncio.create_task(database.close()))
    except TombstoneLimit as error:
        raise InvalidPurgeSelection(str(error)) from error
    except InvalidPurgeSelection:
        raise
    except STORAGE_FAILURES:
        return ports.ServiceUnavailable("retention")
