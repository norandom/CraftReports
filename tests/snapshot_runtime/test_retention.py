"""Offline bounded content removal keeps identities and truthful current reads."""

import asyncio
import hashlib
import os
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import event, select
from sqlalchemy.engine import Connection, Engine
from test_providers import FEED, admitted, producer, provider, publish
from test_services import ALICE

from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.adapters.storage import providers, retention, schema, serialization
from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    ExpectedVersion,
    Principal,
    ResourceRef,
)
from craftreport.data.values import SnapshotRef


async def fixture(path: Path) -> tuple[SnapshotRef, retention.ResultContentRef, str]:
    database = Database(path, ALICE.deployment_scope)
    target = provider(database)
    effect = await publish(target, database)
    assert isinstance(effect, ports.ResourceEffect)
    resource = await target.read(ResourceRef("snapshot", "portfolio:one:1"))
    assert isinstance(resource, ports.ResourceSnapshot)
    reference = SnapshotRef("portfolio:one", 1, resource.version.version)
    operation = effect.evidence[0].operation_id
    result = await DurableResults(database).write(ALICE, operation, {"retained": "original"})
    epoch = database.deployment.epoch
    await database.close()
    return reference, retention.ResultContentRef(operation, result), epoch


def retained(path: Path) -> dict[str, list[tuple[object, ...]]]:
    with sqlite3.connect(path) as connection:
        return {
            name: connection.execute("SELECT * FROM " + name).fetchall()
            for name in (
                "deployment",
                "commands",
                "observations",
                "feeds",
                "snapshots",
                "results",
                "evidence",
            )
        }


