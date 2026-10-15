"""Real local-file transaction and lifetime acceptance for task 1.2."""

import asyncio
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from threading import Event, get_ident

import pytest
from sqlalchemy import Column, ForeignKey, Integer, LargeBinary, MetaData, Table, insert, select
from sqlalchemy.engine import Connection

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.schema import deployment


@pytest.fixture
def content() -> Table:
    metadata = MetaData()
    Table("parent", metadata, Column("id", Integer, primary_key=True))
    return Table(
        "content",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, ForeignKey("parent.id"), nullable=False),
        Column("payload", LargeBinary, nullable=False),
    )


def test_commit_rollback_and_exact_reopen(tmp_path: Path, content: Table) -> None:
    path = tmp_path / "retained.sqlite3"
    payload = (
        b'{"amount":"99999999999999999999.000000000000000001","version":"9223372036854775807"}'
    )

    async def exercise() -> str:
        database = Database(path, "deployment-a")
        await database.transaction(lambda connection: content.metadata.create_all(connection))

        def commit(connection: Connection) -> None:
            connection.execute(insert(content.metadata.tables["parent"]).values(id=1))
            connection.execute(insert(content).values(id=1, parent_id=1, payload=payload))

        await database.transaction(commit)
        epoch = database.deployment.epoch

        def rollback(connection: Connection) -> None:
            connection.execute(insert(content).values(id=2, parent_id=1, payload=b"discard"))
            raise RuntimeError("abort")

        with pytest.raises(RuntimeError, match="abort"):
            await database.transaction(rollback)
        with pytest.raises(StorageUnavailable):
            await database.transaction(
                lambda connection: connection.execute(
                    insert(content).values(id=3, parent_id=999, payload=b"invalid")
                )
            )
        assert await database.transaction(
            lambda connection: connection.execute(select(content.c.payload)).scalars().all()
        ) == [payload]
        await database.close()
        reopened = Database(path, "deployment-a")
        assert reopened.deployment.epoch == epoch
        assert reopened.deployment.retention_profile == "retain-all"
        assert (
            await reopened.transaction(
                lambda connection: connection.execute(select(content.c.payload)).scalar_one()
            )
            == payload
        )
        await reopened.close()
        return epoch

    assert asyncio.run(exercise())
    with sqlite3.connect(path) as independent:
        assert independent.execute("SELECT payload FROM content").fetchall() == [(payload,)]


def test_per_connection_configuration(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "settings.sqlite3", "deployment-a")

        def settings(connection: Connection) -> tuple[object, object, object, object]:
            raw = connection.connection.driver_connection
            assert isinstance(raw, sqlite3.Connection)
            return (
                raw.autocommit,
                raw.execute("PRAGMA foreign_keys").fetchone(),
                raw.execute("PRAGMA synchronous").fetchone(),
                raw.execute("PRAGMA journal_mode").fetchone(),
            )

        for _ in range(3):
            assert await database.transaction(settings) == (False, (1,), (2,), ("delete",))
        await database.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("kind", ["unknown", "corrupt", "other", "empty"])
def test_existing_incompatible_file_is_not_replaced(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "existing.sqlite3"
    if kind == "corrupt":
        path.write_bytes(b"retained bytes that are not a sqlite database")
    elif kind == "empty":
        path.touch()
    else:
        with sqlite3.connect(path) as connection:
            if kind == "unknown":
                connection.execute("CREATE TABLE deployment (schema_version INTEGER)")
                connection.execute("INSERT INTO deployment VALUES (99)")
            else:
                connection.execute("CREATE TABLE other (id INTEGER)")
    original = path.read_bytes()
    with pytest.raises(StorageUnavailable):
        Database(path, "deployment-a")
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "path", [Path("relative.sqlite3"), Path(":memory:"), Path("//server/share/database.sqlite3")]
)
def test_nonlocal_or_relative_paths_fail(path: Path) -> None:
    with pytest.raises(StorageUnavailable):
        Database(path, "deployment-a")


