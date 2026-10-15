"""Real result bytes, trusted query staging, ownership and v4 transitions."""

import asyncio
import hashlib
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy.engine import Connection, Engine

from craftreport.adapters.storage import schema
from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.application import ports
from craftreport.application.dispatch import Inspection
from craftreport.contracts import (
    Availability,
    Catalog,
    CommandIntent,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Principal,
    ReceiptState,
    Rejection,
    ResourceRef,
    ResultReadback,
    RetryKey,
)
from craftreport.contracts.values import freeze_object

ALICE = Principal("deployment-a", "alice", frozenset())
RESOURCE = ResourceRef("snapshot", "portfolio:1")
PINS = (ExpectedVersion(RESOURCE, "a" * 64),)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    value = Database(tmp_path / "results.sqlite3", ALICE.deployment_scope)
    yield value
    asyncio.run(value.close())


async def command(database: Database) -> str:
    intent = CommandIntent(
        RetryKey(
            ALICE.deployment_scope, ALICE.subject, OperationKey("reports.prepare", "1"), "one"
        ),
        "a" * 64,
        "craftreport-json-v1",
        "correlation",
        (),
        (RESOURCE,),
        PINS,
    )
    found = await DurableJournal(database).admit(intent)
    assert isinstance(found, ports.Admitted)
    return found.receipt.operation_id


def query(
    operation_id: str, reference: str | None, available: Availability = Availability.AVAILABLE
) -> ports.QueryObservation:
    return ports.QueryObservation(
        operation_id,
        ALICE,
        OperationKey("snapshot.read", "1"),
        "query",
        (),
        (RESOURCE,),
        PINS,
        ports.ReceiptUpdate(
            ReceiptState.COMPLETE, result_ref=reference, result_availability=available
        ),
    )


class AllowAccess:
    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessAllowed:
        return ports.AccessAllowed()


class NoEvidence:
    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        assert not refs
        return ()


def inspection(database: Database) -> Inspection:
    deployment = database.deployment
    return Inspection(
        Catalog((), (), deployment.epoch, deployment.retention_profile),
        AllowAccess(),
        DurableJournal(database),
        DurableResults(database),
        NoEvidence(),
    )


def test_exact_bytes_immutable_owner_and_reopen(database: Database) -> None:
    async def exercise() -> None:
        store = DurableResults(database)
        operation_id = await command(database)
        value: JsonObject = {"text": "=SUM(A1:A2)", "n": "9223372036854775807", "nested": [1, None]}
        reference = await store.write(ALICE, operation_id, value)
        assert len(reference) == 32 and "/" not in reference and "\\" not in reference
        assert await store.write(ALICE, operation_id, value) == reference
        retained = await store.read(ALICE, operation_id, reference)
        assert retained.availability is Availability.AVAILABLE and retained.value == freeze_object(
            value
        )
        assert retained.value is not None and isinstance(retained.value["nested"], tuple)
        nested = value["nested"]
        assert isinstance(nested, list)
        nested.append(99)
        assert (await store.read(ALICE, operation_id, reference)).value == retained.value
        with pytest.raises(ports.ServiceUnavailableError):
            await store.write(ALICE, operation_id, {"different": True})
        for caller, identity in (
            (replace(ALICE, subject="bob"), operation_id),
            (replace(ALICE, deployment_scope="other"), operation_id),
            (ALICE, "other-operation"),
        ):
            denied = await store.read(caller, identity, reference)
            assert denied.availability is Availability.INACCESSIBLE and denied.value is None
        await database.close()
        expected = b'{"n":"9223372036854775807","nested":[1,null],"text":"=SUM(A1:A2)"}'
        with sqlite3.connect(database.path) as independent:
            row = independent.execute(
                "SELECT result_bytes,result_digest,command_operation_id FROM results"
            ).fetchone()
            assert row == (expected, hashlib.sha256(expected).hexdigest(), operation_id)
        reopened = Database(database.path, ALICE.deployment_scope)
        try:
            assert await DurableResults(reopened).read(ALICE, operation_id, reference) == retained
        finally:
            await reopened.close()

    asyncio.run(exercise())