def test_offline_purge_changes_only_selected_payloads_and_reopens_truthfully(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        path = tmp_path / "purge.sqlite3"
        snapshot, result, epoch = await fixture(path)
        before = retained(path)
        selection = retention.PurgeSelection((snapshot,), (result,))
        report = await retention.purge_retained(
            path, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
        )
        assert report == retention.PurgeReport(epoch, (snapshot,), (result,))
        after = retained(path)
        for name in ("deployment", "commands", "observations", "feeds", "evidence"):
            assert after[name] == before[name]
        assert after["snapshots"][0][:4] == before["snapshots"][0][:4]
        payload = after["snapshots"][0][4]
        assert isinstance(payload, bytes) and payload.startswith(serialization.PURGED)
        assert after["snapshots"][0][4] == after["snapshots"][0][5]
        assert after["results"][0][:-2] == before["results"][0][:-2]
        again = await retention.purge_retained(
            path, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
        )
        assert again == retention.PurgeReport(epoch, (), ())
        database = Database(path, ALICE.deployment_scope)
        target = provider(database)
        assert isinstance(
            await target.read(ResourceRef("snapshot", "portfolio:one:1")), ports.Missing
        )
        feed = await target.read(ResourceRef("feed", "portfolio:one"))
        assert isinstance(feed, ports.ResourceSnapshot) and feed.content["high_water"] == "1"
        assert (
            await DurableResults(database).read(ALICE, result.operation_id, result.opaque_reference)
        ).availability is Availability.MISSING
        facts = await database.transaction(
            lambda c: c.execute(select(schema.evidence)).mappings().all()
        )
        ref = serialization.decode_evidence(
            facts[0]["reference_bytes"], facts[0]["reference_digest"]
        )
        assert (await DurableEvidence(database).inspect((ref,)))[
            0
        ].availability is Availability.MISSING
        assert (
            await providers.DurableHealth(database, target, {}).check(
                ("resources", "results", "evidence")
            )
            is None
        )
        await database.close()

    asyncio.run(exercise())


def test_active_host_missing_wrong_deployment_and_older_schema_fail_unchanged(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        path = tmp_path / "owned.sqlite3"
        snapshot, _, _ = await fixture(path)
        selection = retention.PurgeSelection((snapshot,), ())
        database = Database(path, ALICE.deployment_scope)
        before = path.read_bytes()
        assert isinstance(
            await retention.purge_retained(
                path, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
            ),
            ports.ServiceUnavailable,
        )
        assert path.read_bytes() == before
        await database.close()
        assert isinstance(
            await retention.purge_retained(
                path, "foreign", selection, snapshot_codec=snapshot_codec()
            ),
            ports.ServiceUnavailable,
        )
        absent = tmp_path / "absent.sqlite3"
        assert isinstance(
            await retention.purge_retained(
                absent, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
            ),
            ports.ServiceUnavailable,
        )
        assert not absent.exists()
        with sqlite3.connect(path) as connection:
            connection.execute("DROP TABLE handoffs")
            connection.execute("UPDATE deployment SET schema_version=4")
        before = path.read_bytes()
        assert isinstance(
            await retention.purge_retained(
                path, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
            ),
            ports.ServiceUnavailable,
        )
        assert path.read_bytes() == before

    asyncio.run(exercise())


def test_invalid_batch_and_injected_update_failure_roll_back(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "rollback.sqlite3"
        snapshot, result, _ = await fixture(path)
        before = retained(path)
        absent = SnapshotRef(snapshot.feed_id, 99, "a" * 64)
        with pytest.raises(retention.InvalidPurgeSelection):
            await retention.purge_retained(
                path,
                ALICE.deployment_scope,
                retention.PurgeSelection((snapshot, absent), ()),
                snapshot_codec=snapshot_codec(),
            )
        assert retained(path) == before

        def fail(
            c: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if statement.startswith("UPDATE snapshots SET"):
                raise ValueError("after first purge update")

        event.listen(Engine, "after_cursor_execute", fail)
        try:
            outcome = await retention.purge_retained(
                path,
                ALICE.deployment_scope,
                retention.PurgeSelection((snapshot,), (result,)),
                snapshot_codec=snapshot_codec(),
            )
            assert isinstance(outcome, ports.ServiceUnavailable)
        finally:
            event.remove(Engine, "after_cursor_execute", fail)
        assert retained(path) == before

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["checksum", "one_sided", "metadata", "original_digest"])
def test_corrupt_tombstones_are_unavailable_not_missing(tmp_path: Path, damage: str) -> None:
    async def exercise() -> None:
        path = tmp_path / "damage.sqlite3"
        snapshot, _, _ = await fixture(path)
        await retention.purge_retained(
            path,
            ALICE.deployment_scope,
            retention.PurgeSelection((snapshot,), ()),
            snapshot_codec=snapshot_codec(),
        )
        with sqlite3.connect(path) as connection:
            payload, _ = connection.execute(
                "SELECT snapshot_bytes,snapshot_digest FROM snapshots"
            ).fetchone()
            if damage == "one_sided":
                connection.execute("UPDATE snapshots SET producer_bytes=?", (b"{}",))
            elif damage == "checksum":
                connection.execute("UPDATE snapshots SET snapshot_digest=?", ("a" * 64,))
            elif damage == "original_digest":
                body = serialization.decode_object(
                    payload[len(serialization.PURGED) :],
                    hashlib.sha256(payload[len(serialization.PURGED) :]).hexdigest(),
                )
                original = body["snapshot_digest"]
                assert isinstance(original, str)
                changed = payload.replace(original.encode(), b"a" * 64)
                assert changed != payload
                connection.execute(
                    "UPDATE snapshots SET producer_bytes=?,snapshot_bytes=?", (changed, changed)
                )
            else:
                changed = payload.replace(b'"subject":"alice"', b'"subject":"foreign"')
                assert changed != payload
                connection.execute(
                    "UPDATE snapshots SET producer_bytes=?,snapshot_bytes=?,snapshot_digest=?",
                    (changed, changed, hashlib.sha256(changed).hexdigest()),
                )
        database = Database(path, ALICE.deployment_scope)
        assert isinstance(
            await provider(database).read(ResourceRef("snapshot", "portfolio:one:1")),
            ports.ServiceUnavailable,
        )
        assert isinstance(
            await providers.DurableHealth(database, provider(database), {}).check(("resources",)),
            ports.ServiceUnavailable,
        )
        await database.close()

    asyncio.run(exercise())


def test_oversized_payload_is_rejected_before_blob_select(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "oversize.sqlite3"
        snapshot, _, _ = await fixture(path)
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE snapshots SET snapshot_bytes=zeroblob(1048577)")
        statements: list[str] = []

        def record(
            c: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(Engine, "before_cursor_execute", record)
        try:
            assert isinstance(
                await retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((snapshot,), ()),
                    snapshot_codec=snapshot_codec(),
                ),
                ports.ServiceUnavailable,
            )
        finally:
            event.remove(Engine, "before_cursor_execute", record)
        reads = [s for s in statements if "FROM snapshots" in s]
        assert reads and all("length(snapshots.snapshot_bytes)" in s for s in reads)

    asyncio.run(exercise())


def test_cancelled_purge_retains_lock_until_worker_and_close_finish(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "cancel.sqlite3"
        snapshot, _, _ = await fixture(path)
        entered, release = Event(), Event()

        def block(
            c: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            if statement.startswith("UPDATE snapshots SET"):
                entered.set()
                assert release.wait(5)

        event.listen(Engine, "after_cursor_execute", block)
        try:
            task = asyncio.create_task(
                retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((snapshot,), ()),
                    snapshot_codec=snapshot_codec(),
                )
            )
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            assert not task.done()
            with pytest.raises(StorageUnavailable):
                Database(path, ALICE.deployment_scope)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
            event.remove(Engine, "after_cursor_execute", block)
        database = Database(path, ALICE.deployment_scope)
        assert isinstance(
            await provider(database).read(ResourceRef("snapshot", "portfolio:one:1")), ports.Missing
        )
        await database.close()

    asyncio.run(exercise())


def test_close_failure_is_unavailable_after_actual_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        path = tmp_path / "close-failure.sqlite3"
        snapshot, _, _ = await fixture(path)
        original = Database.close

        async def fail(database: Database) -> None:
            await original(database)
            raise StorageUnavailable("lost close acknowledgement")

        with monkeypatch.context() as patch:
            patch.setattr(Database, "close", fail)
            assert isinstance(
                await retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((snapshot,), ()),
                    snapshot_codec=snapshot_codec(),
                ),
                ports.ServiceUnavailable,
            )
        database = Database(path, ALICE.deployment_scope)
        assert isinstance(
            await provider(database).read(ResourceRef("snapshot", "portfolio:one:1")), ports.Missing
        )
        await database.close()

    asyncio.run(exercise())


def test_cancel_during_close_drains_then_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        path = tmp_path / "cancel-close.sqlite3"
        snapshot, _, _ = await fixture(path)
        original = Database.close
        entered, release = asyncio.Event(), asyncio.Event()

        async def block(database: Database) -> None:
            entered.set()
            await release.wait()
            await original(database)

        with monkeypatch.context() as patch:
            patch.setattr(Database, "close", block)
            task = asyncio.create_task(
                retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((snapshot,), ()),
                    snapshot_codec=snapshot_codec(),
                )
            )
            await entered.wait()
            task.cancel()
            await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(StorageUnavailable):
                Database(path, ALICE.deployment_scope)
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        database = Database(path, ALICE.deployment_scope)
        await database.close()

    asyncio.run(exercise())


def test_purged_identity_cannot_rehydrate_or_fall_back(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "publication.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        target = provider(database)
        await publish(target, database)
        applied = await publish(target, database, 3, "1")
        assert isinstance(applied, ports.ResourceEffect)
        original = await database.transaction(
            lambda c: DurableJournal(database).retained(
                c,
                c.execute(
                    select(schema.commands).where(
                        schema.commands.c.operation_id == applied.evidence[0].operation_id
                    )
                )
                .mappings()
                .one(),
            )
        )
        assert isinstance(original, ports.RetainedCommand)
        content = await target.read(ResourceRef("snapshot", "portfolio:one:3"))
        assert isinstance(content, ports.ResourceSnapshot)
        snapshot = SnapshotRef(FEED.identity, 3, content.version.version)
        await database.close()
        await retention.purge_retained(
            path,
            ALICE.deployment_scope,
            retention.PurgeSelection((snapshot,), ()),
            snapshot_codec=snapshot_codec(),
        )
        database = Database(path, ALICE.deployment_scope)
        target = provider(database)
        retried = await DurableJournal(database).admit(original.intent)
        assert isinstance(retried, ports.Existing) and retried.command == original
        same = await publish(target, database, 3, "2")
        assert isinstance(same, ports.ResourceEffect) and same.effect is EffectDisposition.NONE
        assert isinstance(
            await target.read(ResourceRef("snapshot", "portfolio:one:3")), ports.Missing
        )
        assert isinstance(await publish(target, database, 2, "2"), ports.VersionConflict)
        changed = {**producer(3), "observation_time": "2026-10-15T11:00:00.000000Z"}
        _, change = await admitted(database, 3, "2", content_override=changed)
        async with target.guard.acquire((ExpectedVersion(FEED, "2"),)) as lease:
            assert isinstance(await target.apply(FEED, change, lease), ports.VersionConflict)
        assert isinstance(await publish(target, database, 4, "2"), ports.ResourceEffect)
        await database.close()

    asyncio.run(exercise())


def test_result_purge_protects_owner_staged_link_and_immutable_write(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "results.sqlite3"
        _, linked, epoch = await fixture(path)
        database = Database(path, ALICE.deployment_scope)
        staged = await DurableResults(database).write(ALICE, "staged-query", {"staged": True})
        await database.close()
        selected = retention.ResultContentRef("staged-query", staged)
        assert await retention.purge_retained(
            path,
            ALICE.deployment_scope,
            retention.PurgeSelection((), (linked, selected)),
            snapshot_codec=snapshot_codec(),
        ) == retention.PurgeReport(epoch, (), (linked, selected))
        database = Database(path, ALICE.deployment_scope)
        results = DurableResults(database)
        assert (
            await results.read(ALICE, "staged-query", staged)
        ).availability is Availability.MISSING
        assert (
            await results.read(
                Principal(ALICE.deployment_scope, "other", frozenset()), "staged-query", staged
            )
        ).availability is Availability.INACCESSIBLE
        with pytest.raises(ports.ServiceUnavailableError):
            await results.write(ALICE, linked.operation_id, {"retained": "original"})
        with pytest.raises(ports.ServiceUnavailableError):
            await results.write(ALICE, "staged-query", {"staged": True})
        await database.close()
        with sqlite3.connect(path) as connection:
            assert connection.execute(
                "SELECT command_operation_id FROM results WHERE identity=?", (staged,)
            ).fetchone() == (None,)

    asyncio.run(exercise())


def test_uncertain_commit_requires_reopen_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        path = tmp_path / "lost-ack.sqlite3"
        snapshot, _, _ = await fixture(path)
        original = Database.transaction

        async def lose_ack[T](database: Database, action: Callable[[Connection], T]) -> T:
            await original(database, action)
            raise StorageUnavailable("lost transaction acknowledgement")

        with monkeypatch.context() as patch:
            patch.setattr(Database, "transaction", lose_ack)
            assert isinstance(
                await retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((snapshot,), ()),
                    snapshot_codec=snapshot_codec(),
                ),
                ports.ServiceUnavailable,
            )
        database = Database(path, ALICE.deployment_scope)
        assert isinstance(
            await provider(database).read(ResourceRef("snapshot", "portfolio:one:1")), ports.Missing
        )
        await database.close()

    asyncio.run(exercise())


def test_competing_host_process_rejects_purge_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "process.sqlite3"
    snapshot, _, _ = asyncio.run(fixture(path))
    before = path.read_bytes()
    ready = tmp_path / "ready"
    child = Path(__file__).with_name("database_owner.py")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with subprocess.Popen(
        [sys.executable, str(child), str(path), str(ready)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=flags,
    ) as process:
        try:
            deadline = time.monotonic() + 15
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            assert ready.exists()
            assert isinstance(
                asyncio.run(
                    retention.purge_retained(
                        path,
                        ALICE.deployment_scope,
                        retention.PurgeSelection((snapshot,), ()),
                        snapshot_codec=snapshot_codec(),
                    )
                ),
                ports.ServiceUnavailable,
            )
            assert path.read_bytes() == before
        finally:
            stdout, stderr = process.communicate("exit\n", timeout=15)
        assert process.returncode == 0, (stdout, stderr)


def test_transplanted_result_envelope_is_unavailable(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "transplant.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        results = DurableResults(database)
        first = await results.write(ALICE, "first", {"secret": "one"})
        second = await results.write(ALICE, "second", {"secret": "two"})
        await database.close()
        await retention.purge_retained(
            path,
            ALICE.deployment_scope,
            retention.PurgeSelection((), (retention.ResultContentRef("first", first),)),
            snapshot_codec=snapshot_codec(),
        )
        with sqlite3.connect(path) as connection:
            payload, digest = connection.execute(
                "SELECT result_bytes,result_digest FROM results WHERE identity=?", (first,)
            ).fetchone()
            connection.execute(
                "UPDATE results SET result_bytes=?,result_digest=? WHERE identity=?",
                (payload, digest, second),
            )
        before = retained(path)
        outcome = await retention.purge_retained(
            path,
            ALICE.deployment_scope,
            retention.PurgeSelection((), (retention.ResultContentRef("second", second),)),
            snapshot_codec=snapshot_codec(),
        )
        assert isinstance(outcome, ports.ServiceUnavailable) and retained(path) == before
        database = Database(path, ALICE.deployment_scope)
        assert (
            await DurableResults(database).read(ALICE, "second", second)
        ).availability is Availability.UNAVAILABLE
        await database.close()

    asyncio.run(exercise())


def test_selection_bound_and_aggregate_lengths_precede_materialization(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "aggregate.sqlite3"
        refs = tuple(retention.ResultContentRef(str(i), str(i)) for i in range(33))
        for selection in (
            retention.PurgeSelection(),
            retention.PurgeSelection((), refs),
            retention.PurgeSelection((), (refs[0], refs[0])),
        ):
            with pytest.raises(retention.InvalidPurgeSelection):
                await retention.purge_retained(
                    path, ALICE.deployment_scope, selection, snapshot_codec=snapshot_codec()
                )
            assert not path.exists()
        database = Database(path, ALICE.deployment_scope)
        actual = tuple(
            [
                retention.ResultContentRef(
                    str(i), await DurableResults(database).write(ALICE, str(i), {})
                )
                for i in range(9)
            ]
        )
        await database.close()
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE results SET result_bytes=zeroblob(8388608)")
        statements: list[str] = []

        def record(
            c: Connection,
            cursor: object,
            statement: str,
            parameters: object,
            context: object,
            executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(Engine, "before_cursor_execute", record)
        try:
            with pytest.raises(retention.InvalidPurgeSelection, match="64MiB"):
                await retention.purge_retained(
                    path,
                    ALICE.deployment_scope,
                    retention.PurgeSelection((), actual),
                    snapshot_codec=snapshot_codec(),
                )
        finally:
            event.remove(Engine, "before_cursor_execute", record)
        reads = [s for s in statements if "FROM results" in s]
        assert len(reads) == 9 and all("length(results.result_bytes)" in s for s in reads)

    asyncio.run(exercise())


def test_invalid_snapshot_contract_is_not_purged(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "invalid-contract.sqlite3"
        snapshot, _, _ = await fixture(path)
        with sqlite3.connect(path) as connection:
            payload, digest = connection.execute(
                "SELECT snapshot_bytes,snapshot_digest FROM snapshots"
            ).fetchone()
            value = serialization.decode_object(payload, digest)
            changed, digest = serialization.encode_object({**value, "received_at": "invalid"})
            connection.execute(
                "UPDATE snapshots SET snapshot_bytes=?,snapshot_digest=?", (changed, digest)
            )
        before = retained(path)
        assert isinstance(
            await retention.purge_retained(
                path,
                ALICE.deployment_scope,
                retention.PurgeSelection((snapshot,), ()),
                snapshot_codec=snapshot_codec(),
            ),
            ports.ServiceUnavailable,
        )
        assert retained(path) == before

    asyncio.run(exercise())


def test_offline_operator_requires_explicit_snapshot_codec(tmp_path: Path) -> None:
    path = tmp_path / "no-codec.sqlite3"
    operator = getattr(retention, "purge_retained")
    with pytest.raises(TypeError, match="snapshot_codec"):
        asyncio.run(operator(path, ALICE.deployment_scope, retention.PurgeSelection()))
    assert not path.exists() and not path.with_suffix(".sqlite3.lock").exists()
