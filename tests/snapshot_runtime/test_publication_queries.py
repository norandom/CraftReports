"""Bounded coherent selection, exact identity and offline removal readback."""

import asyncio
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import event, update
from sqlalchemy.engine import Connection, Engine

from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.retention import PurgeSelection, purge_retained
from craftreport.adapters.storage.schema import commands
from craftreport.application import ports
from craftreport.contracts import Availability, JsonObject, Principal
from craftreport.data.requirements import DatasetRequirement, InputRequirements
from craftreport.data.values import Snapshot
from craftreport.runtime.publication import LatestRequest, LatestSelection, PublicationDecision
from tests.snapshot_runtime.test_providers import FEED, admitted, producer, provider, publish

ALICE = Principal("deployment-a", "alice", frozenset())
INCOMPLETE = InputRequirements((DatasetRequirement("missing", ()),), ())


def test_cancelled_scan_drains_page_worker_and_reopens(tmp_path: Path) -> None:
    entered, release = Event(), Event()
    pages = 0

    def block_second_page(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal pages
        if "ORDER BY snapshots.producer_version DESC" in statement:
            pages += 1
            if pages == 2:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("Test page worker was not released")

    async def exercise() -> None:
        path = tmp_path / "cancelled-scan.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        try:
            resources = provider(database)
            for version in range(1, 18):
                assert isinstance(
                    await publish(
                        resources, database, version, str(version - 1) if version > 1 else "absent"
                    ),
                    ports.ResourceEffect,
                )
            event.listen(Engine, "before_cursor_execute", block_second_page)
            try:
                scan = asyncio.create_task(
                    resources.store.queries(ALICE).latest(LatestRequest(FEED.identity, INCOMPLETE))
                )
                assert await asyncio.to_thread(entered.wait, 5)
                scan.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(scan, 2)
                release.set()
                selected = await asyncio.wait_for(
                    resources.store.queries(ALICE).latest(LatestRequest(FEED.identity, INCOMPLETE)),
                    3,
                )
                assert isinstance(selected, LatestSelection) and selected.selection_status == "none"
                assert isinstance(
                    await asyncio.wait_for(publish(resources, database, 18, "17"), 3),
                    ports.ResourceEffect,
                )
            finally:
                release.set()
                event.remove(Engine, "before_cursor_execute", block_second_page)
        finally:
            await asyncio.wait_for(database.close(), 3)
        reopened = Database(path, ALICE.deployment_scope)
        try:
            latest = (
                await provider(reopened).store.queries(ALICE).latest(LatestRequest(FEED.identity))
            )
            assert (
                isinstance(latest, LatestSelection)
                and latest.latest_accepted.producer_version == 18
            )
        finally:
            await reopened.close()

    asyncio.run(exercise())


def test_maximum_producer_version_is_selectable(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "maximum.sqlite3", ALICE.deployment_scope)
        try:
            resources = provider(database)
            await publish(resources, database, 2**63 - 1)
            found = await resources.store.queries(ALICE).latest(
                LatestRequest(FEED.identity, InputRequirements((), ()))
            )
            assert isinstance(found, LatestSelection) and found.highest_complete is not None
            assert found.highest_complete.producer_version == 2**63 - 1
        finally:
            await database.close()

    asyncio.run(exercise())


def test_older_complete_selection_after_multiple_pages(tmp_path: Path) -> None:
    async def exercise() -> None:
        from craftreport.contracts import ExpectedVersion

        database = Database(tmp_path / "complete.sqlite3", ALICE.deployment_scope)
        try:
            resources = provider(database)
            content: JsonObject = {
                **producer(),
                "datasets": [
                    {
                        "name": "missing",
                        "label": "Complete",
                        "fields": [],
                        "rows": [],
                        "keys": [],
                        "source_ref": "source",
                        "producer_id": "producer",
                        "source_version": None,
                    }
                ],
            }
            _, change = await admitted(database, content_override=content)
            async with resources.guard.acquire((ExpectedVersion(FEED, "absent"),)) as guard:
                assert isinstance(await resources.apply(FEED, change, guard), ports.ResourceEffect)
            for version in range(2, 19):
                await publish(resources, database, version, str(version - 1))
            found = await resources.store.queries(ALICE).latest(
                LatestRequest(FEED.identity, INCOMPLETE)
            )
            assert isinstance(found, LatestSelection) and found.highest_complete is not None
            assert found.latest_accepted.producer_version == 18
            assert found.highest_complete.producer_version == 1 and len(found.latest_issues) == 1
        finally:
            await database.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("count", [17, 64, 65])
def test_exhaustion_is_distinct_from_scan_limit(tmp_path: Path, count: int) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "scan.sqlite3", ALICE.deployment_scope)
        try:
            resources = provider(database)
            for version in range(1, count + 1):
                outcome = await publish(
                    resources, database, version, str(version - 1) if version > 1 else "absent"
                )
                assert isinstance(outcome, ports.ResourceEffect)
            queries = resources.store.queries(ALICE)
            found = await queries.latest(LatestRequest(FEED.identity, INCOMPLETE))
            if count <= 64:
                assert isinstance(found, LatestSelection)
                assert found.selection_status == "none" and found.highest_complete is None
                assert len(found.latest_issues) == 1
            else:
                assert found == ports.ServiceUnavailable("snapshot_selection_limit")
        finally:
            await database.close()

    asyncio.run(exercise())


