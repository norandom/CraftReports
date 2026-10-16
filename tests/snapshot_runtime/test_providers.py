"""File-backed guard, mutation and retained fact acceptance for task 3.2."""

import asyncio
import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update

from craftreport.adapters.canonical import CanonicalFingerprint, canonical_bytes
from craftreport.adapters.snapshot_wire import finalize_snapshot, publication_codec, snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import DurableResources
from craftreport.application import ports
from craftreport.contracts import (
    CommandIntent,
    EffectDisposition,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    ResourceRef,
    RetryKey,
)

FEED = ResourceRef("feed", "portfolio:one")
KEY = OperationKey("snapshot.publish", "1")
STAMP = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    value = Database(tmp_path / "effects.sqlite3", "deployment-a")
    yield value
    asyncio.run(value.close())


def provider(database: Database) -> DurableResources:
    fingerprint = CanonicalFingerprint()
    return DurableResources(database, snapshot_codec(), fingerprint, fingerprint.policy)


def test_original_snapshot_evidence_survives_feed_advance_and_detects_corruption(
    database: Database,
) -> None:
    from craftreport.adapters.storage.schema import snapshots
    from craftreport.contracts import Availability, StageState

    async def exercise() -> None:
        resources = provider(database)
        first = await publish(resources, database)
        second = await publish(resources, database, 2, "1")
        assert isinstance(first, ports.ResourceEffect) and isinstance(second, ports.ResourceEffect)
        reader = DurableEvidence(database)
        observed = await reader.inspect((*first.evidence, *second.evidence))
        assert all(
            item.availability is Availability.AVAILABLE and item.verification is StageState.PASSED
            for item in observed
        )
        await database.transaction(
            lambda c: c.execute(
                update(snapshots)
                .where(snapshots.c.producer_version == 1)
                .values(snapshot_bytes=b"bad")
            )
        )
        observed = await reader.inspect((*first.evidence, *second.evidence))
        assert observed[0].availability is Availability.UNAVAILABLE
        assert observed[1].availability is Availability.UNAVAILABLE
        assert all(item.availability is Availability.AVAILABLE for item in observed[2:])

    asyncio.run(exercise())


def producer(version: int = 1) -> JsonObject:
    return publication_codec().decode(
        {
            "schema_version": "1",
            "feed_id": FEED.identity,
            "producer_version": str(version),
            "datasets": [],
            "metrics": [],
            "observation_time": None,
            "generation_time": None,
        }
    )


async def admitted(
    database: Database,
    version: int = 1,
    expected: str = "absent",
    subject: str = "alice",
    operation: OperationKey = KEY,
    content_override: JsonObject | None = None,
) -> tuple[str, JsonObject]:
    content = producer(version) if content_override is None else content_override
    pins = (ExpectedVersion(FEED, expected),)
    finger = CanonicalFingerprint()
    intent = CommandIntent(
        RetryKey("deployment-a", subject, operation, uuid4().hex),
        finger(operation, content, (FEED,), pins),
        finger.policy,
        "correlation",
        (),
        (FEED,),
        pins,
    )
    result = await DurableJournal(database).admit(intent)
    assert isinstance(result, ports.Admitted)
    snapshot, _ = finalize_snapshot(content, STAMP, STAMP)
    return result.receipt.operation_id, {
        "operation_id": result.receipt.operation_id,
        "snapshot": snapshot_codec().encode(snapshot),
    }


async def publish(
    value: DurableResources,
    database: Database,
    version: int = 1,
    expected: str = "absent",
) -> ports.ResourceEffectResult:
    _, change = await admitted(database, version, expected)
    async with value.guard.acquire((ExpectedVersion(FEED, expected),)) as lease:
        return await value.apply(FEED, change, lease)