def test_staged_query_is_not_public_then_atomic_link(database: Database) -> None:
    async def exercise() -> None:
        store = DurableResults(database)
        reference = await store.write(ALICE, "new-query", {"private": "contents"})
        assert (
            await store.read(ALICE, "new-query", reference)
        ).availability is Availability.AVAILABLE
        rejected = await inspection(database).read_result(ALICE, "new-query")
        assert isinstance(rejected, Rejection) and rejected.diagnostic.code == "receipt_missing"
        observed = await DurableJournal(database).record_query(query("new-query", reference))
        readback = await inspection(database).read_result(ALICE, "new-query")
        assert isinstance(readback, ResultReadback) and readback.receipt == observed
        assert readback.value == {"private": "contents"}
        denied = await inspection(database).read_result(replace(ALICE, subject="bob"), "new-query")
        assert isinstance(denied, Rejection) and denied.diagnostic.code == "result_inaccessible"
        assert (
            await database.transaction(
                lambda c: c.scalar(select(schema.results.c.command_operation_id))
            )
            == "new-query"
        )
        await database.close()
        reopened = Database(database.path, ALICE.deployment_scope)
        try:
            assert await inspection(reopened).read_result(ALICE, "new-query") == readback
        finally:
            await reopened.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "damage", ["absent", "wrong_owner", "wrong_operation", "corrupt", "noncanonical"]
)
def test_available_query_never_journals_unverified_content(database: Database, damage: str) -> None:
    async def exercise() -> None:
        store = DurableResults(database)
        reference = await store.write(ALICE, "new-query", {"answer": 42})
        values: dict[str, dict[str, object]] = {
            "wrong_owner": {"subject": "bob"},
            "wrong_operation": {"operation_id": "another"},
            "corrupt": {"result_bytes": b"{}"},
            "noncanonical": {
                "result_bytes": b'{ "answer":42}',
                "result_digest": hashlib.sha256(b'{ "answer":42}').hexdigest(),
            },
        }
        if damage == "absent":
            await database.transaction(lambda c: c.execute(delete(schema.results)))
        else:
            await database.transaction(
                lambda c: c.execute(update(schema.results).values(**values[damage]))
            )
        with pytest.raises(ports.ServiceUnavailableError):
            await DurableJournal(database).record_query(query("new-query", reference))
        assert isinstance(await DurableJournal(database).read("new-query"), ports.Missing)
        assert (
            await database.transaction(
                lambda c: c.scalar(select(schema.observations.c.operation_id))
            )
            is None
        )

    asyncio.run(exercise())


def test_missing_failed_query_remains_recordable(database: Database) -> None:
    async def exercise() -> None:
        for availability in (Availability.MISSING, Availability.UNAVAILABLE):
            observation = query(availability.value, None, availability)
            observation = replace(
                observation, update=replace(observation.update, state=ReceiptState.FAILED)
            )
            saved = await DurableJournal(database).record_query(observation)
            assert saved.state is ReceiptState.FAILED and saved.result_availability is availability

    asyncio.run(exercise())


def test_linked_reference_cannot_be_reused_by_second_query(database: Database) -> None:
    async def exercise() -> None:
        reference = await DurableResults(database).write(ALICE, "first", {"answer": 42})
        await DurableJournal(database).record_query(query("first", reference))
        with pytest.raises(ports.ServiceUnavailableError):
            await DurableJournal(database).record_query(query("second", reference))
        assert isinstance(await DurableJournal(database).read("second"), ports.Missing)

    asyncio.run(exercise())