def test_reopen_purged_identity_is_missing_and_never_complete(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "purged.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        resources = provider(database)
        result = await publish(resources, database)
        assert isinstance(result, ports.ResourceEffect)
        original_id = result.evidence[0].operation_id
        original = await resources.store.read_decision(original_id)
        assert isinstance(original, PublicationDecision)
        ref = original.result.requested
        await database.close()
        await purge_retained(
            path,
            ALICE.deployment_scope,
            PurgeSelection((ref,), ()),
            snapshot_codec=snapshot_codec(),
        )
        reopened = Database(path, ALICE.deployment_scope)
        try:
            resources = provider(reopened)
            queries = resources.store.queries(ALICE)
            assert isinstance(await queries.read(ref), ports.Missing)
            assert isinstance(
                await queries.read(replace(ref, content_digest="a" * 64)), ports.VersionConflict
            )
            latest = await queries.latest(LatestRequest(FEED.identity))
            assert (
                isinstance(latest, LatestSelection)
                and latest.content_availability is Availability.MISSING
            )
            assert await queries.latest(
                LatestRequest(FEED.identity, INCOMPLETE)
            ) == ports.ServiceUnavailable("snapshot_selection_content")
            duplicate = await publish(resources, reopened, 1, "1")
            assert isinstance(duplicate, ports.ResourceEffect)
            decided = await resources.store.read_decision(duplicate.evidence[0].operation_id)
            assert isinstance(decided, PublicationDecision)
            assert decided.result.status == "existing" and decided.result.summary is None
            assert isinstance(
                await resources.store.read_decision(original_id), ports.ServiceUnavailable
            )
        finally:
            await reopened.close()

    asyncio.run(exercise())


def test_candidate_owner_tampering_fails_closed(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "owner.sqlite3", ALICE.deployment_scope)
        try:
            resources = provider(database)
            effect = await publish(resources, database)
            assert isinstance(effect, ports.ResourceEffect)
            original = await resources.store.read_decision(effect.evidence[0].operation_id)
            assert isinstance(original, PublicationDecision)
            await database.transaction(
                lambda c: c.execute(update(commands).values(subject="mallory"))
            )
            assert isinstance(
                await resources.store.queries(ALICE).read(original.result.requested),
                ports.ServiceUnavailable,
            )
        finally:
            await database.close()

    asyncio.run(exercise())


def test_latest_anchor_excludes_arrival_during_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        from craftreport.adapters.storage.snapshots import SnapshotQueryAdapter

        database = Database(tmp_path / "anchor.sqlite3", ALICE.deployment_scope)
        try:
            resources = provider(database)
            await publish(resources, database)
            original = SnapshotQueryAdapter.read
            arrived = False

            async def read(
                query: SnapshotQueryAdapter, ref: object
            ) -> Snapshot | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
                nonlocal arrived
                from craftreport.data.values import SnapshotRef

                assert isinstance(ref, SnapshotRef)
                if not arrived:
                    arrived = True
                    await publish(resources, database, 2, "1")
                return await original(query, ref)

            monkeypatch.setattr(SnapshotQueryAdapter, "read", read)
            found = await resources.store.queries(ALICE).latest(
                LatestRequest(FEED.identity, InputRequirements((), ()))
            )
            assert isinstance(found, LatestSelection)
            assert found.highest_complete == found.latest_accepted
            assert found.latest_accepted.producer_version == 1
        finally:
            await database.close()

    asyncio.run(exercise())
