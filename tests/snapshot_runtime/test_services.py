"""Actual retained handoffs, bounded service probes and schema-v5 cutpoints."""

import asyncio
import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.engine import Connection, Engine

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.adapters.storage import providers, schema, serialization
from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.application import ports
from craftreport.application.dispatch_ports import RecordedHandoff
from craftreport.contracts import (
    CommandIntent,
    ExpectedVersion,
    OperationKey,
    Principal,
    ReceiptState,
    ResourceRef,
)
from craftreport.contracts.identity import RetryKey

ALICE = Principal("deployment-a", "alice", frozenset({"write", "read"}))
A, B = ResourceRef("feed", "a"), ResourceRef("feed", "b")


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    value = Database(tmp_path / "services.sqlite3", ALICE.deployment_scope)
    yield value
    asyncio.run(value.close())


def resources(database: Database) -> providers.DurableResources:
    fingerprint = CanonicalFingerprint()
    return providers.DurableResources(database, snapshot_codec(), fingerprint, fingerprint.policy)


async def admit(
    database: Database,
    declared: tuple[ResourceRef, ...],
    pins: ports.Preconditions,
    key: str = "one",
) -> str:
    intent = CommandIntent(
        RetryKey(ALICE.deployment_scope, ALICE.subject, OperationKey("fixture.accept", "1"), key),
        "a" * 64,
        "craftreport-json-v1",
        "correlation",
        (),
        declared,
        pins,
    )
    result = await DurableJournal(database).admit(intent)
    assert isinstance(result, ports.Admitted)
    return result.receipt.operation_id


@pytest.mark.parametrize(
    "declared,pins",
    [
        ((), ()),
        ((A, B), ()),
        ((A, B), (ExpectedVersion(A, "absent"),)),
        ((A, B), (ExpectedVersion(A, "absent"), ExpectedVersion(B, "absent"))),
    ],
)
def test_exact_actual_pins_and_original_authority(
    database: Database, declared: tuple[ResourceRef, ...], pins: ports.Preconditions
) -> None:
    async def exercise() -> None:
        target = resources(database)
        handoffs = providers.DurableHandoffs(database, target.guard)
        operation_id = await admit(database, declared, pins)
        record = RecordedHandoff(ALICE, operation_id, "acceptance", "local-uuid", pins)
        async with target.guard.acquire(pins):
            await handoffs.record(record)
            await handoffs.record(record)
            assert await handoffs.inspect(ALICE, operation_id, record.reference) == record
            with pytest.raises(ports.ServiceUnavailableError):
                await handoffs.record(replace(record, owner="changed"))
            task = asyncio.create_task(handoffs.record(record))
            with pytest.raises(ports.ServiceUnavailableError):
                await task
        assert isinstance(
            await handoffs.inspect(ALICE, operation_id, record.reference), ports.ServiceUnavailable
        )
        async with target.guard.acquire(pins):
            with pytest.raises(ports.ServiceUnavailableError):
                await handoffs.record(record)
            assert isinstance(
                await handoffs.inspect(ALICE, operation_id, record.reference),
                ports.ServiceUnavailable,
            )
        raw = await database.transaction(
            lambda c: c.execute(select(schema.handoffs.c.handoff_bytes)).scalar_one()
        )
        assert json.loads(raw)["versions"] == [
            {
                "resource": {"kind": p.resource.kind, "identity": p.resource.identity},
                "version": p.version,
            }
            for p in pins
        ]
        assert json.loads(raw)["principal"]["permitted_scopes"] == ["read", "write"]

    asyncio.run(exercise())


