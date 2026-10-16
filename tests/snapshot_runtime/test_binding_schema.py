"""Real-file v6 migration and fail-closed schema acceptance."""

import asyncio
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, insert
from sqlalchemy.engine import Connection, Engine

from craftreport.adapters.storage import schema
from craftreport.adapters.storage.database import Database, StorageUnavailable

OLD_TABLES = (
    schema.deployment,
    schema.commands,
    schema.observations,
    schema.feeds,
    schema.snapshots,
    schema.evidence,
    schema.results,
    schema.handoffs,
)


def legacy(path: Path) -> None:
    engine = create_engine("sqlite+pysqlite:///" + str(path))
    with engine.begin() as connection:
        schema.metadata.create_all(connection, tables=OLD_TABLES)
        connection.execute(
            insert(schema.deployment).values(
                singleton=1,
                schema_version=5,
                identity="deployment-a",
                epoch="old-epoch",
                retention_profile="retain-all",
                configured_limits=b'{"setting":"retained"}',
            )
        )
        connection.execute(
            insert(schema.commands).values(
                operation_id="command",
                record_kind="command",
                deployment_scope="deployment-a",
                subject="alice",
                operation_name="snapshot.publish",
                contract_version="1",
                caller_key="caller",
                intent_bytes=b"original intent",
                intent_digest="intent hash",
                revision=1,
                receipt_bytes=b"original receipt",
                receipt_digest="receipt hash",
            )
        )
        connection.execute(
            insert(schema.feeds).values(
                feed_id="feed",
                subject="alice",
                high_water=1,
                revision=1,
            )
        )
        connection.execute(
            insert(schema.snapshots).values(
                feed_id="feed",
                producer_version=1,
                operation_id="command",
                content_digest="content",
                producer_bytes=b"producer",
                snapshot_bytes=b"snapshot",
                snapshot_digest="digest",
            )
        )
        connection.execute(
            insert(schema.observations).values(
                operation_id="command",
                revision=1,
                receipt_bytes=b"old observation",
                receipt_digest="observation digest",
            )
        )
        connection.execute(
            insert(schema.evidence).values(
                identity="evidence",
                operation_id="command",
                reference_bytes=b"reference",
                reference_digest="reference digest",
                fact_bytes=b"fact",
                fact_digest="fact digest",
            )
        )
        connection.execute(
            insert(schema.results).values(
                identity="result",
                operation_id="command",
                command_operation_id="command",
                deployment_scope="deployment-a",
                subject="alice",
                result_bytes=b"result",
                result_digest="result digest",
            )
        )
        connection.execute(
            insert(schema.handoffs).values(
                operation_id="command",
                reference="handoff",
                handoff_bytes=b"handoff",
                handoff_digest="handoff digest",
            )
        )
    engine.dispose()


def dump(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize("existing", [False, True])
def test_fresh_and_populated_v5_migrate_reopen(tmp_path: Path, existing: bool) -> None:
    path = tmp_path / "migration.sqlite3"
    if existing:
        legacy(path)
    before_rows = retained_rows(path) if existing else None
    database = Database(path, "deployment-a")
    asyncio.run(database.close())
    if existing:
        assert retained_rows(path) == before_rows
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT schema_version FROM deployment").fetchone() == (6,)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema")}
        assert {"bindings", "runs"} <= tables
        if existing:
            assert connection.execute("SELECT snapshot_bytes FROM snapshots").fetchone() == (
                b"snapshot",
            )
            assert connection.execute(
                "SELECT epoch, configured_limits FROM deployment"
            ).fetchone() == (
                "old-epoch",
                b'{"setting":"retained"}',
            )
    before = path.read_bytes()
    reopened = Database(path, "deployment-a")
    asyncio.run(reopened.close())
    assert path.read_bytes() == before


def retained_rows(path: Path) -> list[list[tuple[object, ...]]]:
    with sqlite3.connect(path) as connection:
        return [
            connection.execute("SELECT * FROM " + table.name).fetchall()
            for table in OLD_TABLES
            if table.name != "deployment"
        ]