def test_query_link_failure_rolls_back_observation_and_retains_stage(database: Database) -> None:
    def fail(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith("UPDATE results SET command_operation_id="):
            raise ValueError("lost query link acknowledgement")

    async def exercise() -> None:
        reference = await DurableResults(database).write(ALICE, "query-cutpoint", {"answer": 42})
        event.listen(Engine, "after_cursor_execute", fail)
        try:
            with pytest.raises(ValueError, match="acknowledgement"):
                await DurableJournal(database).record_query(query("query-cutpoint", reference))
        finally:
            event.remove(Engine, "after_cursor_execute", fail)
        assert isinstance(await DurableJournal(database).read("query-cutpoint"), ports.Missing)
        assert (
            await database.transaction(
                lambda c: c.scalar(select(schema.results.c.command_operation_id))
            )
            is None
        )
        assert (
            await DurableResults(database).read(ALICE, "query-cutpoint", reference)
        ).availability is Availability.AVAILABLE
        assert (
            await DurableJournal(database).record_query(query("query-cutpoint", reference))
        ).result_ref == reference

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["missing", "corrupt", "journal"])
def test_availability_never_regenerates(database: Database, damage: str) -> None:
    async def exercise() -> None:
        operation_id = await command(database)
        store = DurableResults(database)
        reference = await store.write(ALICE, operation_id, {"answer": 42})
        if damage == "missing":
            await database.transaction(lambda c: c.execute(delete(schema.results)))
        elif damage == "corrupt":
            await database.transaction(
                lambda c: c.execute(update(schema.results).values(result_bytes=b"bad"))
            )
        else:
            await database.transaction(
                lambda c: c.execute(update(schema.commands).values(receipt_digest="bad"))
            )
        result = await store.read(ALICE, operation_id, reference)
        assert result.value is None
        assert result.availability is (
            Availability.MISSING if damage == "missing" else Availability.UNAVAILABLE
        )
        await database.close()
        assert (
            await store.read(ALICE, operation_id, reference)
        ).availability is Availability.UNAVAILABLE

    asyncio.run(exercise())


def test_large_supported_result_and_explicit_bound(database: Database) -> None:
    async def exercise() -> None:
        store = DurableResults(database)
        value: JsonObject = {"text": "x" * (8_388_608 - 11)}
        reference = await store.write(ALICE, "large-query", value)
        assert (await store.read(ALICE, "large-query", reference)).value == value
        payload = await database.transaction(
            lambda c: c.scalar(select(schema.results.c.result_bytes))
        )
        assert isinstance(payload, bytes) and len(payload) == 8_388_608
        with pytest.raises(ports.ServiceUnavailableError):
            await store.write(ALICE, "oversize", {"text": "x" * 8_388_608})

    asyncio.run(exercise())


@pytest.mark.parametrize("cutpoint", ["table", "version"])
def test_exact_v3_transition_rolls_back_and_reopens(tmp_path: Path, cutpoint: str) -> None:
    path = tmp_path / "v3.sqlite3"
    database = Database(path, ALICE.deployment_scope)
    asyncio.run(command(database))
    asyncio.run(database.close())
    engine = create_engine("sqlite+pysqlite:///" + str(path))
    with engine.begin() as connection:
        schema.handoffs.drop(connection)
        schema.results.drop(connection)
        connection.execute(update(schema.deployment).values(schema_version=3))
    engine.dispose()
    with sqlite3.connect(path) as independent:
        before = "\n".join(independent.iterdump())

    def fail(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if (cutpoint == "table" and statement.lstrip().startswith("CREATE TABLE results")) or (
            cutpoint == "version" and statement.startswith("UPDATE deployment SET schema_version=")
        ):
            raise ValueError("result migration cutpoint")

    event.listen(Engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(StorageUnavailable):
            Database(path, ALICE.deployment_scope)
    finally:
        event.remove(Engine, "after_cursor_execute", fail)
    with sqlite3.connect(path) as independent:
        assert "\n".join(independent.iterdump()) == before
    reopened = Database(path, ALICE.deployment_scope)
    asyncio.run(reopened.close())
    with sqlite3.connect(path) as independent:
        assert independent.execute("SELECT schema_version FROM deployment").fetchone() == (5,)
        assert independent.execute("SELECT count(*) FROM commands").fetchone() == (1,)


@pytest.mark.parametrize("version", [3, 4])
def test_partial_result_schema_fails_without_repair(tmp_path: Path, version: int) -> None:
    path = tmp_path / "partial-results.sqlite3"
    database = Database(path, ALICE.deployment_scope)
    asyncio.run(database.close())
    with sqlite3.connect(path) as independent:
        independent.execute("DROP TABLE results")
        independent.execute("CREATE TABLE results (identity TEXT PRIMARY KEY)")
        independent.execute("UPDATE deployment SET schema_version=?", (version,))
        before = "\n".join(independent.iterdump())
    with pytest.raises(StorageUnavailable):
        Database(path, ALICE.deployment_scope)
    with sqlite3.connect(path) as independent:
        assert "\n".join(independent.iterdump()) == before