def test_unissued_unknown_foreign_and_same_pin_second_operation(database: Database) -> None:
    async def exercise() -> None:
        target = resources(database)
        handoffs = providers.DurableHandoffs(database, target.guard)
        first, second = await admit(database, (), ()), await admit(database, (), (), "two")
        record = RecordedHandoff(ALICE, first, "one", "local", ())
        with pytest.raises(ports.ServiceUnavailableError):
            await handoffs.record(record)
        async with target.guard.acquire(()):
            await handoffs.record(record)
            assert isinstance(await handoffs.inspect(ALICE, first, "absent"), ports.Missing)
            bob = replace(ALICE, subject="bob")
            assert isinstance(await handoffs.inspect(bob, first, "one"), ports.ServiceUnavailable)
        async with target.guard.acquire(()):
            await handoffs.record(replace(record, operation_id=second, reference="two"))
            assert isinstance(await handoffs.inspect(ALICE, first, "one"), ports.ServiceUnavailable)
        handoffs.close()
        assert isinstance(await handoffs.inspect(ALICE, second, "two"), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_historical_bytes_survive_reopen_without_reviving_owner(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "reopen.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        target = resources(database)
        operation = await admit(database, (), ())
        record = RecordedHandoff(ALICE, operation, "ref", "old-owner", ())
        async with target.guard.acquire(()):
            await providers.DurableHandoffs(database, target.guard).record(record)
        before = await database.transaction(
            lambda c: c.execute(select(schema.handoffs)).mappings().one()
        )
        await database.close()
        reopened = Database(path, ALICE.deployment_scope)
        after = await reopened.transaction(
            lambda c: c.execute(select(schema.handoffs)).mappings().one()
        )
        assert dict(before) == dict(after)
        assert (
            serialization.decode_handoff(after["handoff_bytes"], after["handoff_digest"]) == record
        )
        reader = providers.DurableHandoffs(reopened, resources(reopened).guard)
        assert isinstance(await reader.inspect(ALICE, operation, "ref"), ports.ServiceUnavailable)
        await reopened.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["handoff_bytes", "handoff_digest", "receipt_bytes", "subject"])
def test_corrupt_handoff_or_original_command_fails_closed(database: Database, damage: str) -> None:
    async def exercise() -> None:
        target = resources(database)
        handoffs = providers.DurableHandoffs(database, target.guard)
        operation = await admit(database, (), ())
        record = RecordedHandoff(ALICE, operation, "ref", "local", ())
        async with target.guard.acquire(()):
            await handoffs.record(record)
            table = schema.handoffs if damage.startswith("handoff") else schema.commands
            value = b"broken" if damage.endswith("bytes") else "broken"
            await database.transaction(lambda c: c.execute(update(table).values({damage: value})))
            assert isinstance(
                await handoffs.inspect(ALICE, operation, "ref"), ports.ServiceUnavailable
            )

    asyncio.run(exercise())


def test_actual_health_and_retention_are_current_not_object_presence(database: Database) -> None:
    async def exercise() -> None:
        calls: list[str] = []

        async def owner() -> None:
            calls.append("observed")
            await database.transaction(
                lambda c: c.execute(select(schema.deployment.c.identity)).scalar_one()
            )

        health = providers.DurableHealth(
            database, resources(database), {"access": owner, "capabilities": owner}
        )
        assert (
            await health.check(
                (
                    "journal",
                    "guard",
                    "resources",
                    "effects",
                    "results",
                    "evidence",
                    "handoffs",
                    "access",
                    "capabilities",
                )
            )
            is None
        )
        report = await health.retention()
        assert isinstance(report, providers.RetentionReport)
        assert report.deployment == database.deployment
        assert report.retained_kinds == (
            "snapshots",
            "retry_identities",
            "receipts",
            "results",
            "bindings",
            "runs",
            "evidence",
        )
        assert report.removal == "explicit-offline-only" and len(calls) == 2
        assert isinstance(await health.check(("unconfigured",)), ports.ServiceUnavailable)
        await database.transaction(
            lambda c: c.execute(update(schema.deployment).values(epoch="changed"))
        )
        assert isinstance(await health.retention(), ports.ServiceUnavailable)
        assert isinstance(await health.check(("access",)), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_health_detects_canonical_content_damage_and_close(database: Database) -> None:
    async def exercise() -> None:
        health = providers.DurableHealth(database, resources(database), {})
        operation = await admit(database, (), ())
        await DurableResults(database).write(ALICE, operation, {"retained": "exact"})
        assert await health.check(("results",)) is None
        await database.transaction(
            lambda c: c.execute(update(schema.results).values(result_bytes=b"broken"))
        )
        assert isinstance(await health.check(("results",)), ports.ServiceUnavailable)
        health.close()
        assert isinstance(await health.retention(), ports.ServiceUnavailable)
        assert isinstance(await health.check(()), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_cancelled_original_task_and_pending_external_transfer(database: Database) -> None:
    async def exercise() -> None:
        target = resources(database)
        handoffs = providers.DurableHandoffs(database, target.guard)
        operation = await admit(database, (), ())
        record = RecordedHandoff(ALICE, operation, "original", "local", ())
        entered, release = asyncio.Event(), asyncio.Event()

        async def owner() -> None:
            async with target.guard.acquire(()):
                await handoffs.record(record)
                await DurableJournal(database).record(
                    operation,
                    1,
                    ports.ReceiptUpdate(ReceiptState.PENDING, handoff_ref=record.reference),
                )
                with pytest.raises(ports.ServiceUnavailableError):
                    await handoffs.record(replace(record, reference="transfer", owner="external"))
                entered.set()
                await release.wait()

        task = asyncio.create_task(owner())
        async with asyncio.timeout(5):
            await entered.wait()
        assert await handoffs.inspect(ALICE, operation, "original") == record
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert isinstance(
            await handoffs.inspect(ALICE, operation, "original"), ports.ServiceUnavailable
        )

    asyncio.run(exercise())


def test_unknown_and_corrupt_schema_v5_rejected_untouched(tmp_path: Path) -> None:
    path = tmp_path / "bad-v5.sqlite3"
    database = Database(path, ALICE.deployment_scope)
    asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE INDEX unexpected ON handoffs(reference)")
    before = path.read_bytes()
    with pytest.raises(StorageUnavailable):
        Database(path, ALICE.deployment_scope)
    assert path.read_bytes() == before


def test_handoff_cannot_forge_pins_retarget_operation_or_mutate_issued_lease(
    database: Database,
) -> None:
    async def exercise() -> None:
        target = resources(database)
        handoffs = providers.DurableHandoffs(database, target.guard)
        pins = (ExpectedVersion(A, "absent"),)
        one = await admit(database, (A,), pins)
        two = await admit(database, (A,), pins, "two")
        record = RecordedHandoff(ALICE, one, "ref", "local", pins)
        async with target.guard.acquire(pins) as lease:
            with pytest.raises(ports.ServiceUnavailableError):
                await handoffs.record(replace(record, versions=()))
            await handoffs.record(record)
            with pytest.raises(ports.ServiceUnavailableError):
                await handoffs.record(replace(record, operation_id=two))
            object.__setattr__(lease, "authoritative_versions", ())
            assert isinstance(await handoffs.inspect(ALICE, one, "ref"), ports.ServiceUnavailable)
        assert (
            await database.transaction(lambda c: len(c.execute(select(schema.handoffs)).all())) == 1
        )

    asyncio.run(exercise())


def test_strict_handoff_codec_rejects_unknown_fields_and_noncanonical_content() -> None:
    import hashlib

    record = RecordedHandoff(ALICE, "operation", "ref", "local", ())
    payload, digest = serialization.encode_handoff(record)
    assert serialization.decode_handoff(payload, digest) == record
    for changed in (
        payload.replace(b'"owner":"local"', b'"owner":"local","unexpected":true'),
        b" " + payload,
    ):
        with pytest.raises(ValueError):
            serialization.decode_handoff(changed, hashlib.sha256(changed).hexdigest())


@pytest.mark.parametrize("cutpoint", ["before", "after", "changed"])
def test_handoff_write_failure_reconciles_only_original_live_exact_record(
    database: Database, monkeypatch: pytest.MonkeyPatch, cutpoint: str
) -> None:
    async def exercise() -> None:
        target = resources(database)
        store = providers.DurableHandoffs(database, target.guard)
        operation = await admit(database, (), ())
        record = RecordedHandoff(ALICE, operation, "ref", "original", ())
        original = database.transaction
        calls = 0

        async def fail_once[T](action: Callable[[Connection], T]) -> T:
            nonlocal calls
            calls += 1
            if calls != 1:
                return await original(action)
            if cutpoint != "before":
                await original(action)
                if cutpoint == "changed":
                    payload, digest = serialization.encode_handoff(
                        replace(record, owner="different")
                    )
                    await original(
                        lambda c: c.execute(
                            update(schema.handoffs).values(
                                handoff_bytes=payload, handoff_digest=digest
                            )
                        )
                    )
            raise StorageUnavailable("lost write acknowledgement")

        async with target.guard.acquire(()):
            with monkeypatch.context() as patch:
                patch.setattr(database, "transaction", fail_once)
                if cutpoint == "after":
                    await store.record(record)
                else:
                    with pytest.raises(ports.ServiceUnavailableError):
                        await store.record(record)
            found = await store.inspect(ALICE, operation, "ref")
            if cutpoint == "before":
                assert isinstance(found, ports.Missing)
                await store.record(record)
            elif cutpoint == "changed":
                assert isinstance(found, ports.ServiceUnavailable)
            else:
                assert found == record
                await store.record(record)
        async with target.guard.acquire(()):
            assert isinstance(
                await store.inspect(ALICE, operation, "ref"), ports.ServiceUnavailable
            )

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["subject", "deployment_scope", "unlinked"])
def test_result_health_validates_selected_owner_and_link_not_unrelated_command(
    database: Database, damage: str
) -> None:
    async def exercise() -> None:
        await admit(database, (), (), "unrelated")
        operation = await admit(database, (), (), "result-owner")
        await DurableResults(database).write(ALICE, operation, {"retained": "exact"})
        health = providers.DurableHealth(database, resources(database), {})
        assert await health.check(("results",)) is None
        changes = {"command_operation_id": None} if damage == "unlinked" else {damage: "foreign"}
        await database.transaction(lambda c: c.execute(update(schema.results).values(changes)))
        assert isinstance(await health.check(("results",)), ports.ServiceUnavailable)

    asyncio.run(exercise())


@pytest.mark.parametrize("damage", ["owner", "pins", "command"])
def test_handoff_health_checks_historical_original_command_without_claiming_liveness(
    database: Database, damage: str
) -> None:
    async def exercise() -> None:
        await admit(database, (), (), "unrelated")
        operation = await admit(database, (), (), "handoff-owner")
        target = resources(database)
        store = providers.DurableHandoffs(database, target.guard)
        record = RecordedHandoff(ALICE, operation, "ref", "old-local", ())
        async with target.guard.acquire(()):
            await store.record(record)
        health = providers.DurableHealth(database, target, {})
        assert await health.check(("handoffs",)) is None
        assert isinstance(await store.inspect(ALICE, operation, "ref"), ports.ServiceUnavailable)
        if damage == "command":
            await database.transaction(
                lambda c: c.execute(
                    update(schema.commands)
                    .where(schema.commands.c.operation_id == operation)
                    .values(intent_bytes=b"broken")
                )
            )
        else:
            changed = (
                replace(record, principal=replace(ALICE, subject="foreign"))
                if damage == "owner"
                else replace(record, versions=(ExpectedVersion(A, "1"),))
            )
            payload, digest = serialization.encode_handoff(changed)
            await database.transaction(
                lambda c: c.execute(
                    update(schema.handoffs).values(handoff_bytes=payload, handoff_digest=digest)
                )
            )
        assert isinstance(await health.check(("handoffs",)), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_staged_prejournal_result_is_a_valid_health_sample(database: Database) -> None:
    async def exercise() -> None:
        await admit(database, (), (), "unrelated")
        await DurableResults(database).write(ALICE, "prejournal-query", {"retained": "staged"})
        assert (
            await providers.DurableHealth(database, resources(database), {}).check(("results",))
            is None
        )

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["unavailable", "exception", "closed"])
def test_current_owner_probe_failures_and_closed_during_await(
    database: Database, mode: str
) -> None:
    async def exercise() -> None:
        entered, release = asyncio.Event(), asyncio.Event()

        async def probe() -> ports.ServiceUnavailable | None:
            entered.set()
            await release.wait()
            if mode == "exception":
                raise RuntimeError("owner fault")
            return ports.ServiceUnavailable("owner") if mode == "unavailable" else None

        health = providers.DurableHealth(database, resources(database), {"access": probe})
        check = asyncio.create_task(health.check(("access",)))
        async with asyncio.timeout(5):
            await entered.wait()
        if mode == "closed":
            health.close()
        release.set()
        assert isinstance(await check, ports.ServiceUnavailable)
        with pytest.raises(ValueError):
            providers.DurableHealth(database, resources(database), {"journal": probe})

    asyncio.run(exercise())


def v4(path: Path) -> str:
    database = Database(path, ALICE.deployment_scope)
    asyncio.run(admit(database, (), ()))
    asyncio.run(database.close())
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE runs")
        connection.execute("DROP TABLE bindings")
        connection.execute("DROP TABLE handoffs")
        connection.execute("UPDATE deployment SET schema_version=4")
    return dump(path)


def dump(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return "\n".join(connection.iterdump())


@pytest.mark.parametrize("cutpoint", ["table", "version"])
def test_populated_v4_rollback_and_migration(tmp_path: Path, cutpoint: str) -> None:
    path = tmp_path / "v4.sqlite3"
    before = v4(path)

    def fail(
        c: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if (cutpoint == "table" and statement.lstrip().startswith("CREATE TABLE handoffs")) or (
            cutpoint == "version" and statement.startswith("UPDATE deployment SET schema_version=")
        ):
            raise ValueError("v5 fault")

    event.listen(Engine, "after_cursor_execute", fail)
    try:
        with pytest.raises(StorageUnavailable):
            Database(path, ALICE.deployment_scope)
    finally:
        event.remove(Engine, "after_cursor_execute", fail)
    assert dump(path) == before
    database = Database(path, ALICE.deployment_scope)
    asyncio.run(database.close())
    with sqlite3.connect(path) as independent:
        assert independent.execute("SELECT schema_version FROM deployment").fetchone() == (6,)
        assert independent.execute("SELECT count(*) FROM commands").fetchone() == (1,)