@pytest.mark.parametrize("cutpoint", ["bindings", "runs", "version", "before_version"])
def test_migration_rolls_back_ddl_and_version(tmp_path: Path, cutpoint: str) -> None:
    path = tmp_path / "rollback.sqlite3"
    legacy(path)
    before = dump(path)

    def fail(
        c: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.lstrip().startswith("CREATE TABLE " + cutpoint) or (
            cutpoint in ("version", "before_version")
            and statement.startswith("UPDATE deployment SET schema_version=")
        ):
            raise ValueError("migration fault")

    event_name = "before_cursor_execute" if cutpoint == "before_version" else "after_cursor_execute"
    event.listen(Engine, event_name, fail)
    try:
        with pytest.raises(StorageUnavailable):
            Database(path, "deployment-a")
    finally:
        event.remove(Engine, event_name, fail)
    assert dump(path) == before


def test_maintenance_rejects_v5_without_migration(tmp_path: Path) -> None:
    path = tmp_path / "maintenance.sqlite3"
    legacy(path)
    before = path.read_bytes()
    with pytest.raises(StorageUnavailable):
        Database(path, "deployment-a", maintenance=True)
    assert path.read_bytes() == before


@pytest.mark.parametrize("version", [5, 6])
@pytest.mark.parametrize("damage", ["partial", "extra", "column", "constraint", "future"])
def test_unknown_schema_rejected_without_writes(tmp_path: Path, version: int, damage: str) -> None:
    path = tmp_path / "damaged.sqlite3"
    legacy(path)
    if version == 6:
        database = Database(path, "deployment-a")
        asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        if damage == "partial":
            if version == 6:
                connection.execute("DROP TABLE runs")
            else:
                connection.execute("CREATE TABLE bindings (binding_id TEXT PRIMARY KEY)")
        elif damage == "extra":
            connection.execute("CREATE VIEW extra AS SELECT * FROM deployment")
        elif damage == "column":
            connection.execute("ALTER TABLE commands ADD COLUMN extra TEXT")
        elif damage == "future":
            connection.execute("UPDATE deployment SET schema_version=99")
        else:
            table = "bindings" if version == 6 else "feeds"
            ddl = connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name=?", (table,)
            ).fetchone()
            assert ddl is not None
            changed = ddl[0].replace("revision > 0", "revision >= 0")
            assert changed != ddl[0]
            connection.execute("DROP TABLE " + table)
            connection.execute(changed)
    before = path.read_bytes()
    with pytest.raises(StorageUnavailable):
        Database(path, "deployment-a")
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    ["generation", "revision", "operation", "binding", "feed", "producer", "run_generation"],
)
def test_counter_and_fk_constraints(tmp_path: Path, change: str) -> None:
    path = tmp_path / "constraints.sqlite3"
    legacy(path)
    database = Database(path, "deployment-a")
    asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        binding: list[object] = ["binding", "alice", 1, 1, "command", b"binding", "digest"]
        run: list[object] = ["run", "binding", 1, "feed", 1, b"run", "digest"]
        if change in ("generation", "revision", "operation"):
            binding[{"generation": 2, "revision": 3, "operation": 4}[change]] = (
                "missing" if change == "operation" else 0
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO bindings VALUES (?, ?, ?, ?, ?, ?, ?)", binding)
        else:
            connection.execute("INSERT INTO bindings VALUES (?, ?, ?, ?, ?, ?, ?)", binding)
            index = {"binding": 1, "run_generation": 2, "feed": 3, "producer": 4}[change]
            run[index] = 0 if change in ("producer", "run_generation") else "missing"
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)", run)


def test_historical_run_survives_generation_change_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "history.sqlite3"
    legacy(path)
    database = Database(path, "deployment-a")
    asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO bindings VALUES ('binding', 'alice', 1, 1, 'command', ?, 'digest')",
            (b"binding",),
        )
        connection.execute(
            "INSERT INTO runs VALUES ('run', 'binding', 1, 'feed', 1, ?, 'digest')", (b"exact run",)
        )
        connection.execute("UPDATE bindings SET generation=2, revision=2")
    database = Database(path, "deployment-a", maintenance=True)
    asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT binding_generation, run_bytes FROM runs").fetchone() == (
            1,
            b"exact run",
        )