def test_wrong_deployment_and_closed_lifetime_fail(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "identity.sqlite3"
        database = Database(path, "deployment-a")
        await database.close()
        with pytest.raises(StorageUnavailable):
            await database.transaction(lambda connection: connection.execute(select(1)))
        with pytest.raises(StorageUnavailable):
            Database(path, "deployment-b")
        reopened = Database(path, "deployment-a")
        await reopened.close()

    asyncio.run(exercise())


def test_future_schema_version_rejects_and_releases_lock(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "future.sqlite3"
        database = Database(path, "deployment-a")
        await database.transaction(
            lambda connection: connection.execute(deployment.update().values(schema_version=99))
        )
        await database.close()
        original = path.read_bytes()
        with pytest.raises(StorageUnavailable):
            Database(path, "deployment-a")
        assert path.read_bytes() == original
        # Repair is operator/test-owned, proving the failed open relinquished
        # the OS lock without silently migrating or replacing retained state.
        with sqlite3.connect(path) as independent:
            independent.execute("UPDATE deployment SET schema_version = 1")
        reopened = Database(path, "deployment-a")
        await reopened.close()

    asyncio.run(exercise())


def test_actual_process_lock_and_release_after_exit(tmp_path: Path) -> None:
    path = tmp_path / "owned.sqlite3"
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
            assert ready.exists(), "Database owner did not reach readiness within 15 seconds"
            with pytest.raises(StorageUnavailable):
                Database(path, "deployment-a")
        finally:
            stdout, stderr = process.communicate("exit\n", timeout=15)
        assert process.returncode == 0, (stdout, stderr)
    database = Database(path, "deployment-a")
    asyncio.run(database.close())


def test_transactions_run_off_loop_and_serialize(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "workers.sqlite3", "deployment-a")
        loop_thread = get_ident()
        entered, release, second = Event(), Event(), Event()

        def first(connection: Connection) -> int:
            entered.set()
            assert release.wait(timeout=5)
            return get_ident()

        def next_transaction(connection: Connection) -> int:
            second.set()
            return get_ident()

        first_task = asyncio.create_task(database.transaction(first))
        assert await asyncio.to_thread(entered.wait, 5)
        next_task = asyncio.create_task(database.transaction(next_transaction))
        try:
            assert not await asyncio.to_thread(second.wait, 0.05)
        finally:
            release.set()
        assert await first_task != loop_thread
        assert await next_task != loop_thread
        await database.close()

    asyncio.run(exercise())


def test_ddl_rolls_back_with_the_transaction(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "ddl.sqlite3", "deployment-a")
        transient = Table("transient", MetaData(), Column("id", Integer, primary_key=True))

        def abort(connection: Connection) -> None:
            transient.create(connection)
            raise RuntimeError("abort DDL")

        with pytest.raises(RuntimeError, match="abort DDL"):
            await database.transaction(abort)
        await database.transaction(lambda connection: transient.create(connection))
        await database.close()

    asyncio.run(exercise())


def test_cancelled_awaiter_cannot_release_lock_before_worker_finishes(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "cancelled.sqlite3"
        database = Database(path, "deployment-a")
        entered, release = Event(), Event()

        def blocked(connection: Connection) -> None:
            entered.set()
            assert release.wait(timeout=5)

        transaction = asyncio.create_task(database.transaction(blocked))
        assert await asyncio.to_thread(entered.wait, 5)
        transaction.cancel()
        with pytest.raises(asyncio.CancelledError):
            await transaction
        closing = asyncio.create_task(database.close())
        try:
            await asyncio.sleep(0.05)
            assert not closing.done()
            with pytest.raises(StorageUnavailable):
                Database(path, "deployment-a")
        finally:
            release.set()
        await closing
        reopened = Database(path, "deployment-a")
        await reopened.close()

    asyncio.run(exercise())