def test_atomic_effect_exact_readback_reopen(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        assert isinstance(await value.read(FEED), ports.Missing)
        result = await publish(value, database)
        assert isinstance(result, ports.ResourceEffect)
        assert result.effect is EffectDisposition.APPLIED
        assert result.versions == (ExpectedVersion(FEED, "1"),)
        assert result.evidence[0].scope == "snapshot_persisted"
        assert result.evidence[0].resource_versions == result.versions
        snapshot = await value.read(ResourceRef("snapshot", FEED.identity + ":1"))
        assert isinstance(snapshot, ports.ResourceSnapshot)
        assert snapshot.content["producer_version"] == "1"
        await database.close()
        with sqlite3.connect(database.path) as independent:
            rows = independent.execute(
                "SELECT operation_id, producer_bytes, snapshot_bytes FROM snapshots"
            ).fetchall()
            assert len(rows) == 1
            assert rows[0][0] == result.evidence[0].operation_id
            assert rows[0][1] == canonical_bytes(producer())
            assert rows[0][2] == canonical_bytes(snapshot.content)
            fact = independent.execute("SELECT fact_bytes FROM evidence").fetchone()
            assert fact is not None
            assert json.loads(fact[0])["operation_id"] == rows[0][0]
        reopened = Database(database.path, "deployment-a")
        try:
            assert await provider(reopened).read(snapshot.version.resource) == snapshot
        finally:
            await reopened.close()

    asyncio.run(exercise())


def test_same_version_stale_conflict_and_original_operation(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        first = await publish(value, database, 3)
        assert isinstance(first, ports.ResourceEffect)
        same = await publish(value, database, 3, "1")
        assert isinstance(same, ports.ResourceEffect)
        assert same.effect is EffectDisposition.NONE
        assert tuple(ref.scope for ref in same.evidence) == ("publication_decided",)
        stale = await publish(value, database, 2, "1")
        assert isinstance(stale, ports.ResourceEffect) and stale.effect is EffectDisposition.NONE
        assert isinstance(await publish(value, database, 4, "1"), ports.ResourceEffect)
        latest = await value.read(FEED)
        assert isinstance(latest, ports.ResourceSnapshot)
        assert latest.version.version == "2" and latest.content["high_water"] == "4"
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (2,)
            assert independent.execute("SELECT count(*) FROM evidence").fetchone() == (6,)

    asyncio.run(exercise())


def test_concurrent_cas_winner_and_cancelled_waiter(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        pins = (ExpectedVersion(FEED, "absent"),)
        async with value.guard.acquire(pins):
            waiter = asyncio.create_task(publish(value, database))
            await asyncio.sleep(0.03)
            waiter.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiter
        results = await asyncio.gather(
            publish(value, database),
            publish(value, database),
            return_exceptions=True,
        )
        assert sum(isinstance(item, ports.ResourceEffect) for item in results) == 1
        assert sum(isinstance(item, ports.GuardAcquisitionError) for item in results) == 1
        async with value.guard.acquire((ExpectedVersion(FEED, "1"),)) as lease:
            assert isinstance(await lease.assert_current(), ports.GuardCurrent)

    asyncio.run(exercise())


def test_sorted_locks_foreign_expired_and_undeclared_leases(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        pins = (
            ExpectedVersion(FEED, "absent"),
            ExpectedVersion(ResourceRef("feed", "z"), "absent"),
        )

        async def acquire(order: tuple[ExpectedVersion, ...]) -> None:
            async with value.guard.acquire(order) as lease:
                assert isinstance(await lease.assert_current(), ports.GuardCurrent)
                await asyncio.sleep(0)

        await asyncio.wait_for(asyncio.gather(acquire(pins), acquire(pins[::-1])), 1)
        _, change = await admitted(database)
        async with value.guard.acquire(pins[:1]) as expired:
            pass
        assert isinstance(await expired.assert_current(), ports.GuardLost)
        assert isinstance(await value.apply(FEED, change, expired), ports.GuardLost)
        other = provider(database)
        async with other.guard.acquire(pins[:1]) as foreign:
            assert isinstance(await value.apply(FEED, change, foreign), ports.GuardLost)
        async with value.guard.acquire(pins[1:]) as unrelated:
            assert isinstance(await value.apply(FEED, change, unrelated), ports.GuardLost)

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["extra", "missing", "operation", "subject", "payload"])
def test_unknown_or_unowned_changes_fail_closed(database: Database, damage: str) -> None:
    async def exercise() -> None:
        value = provider(database)
        assert isinstance(await publish(value, database), ports.ResourceEffect)
        _, original = await admitted(
            database,
            2,
            "1",
            "bob" if damage == "subject" else "alice",
            OperationKey("other", "1") if damage == "operation" else KEY,
        )
        change = dict(original)
        if damage == "extra":
            change["subject"] = "alice"
        if damage == "missing":
            change.pop("operation_id")
        if damage == "payload":
            snapshot, _ = finalize_snapshot(producer(3), STAMP, STAMP)
            change["snapshot"] = snapshot_codec().encode(snapshot)
        async with value.guard.acquire((ExpectedVersion(FEED, "1"),)) as lease:
            assert isinstance(await value.apply(FEED, change, lease), ports.ServiceUnavailable)
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (1,)

    asyncio.run(exercise())


def test_authoritative_version_loss_and_closed_database(database: Database) -> None:
    async def exercise() -> None:
        from craftreport.adapters.storage.schema import feeds

        value = provider(database)
        await publish(value, database)
        _, change = await admitted(database, 2, "1")
        async with value.guard.acquire((ExpectedVersion(FEED, "1"),)) as lease:
            await database.transaction(
                lambda connection: connection.execute(update(feeds).values(revision=2))
            )
            assert isinstance(await lease.assert_current(), ports.VersionConflict)
            assert isinstance(await value.apply(FEED, change, lease), ports.VersionConflict)
        await database.close()
        assert isinstance(await value.read(FEED), ports.ServiceUnavailable)
        with pytest.raises(ports.GuardAcquisitionError):
            async with value.guard.acquire((ExpectedVersion(FEED, "2"),)):
                pytest.fail("closed storage granted a lease")

    asyncio.run(exercise())


def test_same_version_different_content_conflicts(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        await publish(value, database)
        alternate = dict(producer())
        alternate["generation_time"] = "2026-10-15T11:00:00.000000Z"
        _, change = await admitted(database, 1, "1", content_override=alternate)
        async with value.guard.acquire((ExpectedVersion(FEED, "1"),)) as lease:
            result = await value.apply(FEED, change, lease)
            assert (
                isinstance(result, ports.ResourceEffect) and result.effect is EffectDisposition.NONE
            )
            from craftreport.runtime.publication import PublicationDecision

            decision = await value.store.read_decision(result.evidence[0].operation_id)
            assert isinstance(decision, PublicationDecision)
            assert decision.result.status == "version_conflict"
            assert decision.result.requested != decision.result.retained
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (1,)

    asyncio.run(exercise())


@pytest.mark.parametrize("phase", ["before_worker", "after_commit"])
def test_cancellation_cutpoints_retain_only_real_commits(
    database: Database,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    from collections.abc import Callable

    from sqlalchemy.engine import Connection

    async def exercise() -> None:
        value = provider(database)
        _, change = await admitted(database)
        reached, release = asyncio.Event(), asyncio.Event()
        transaction = database.transaction
        calls = 0

        async def timed[T](action: Callable[[Connection], T]) -> T:
            nonlocal calls
            calls += 1
            # acquire read, assert_current read, then atomic effect callback.
            if calls == 3 and phase == "before_worker":
                reached.set()
                await release.wait()
            result = await transaction(action)
            if calls == 3 and phase == "after_commit":
                reached.set()
                await release.wait()
            return result

        monkeypatch.setattr(database, "transaction", timed)

        async def run() -> ports.ResourceEffectResult:
            async with value.guard.acquire((ExpectedVersion(FEED, "absent"),)) as lease:
                return await value.apply(FEED, change, lease)

        task = asyncio.create_task(run())
        await asyncio.wait_for(reached.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        monkeypatch.setattr(database, "transaction", transaction)
        expected = "1" if phase == "after_commit" else "absent"
        async with value.guard.acquire((ExpectedVersion(FEED, expected),)) as lease:
            assert isinstance(await lease.assert_current(), ports.GuardCurrent)
        with sqlite3.connect(database.path) as independent:
            count = 1 if phase == "after_commit" else 0
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (count,)
            assert independent.execute("SELECT count(*) FROM evidence").fetchone() == (2 * count,)

    asyncio.run(exercise())


def test_timeout_releases_earlier_locks(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        value.guard.timeout = 0.02
        first, second = (
            ExpectedVersion(ResourceRef("feed", "a"), "absent"),
            ExpectedVersion(FEED, "absent"),
        )
        async with value.guard.acquire((second,)):

            async def blocked() -> None:
                with pytest.raises(ports.GuardAcquisitionError) as failed:
                    async with value.guard.acquire((first, second)):
                        pytest.fail("contended lease granted")
                assert isinstance(failed.value.reason, ports.ServiceUnavailable)

            await asyncio.create_task(blocked())
            async with value.guard.acquire((first,)) as lease:
                assert isinstance(await lease.assert_current(), ports.GuardCurrent)
        async with value.guard.acquire((first, second)):
            pass

    asyncio.run(exercise())


@pytest.mark.parametrize("field", ["producer_bytes", "snapshot_bytes", "content_digest"])
def test_corrupt_content_is_unavailable(database: Database, field: str) -> None:
    from craftreport.adapters.storage.schema import snapshots

    async def exercise() -> None:
        value = provider(database)
        await publish(value, database)
        await database.transaction(
            lambda connection: connection.execute(
                update(snapshots).values({field: "bad" if field == "content_digest" else b"bad"})
            )
        )
        assert isinstance(await value.read(FEED), ports.ServiceUnavailable)
        assert isinstance(
            await value.read(ResourceRef("snapshot", FEED.identity + ":1")),
            ports.ServiceUnavailable,
        )

    asyncio.run(exercise())


def test_v2_migration_preserves_journal_bytes_and_current_schema_opens_without_writes(
    database: Database,
) -> None:
    async def exercise() -> None:
        operation_id, _ = await admitted(database)
        before_receipt = await DurableJournal(database).read(operation_id)
        epoch = database.deployment.epoch
        await database.close()
        with sqlite3.connect(database.path) as independent:
            before = independent.execute("SELECT * FROM commands").fetchall()
            history = independent.execute("SELECT * FROM observations").fetchall()
            for table in (
                "runs",
                "bindings",
                "handoffs",
                "results",
                "evidence",
                "snapshots",
                "feeds",
            ):
                independent.execute("DROP TABLE " + table)
            independent.execute("UPDATE deployment SET schema_version=2")
        migrated = Database(database.path, "deployment-a")
        assert migrated.deployment.epoch == epoch
        assert await DurableJournal(migrated).read(operation_id) == before_receipt
        await migrated.close()
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT * FROM commands").fetchall() == before
            assert independent.execute("SELECT * FROM observations").fetchall() == history
        original_bytes = database.path.read_bytes()
        reopened = Database(database.path, "deployment-a")
        await reopened.close()
        assert database.path.read_bytes() == original_bytes

    asyncio.run(exercise())


def test_atomic_fact_failure_rolls_back_feed_and_snapshot(database: Database) -> None:
    from sqlalchemy import event
    from sqlalchemy.engine import Connection, Engine

    def fail(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("INSERT INTO evidence"):
            raise ValueError("fact retention failed")

    async def exercise() -> None:
        value = provider(database)
        event.listen(Engine, "after_cursor_execute", fail)
        try:
            assert isinstance(await publish(value, database), ports.ServiceUnavailable)
        finally:
            event.remove(Engine, "after_cursor_execute", fail)
        assert isinstance(await value.read(FEED), ports.Missing)
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (0,)
            assert independent.execute("SELECT count(*) FROM evidence").fetchone() == (0,)
        assert isinstance(await publish(value, database), ports.ResourceEffect)

    asyncio.run(exercise())


def test_guard_does_not_reclassify_handler_timeout(database: Database) -> None:
    async def exercise() -> None:
        value = provider(database)
        with pytest.raises(TimeoutError, match="handler"):
            async with value.guard.acquire((ExpectedVersion(FEED, "absent"),)):
                raise TimeoutError("handler")

    asyncio.run(exercise())


def test_invalid_feed_revision_is_unavailable(database: Database) -> None:
    from craftreport.adapters.storage.schema import feeds

    async def exercise() -> None:
        value = provider(database)
        await publish(value, database)
        await database.transaction(
            lambda connection: connection.execute(update(feeds).values(revision="corrupt"))
        )
        assert isinstance(await value.read(FEED), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_cancelled_lease_blocks_queued_worker_effect(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    from sqlalchemy.engine import Connection

    from craftreport.adapters.storage.guard import DurableLease

    async def exercise() -> None:
        value = provider(database)
        _, change = await admitted(database)
        entered, release = Event(), Event()
        original = DurableLease.check
        calls = 0

        def check(lease: DurableLease, connection: Connection) -> ports.GuardCheck:
            nonlocal calls
            calls += 1
            if calls == 3:
                entered.set()
                assert release.wait(3)
            return original(lease, connection)

        monkeypatch.setattr(DurableLease, "check", check)

        async def run() -> ports.ResourceEffectResult:
            async with value.guard.acquire((ExpectedVersion(FEED, "absent"),)) as lease:
                return await value.apply(FEED, change, lease)

        task = asyncio.create_task(run())
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        assert isinstance(await value.read(FEED), ports.Missing)
        with sqlite3.connect(database.path) as independent:
            assert independent.execute("SELECT count(*) FROM snapshots").fetchone() == (0,)

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["partial", "extra", "cascade"])
def test_v3_unknown_resource_schema_rejects_unchanged(database: Database, damage: str) -> None:
    from craftreport.adapters.storage.database import StorageUnavailable

    asyncio.run(database.close())
    with sqlite3.connect(database.path) as independent:
        if damage == "partial":
            independent.execute("DROP TABLE evidence")
        elif damage == "extra":
            independent.execute("ALTER TABLE feeds ADD COLUMN unexpected VARCHAR")
        else:
            ddl = independent.execute(
                "SELECT sql FROM sqlite_schema WHERE name='snapshots'"
            ).fetchone()
            assert ddl is not None
            independent.execute("DROP TABLE snapshots")
            independent.execute(
                ddl[0].replace(
                    "REFERENCES commands (operation_id)",
                    "REFERENCES commands (operation_id) ON DELETE CASCADE",
                )
            )
        before = "\n".join(independent.iterdump())
    with pytest.raises(StorageUnavailable):
        Database(database.path, "deployment-a")
    with sqlite3.connect(database.path) as independent:
        assert "\n".join(independent.iterdump()) == before


def test_fabricated_lease_never_authorizes_effect(database: Database) -> None:
    from craftreport.adapters.storage.guard import DurableLease

    async def exercise() -> None:
        value = provider(database)
        _, change = await admitted(database)
        forged = DurableLease(value.guard, (ExpectedVersion(FEED, "absent"),))
        assert isinstance(await value.apply(FEED, change, forged), ports.GuardLost)
        assert isinstance(await value.read(FEED), ports.Missing)

    asyncio.run(exercise())


@pytest.mark.parametrize("bypass", [False, True])
def test_issued_lease_cannot_retarget_locked_resource(database: Database, bypass: bool) -> None:
    from dataclasses import FrozenInstanceError

    async def exercise() -> None:
        value = provider(database)
        _, change = await admitted(database)
        pins = (ExpectedVersion(ResourceRef("feed", "unrelated"), "absent"),)
        async with value.guard.acquire(pins) as lease:
            requested = (ExpectedVersion(FEED, "absent"),)
            if bypass:
                object.__setattr__(lease, "authoritative_versions", requested)
            else:
                with pytest.raises((FrozenInstanceError, AttributeError)):
                    setattr(lease, "authoritative_versions", requested)
            assert isinstance(await value.apply(FEED, change, lease), ports.GuardLost)
        assert isinstance(await value.read(FEED), ports.Missing)

    asyncio.run(exercise())


@pytest.mark.parametrize("bypass", [False, True])
def test_issued_lease_cannot_transfer_task_authority(database: Database, bypass: bool) -> None:
    from dataclasses import FrozenInstanceError

    async def exercise() -> None:
        value = provider(database)
        _, change = await admitted(database)
        async with value.guard.acquire((ExpectedVersion(FEED, "absent"),)) as lease:

            async def transfer() -> None:
                if bypass:
                    object.__setattr__(lease, "task", asyncio.current_task())
                else:
                    with pytest.raises((FrozenInstanceError, AttributeError)):
                        setattr(lease, "task", asyncio.current_task())
                assert isinstance(await value.apply(FEED, change, lease), ports.GuardLost)

            await asyncio.create_task(transfer())
        assert isinstance(await value.read(FEED), ports.Missing)

    asyncio.run(exercise())
