"""Durable journal effects, independently inspected after file close/reopen."""

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.serialization import (
    decode_intent,
    decode_receipt,
    encode_intent,
    encode_receipt,
)
from craftreport.adapters.transport_wire import encode_invocation_result
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CapabilityVersion,
    CommandIntent,
    Diagnostic,
    EvidenceRef,
    ExpectedVersion,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    ResourceRef,
    RetryKey,
    StageResult,
    StageState,
)
from craftreport.contracts.values import require_immutable


@pytest.fixture
def intent() -> CommandIntent:
    operation = OperationKey("snapshot.publish", "1")
    resource = ResourceRef("feed", "portfolio")
    return CommandIntent(
        RetryKey("deployment-a", "alice", operation, "retry-one"),
        "a" * 64,
        "craftreport-json-v1",
        "correlation-one",
        (CapabilityVersion("snapshot", "1"),),
        (resource,),
        (ExpectedVersion(resource, "17"),),
    )


def test_concurrent_retry_scopes_and_exact_reopen(tmp_path: Path, intent: CommandIntent) -> None:
    path = tmp_path / "journal.sqlite3"

    async def exercise() -> Receipt:
        database = Database(path, "deployment-a")
        journal: ports.OperationJournal = DurableJournal(database)
        assert isinstance(await journal.find(intent.retry_key), ports.Missing)
        results = await asyncio.gather(*(journal.admit(intent) for _ in range(24)))
        admitted = [item.receipt for item in results if isinstance(item, ports.Admitted)]
        assert len(admitted) == 1
        initial = admitted[0]
        assert all(
            isinstance(item, ports.Admitted)
            or isinstance(item, ports.Existing)
            and item.command.receipt == initial
            for item in results
        )
        changed = replace(
            intent,
            correlation_id="new-correlation",
            capability_versions=(CapabilityVersion("x", "2"),),
        )
        equivalent = await journal.admit(changed)
        assert isinstance(equivalent, ports.Existing)
        assert equivalent.command.intent == intent
        assert equivalent.command.receipt == initial
        for conflict in (
            replace(intent, fingerprint="b" * 64),
            replace(intent, normalization_policy="other"),
            replace(intent, resources=(), expected_versions=()),
            replace(intent, expected_versions=(ExpectedVersion(intent.resources[0], "18"),)),
        ):
            assert isinstance(await journal.admit(conflict), ports.AdmissionConflict)
        for key in (
            replace(intent.retry_key, subject="bob"),
            replace(intent.retry_key, operation=OperationKey("snapshot.read", "1")),
            replace(intent.retry_key, operation=OperationKey("snapshot.publish", "2")),
            replace(intent.retry_key, caller_key="retry-two"),
        ):
            assert isinstance(await journal.admit(replace(intent, retry_key=key)), ports.Admitted)
        foreign = replace(intent.retry_key, deployment_scope="other-deployment")
        assert isinstance(
            await journal.admit(replace(intent, retry_key=foreign)), ports.ServiceUnavailable
        )
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.find(foreign)
        await database.close()
        reopened = Database(path, "deployment-a")
        found = await DurableJournal(reopened).find(intent.retry_key)
        assert isinstance(found, ports.RetainedCommand)
        assert found.intent == intent and found.receipt == initial
        assert await DurableJournal(reopened).read(initial.operation_id) == initial
        await reopened.close()
        return initial

    initial = asyncio.run(exercise())
    expected = canonical_bytes(encode_invocation_result(initial), max_depth=None)
    with sqlite3.connect(path) as independent:
        assert independent.execute("SELECT COUNT(*) FROM commands").fetchone() == (5,)
        assert independent.execute("SELECT COUNT(*) FROM observations").fetchone() == (5,)
        row = independent.execute(
            "SELECT deployment_scope, subject, receipt_bytes, receipt_digest FROM commands "
            "WHERE operation_id = ?",
            (initial.operation_id,),
        ).fetchone()
        assert row == ("deployment-a", "alice", expected, hashlib.sha256(expected).hexdigest())
        retained_intent = independent.execute(
            "SELECT intent_bytes FROM commands WHERE operation_id = ?", (initial.operation_id,)
        ).fetchone()
        assert retained_intent is not None
        assert json.loads(retained_intent[0]) == {
            "retry_key": {
                "deployment_scope": "deployment-a",
                "subject": "alice",
                "operation": {"name": "snapshot.publish", "contract_version": "1"},
                "caller_key": "retry-one",
            },
            "fingerprint": "a" * 64,
            "normalization_policy": "craftreport-json-v1",
            "correlation_id": "correlation-one",
            "capability_versions": [{"identity": "snapshot", "version": "1"}],
            "resources": [{"kind": "feed", "identity": "portfolio"}],
            "expected_versions": [
                {"resource": {"kind": "feed", "identity": "portfolio"}, "version": "17"}
            ],
        }


def test_cas_append_history_terminal_and_missing(tmp_path: Path, intent: CommandIntent) -> None:
    path = tmp_path / "cas.sqlite3"

    async def exercise() -> tuple[Receipt, Receipt, Receipt]:
        database = Database(path, "deployment-a")
        journal = DurableJournal(database)
        admission = await journal.admit(intent)
        assert isinstance(admission, ports.Admitted)
        initial = admission.receipt
        diagnostic = Diagnostic(
            initial.operation, "persisted", "observed", RecoveryDisposition.INSPECT
        )
        reference = EvidenceRef(
            "proof-one",
            "persisted",
            initial.operation_id,
            initial.operation,
            initial.expected_versions,
            "d" * 64,
        )
        pending = ports.ReceiptUpdate(
            ReceiptState.PENDING,
            (StageResult("persisted", StageState.PASSED, "verified", (reference,)),),
            (diagnostic,),
            (reference,),
            handoff_ref="owner-one",
        )
        results = await asyncio.gather(
            *(journal.record(initial.operation_id, 1, pending) for _ in range(16))
        )
        winners = [item for item in results if isinstance(item, Receipt)]
        assert len(winners) == 1
        second = winners[0]
        assert all(
            isinstance(item, Receipt) or item == ports.RevisionConflict(2) for item in results
        )
        assert second.stages == pending.stages and second.evidence == (reference,)
        with pytest.raises(ValueError, match="owner"):
            await journal.record(initial.operation_id, 2, pending)
        with pytest.raises(ValueError, match="accepted"):
            await journal.record(
                initial.operation_id, 2, ports.ReceiptUpdate(ReceiptState.ACCEPTED)
            )
        third = await journal.record(
            initial.operation_id,
            2,
            ports.ReceiptUpdate(
                ReceiptState.COMPLETE,
                result_ref="result-one",
                result_availability=Availability.AVAILABLE,
            ),
        )
        assert isinstance(third, Receipt)
        assert third.revision == 3 and third.stages == second.stages
        assert third.diagnostics == (diagnostic,) and third.evidence == (reference,)
        with pytest.raises(ValueError, match="Terminal"):
            await journal.record(initial.operation_id, 3, ports.ReceiptUpdate(ReceiptState.FAILED))
        with pytest.raises(ports.ReceiptMissingError):
            await journal.record("absent", 1, pending)
        assert isinstance(await journal.read("absent"), ports.Missing)
        await database.close()
        reopened = Database(path, "deployment-a")
        assert await DurableJournal(reopened).read(initial.operation_id) == third
        await reopened.close()
        return initial, second, third

    receipts = asyncio.run(exercise())
    with sqlite3.connect(path) as independent:
        rows = independent.execute(
            "SELECT revision, receipt_bytes FROM observations ORDER BY revision"
        ).fetchall()
        assert rows == [
            (item.revision, canonical_bytes(encode_invocation_result(item), max_depth=None))
            for item in receipts
        ]


def test_pending_new_owner_and_ambiguous_reconciliation(
    tmp_path: Path, intent: CommandIntent
) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "transitions.sqlite3", "deployment-a")
        journal = DurableJournal(database)
        admission = await journal.admit(intent)
        assert isinstance(admission, ports.Admitted)
        initial = admission.receipt
        for revision, owner in ((1, "one"), (2, "two")):
            result = await journal.record(
                initial.operation_id,
                revision,
                ports.ReceiptUpdate(ReceiptState.PENDING, handoff_ref=owner),
            )
            assert isinstance(result, Receipt) and result.revision == revision + 1
        ambiguous = await journal.record(
            initial.operation_id, 3, ports.ReceiptUpdate(ReceiptState.AMBIGUOUS)
        )
        assert isinstance(ambiguous, Receipt)
        for state in (ReceiptState.PENDING, ReceiptState.AMBIGUOUS, ReceiptState.COMPLETE):
            with pytest.raises(ValueError, match="reconciliation"):
                await journal.record(initial.operation_id, 4, ports.ReceiptUpdate(state))
        ref = EvidenceRef("reconciled", "reconciliation", initial.operation_id, initial.operation)
        terminal = await journal.record(
            initial.operation_id, 4, ports.ReceiptUpdate(ReceiptState.FAILED, evidence=(ref,))
        )
        assert isinstance(terminal, Receipt) and terminal.evidence == (ref,)
        await database.close()

    asyncio.run(exercise())


def test_query_ownership_exact_fields_and_collisions(tmp_path: Path, intent: CommandIntent) -> None:
    path = tmp_path / "queries.sqlite3"

    async def exercise() -> Receipt:
        database = Database(path, "deployment-a")
        journal = DurableJournal(database)
        reference = EvidenceRef(
            "query-proof", "read", "query-one", intent.retry_key.operation, intent.expected_versions
        )
        observation = ports.QueryObservation(
            "query-one",
            Principal("deployment-a", "bob", frozenset({"read"})),
            intent.retry_key.operation,
            "query-correlation",
            intent.capability_versions,
            intent.resources,
            intent.expected_versions,
            ports.ReceiptUpdate(
                ReceiptState.COMPLETE,
                stages=(StageResult("read", StageState.PASSED, "verified", (reference,)),),
                evidence=(reference,),
                result_ref="query-result",
                result_availability=Availability.AVAILABLE,
                handoff_ref="query-handoff",
            ),
            input_ref="query-input",
        )
        receipt = await journal.record_query(observation)
        assert receipt == Receipt(
            "query-one",
            observation.operation,
            "query-correlation",
            1,
            ReceiptState.COMPLETE,
            observation.capability_versions,
            observation.resources,
            observation.expected_versions,
            "query-input",
            "query-result",
            observation.update.stages,
            (),
            (reference,),
            database.deployment.epoch,
            "retain-all",
            Availability.AVAILABLE,
        )
        assert isinstance(
            await journal.find(replace(intent.retry_key, subject="bob")), ports.Missing
        )
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record_query(observation)
        foreign = replace(
            observation, operation_id="foreign", principal=Principal("foreign", "bob", frozenset())
        )
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record_query(foreign)
        admitted = await journal.admit(intent)
        assert isinstance(admitted, ports.Admitted)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record_query(
                replace(observation, operation_id=admitted.receipt.operation_id)
            )
        await journal.record_query(replace(observation, operation_id="query-two"))
        await database.close()
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record_query(replace(observation, operation_id="closed-provider"))
        reopened = Database(path, "deployment-a")
        assert await DurableJournal(reopened).read("query-one") == receipt
        await reopened.close()
        return receipt

    receipt = asyncio.run(exercise())
    with sqlite3.connect(path) as independent:
        assert independent.execute(
            "SELECT record_kind, subject, caller_key, intent_bytes, intent_digest, handoff_ref "
            "FROM commands WHERE operation_id = 'query-one'"
        ).fetchone() == ("query", "bob", None, None, None, "query-handoff")
        assert independent.execute("SELECT COUNT(*) FROM commands").fetchone() == (3,)
        assert independent.execute(
            "SELECT receipt_bytes FROM observations WHERE operation_id = 'query-one'"
        ).fetchone() == (canonical_bytes(encode_invocation_result(receipt), max_depth=None),)


def test_ambiguity_cannot_reuse_evidence_retained_only_in_a_stage(
    tmp_path: Path,
    intent: CommandIntent,
) -> None:
    path = tmp_path / "stage-reconciliation.sqlite3"

    async def exercise() -> None:
        database = Database(path, "deployment-a")
        journal = DurableJournal(database)
        admitted = await journal.admit(intent)
        assert isinstance(admitted, ports.Admitted)
        receipt = admitted.receipt
        old = EvidenceRef("old", "reconciliation", receipt.operation_id, receipt.operation)
        stage = StageResult("reconciliation", StageState.PASSED, "observed", (old,))
        ambiguous = await journal.record(
            receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.AMBIGUOUS, stages=(stage,))
        )
        assert isinstance(ambiguous, Receipt) and ambiguous.evidence == ()
        with pytest.raises(ValueError, match="New reconciliation"):
            await journal.record(
                receipt.operation_id, 2, ports.ReceiptUpdate(ReceiptState.FAILED, evidence=(old,))
            )
        fresh = replace(old, identity="new")
        final = await journal.record(
            receipt.operation_id, 2, ports.ReceiptUpdate(ReceiptState.FAILED, evidence=(fresh,))
        )
        assert (
            isinstance(final, Receipt) and final.stages == (stage,) and final.evidence == (fresh,)
        )
        await database.close()

    asyncio.run(exercise())
    with sqlite3.connect(path) as independent:
        assert independent.execute("SELECT COUNT(*) FROM observations").fetchone() == (3,)


@pytest.mark.parametrize(
    "damage",
    [
        "digest",
        "noncanonical",
        "unknown",
        "nested_unknown",
        "revision",
        "identity",
        "intent",
        "history",
        "history_missing",
    ],
)
def test_corruption_is_unavailable_not_missing(
    tmp_path: Path, intent: CommandIntent, damage: str
) -> None:
    from craftreport.adapters.storage.schema import commands, observations

    async def exercise() -> None:
        database = Database(tmp_path / "corrupt.sqlite3", "deployment-a")
        journal = DurableJournal(database)
        admission = await journal.admit(intent)
        assert isinstance(admission, ports.Admitted)
        operation_id = admission.receipt.operation_id

        def corrupt(connection: Connection) -> None:
            row = connection.execute(select(commands)).mappings().one()
            raw = row["receipt_bytes"]
            body = json.loads(raw)
            if damage == "digest":
                connection.execute(update(commands).values(receipt_digest="0" * 64))
            elif damage == "intent":
                broken = json.loads(row["intent_bytes"])
                broken["retry_key"]["subject"] = "different"
                changed = canonical_bytes(broken, max_depth=None)
                connection.execute(
                    update(commands).values(
                        intent_bytes=changed, intent_digest=hashlib.sha256(changed).hexdigest()
                    )
                )
            elif damage == "history_missing":
                connection.execute(delete(observations))
            elif damage == "history":
                connection.execute(update(observations).values(receipt_bytes=b"{}"))
            else:
                _damage_receipt(body, damage)
                raw = (
                    json.dumps(body).encode()
                    if damage == "noncanonical"
                    else canonical_bytes(body, max_depth=None)
                )
                digest = hashlib.sha256(raw).hexdigest()
                connection.execute(
                    update(commands).values(receipt_bytes=raw, receipt_digest=digest)
                )
                connection.execute(
                    update(observations).values(receipt_bytes=raw, receipt_digest=digest)
                )

        await database.transaction(corrupt)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.read(operation_id)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.find(intent.retry_key)
        assert isinstance(await journal.admit(intent), ports.ServiceUnavailable)
        await database.close()

    asyncio.run(exercise())


def test_concrete_serialization_matches_public_bytes_and_preserves_nested_values(
    intent: CommandIntent,
) -> None:
    ref = EvidenceRef(
        "proof",
        "persisted",
        "operation",
        intent.retry_key.operation,
        intent.expected_versions,
        "d" * 64,
    )
    diagnostic = Diagnostic(
        intent.retry_key.operation,
        "persisted",
        "verified",
        RecoveryDisposition.INSPECT,
        ("rows", 2),
    )
    receipt = Receipt(
        "operation",
        intent.retry_key.operation,
        "correlation",
        7,
        ReceiptState.COMPLETE,
        intent.capability_versions,
        intent.resources,
        intent.expected_versions,
        "input-ref",
        "result-ref",
        (StageResult("persisted", StageState.PASSED, "verified", (ref,)),),
        (diagnostic,),
        (ref,),
        "epoch",
        "retain-all",
        Availability.AVAILABLE,
        "prior-operation",
    )
    payload, digest = encode_receipt(receipt)
    assert payload == canonical_bytes(encode_invocation_result(receipt), max_depth=None)
    assert digest == hashlib.sha256(payload).hexdigest()
    restored = decode_receipt(payload, digest)
    assert restored == receipt and isinstance(restored.state, ReceiptState)
    assert isinstance(restored.stages[0].evidence, tuple)
    assert restored.diagnostics[0].location == ("rows", 2)
    require_immutable(restored)
    restored_intent = decode_intent(*encode_intent(intent))
    assert restored_intent == intent
    require_immutable(restored_intent)
    optional = replace(
        receipt,
        input_ref=None,
        result_ref=None,
        previous_operation_id=None,
        result_availability=Availability.MISSING,
    )
    assert decode_receipt(*encode_receipt(optional)) == optional
    for damaged in (payload + b" ", b"{}", payload.replace(b'"revision":7', b'"revision":"7"')):
        with pytest.raises(ValueError):
            decode_receipt(damaged, hashlib.sha256(damaged).hexdigest())
    intent_body = json.loads(encode_intent(intent)[0])
    intent_body["retry_key"]["unexpected"] = True
    damaged = canonical_bytes(intent_body)
    with pytest.raises(ValueError):
        decode_intent(damaged, hashlib.sha256(damaged).hexdigest())


def _damage_receipt(body: dict[str, object], damage: str) -> None:
    if damage == "nested_unknown":
        operation = body["operation"]
        assert isinstance(operation, dict)
        operation["unexpected"] = 1
    else:
        changes = {
            "unknown": {"unexpected": 1},
            "revision": {"revision": True},
            "identity": {"operation_id": "different"},
        }
        body.update(changes.get(damage, {}))


def test_database_group_constraint_and_history_foreign_key(
    tmp_path: Path, intent: CommandIntent
) -> None:
    from craftreport.adapters.storage.schema import commands, observations

    async def exercise() -> None:
        database = Database(tmp_path / "constraints.sqlite3", "deployment-a")
        admitted = await DurableJournal(database).admit(intent)
        assert isinstance(admitted, ports.Admitted)
        with pytest.raises(StorageUnavailable):
            await database.transaction(
                lambda c: c.execute(update(commands).values(record_kind="query"))
            )
        with pytest.raises(StorageUnavailable):
            await database.transaction(
                lambda c: c.execute(update(commands).values(caller_key=None))
            )
        with pytest.raises(StorageUnavailable):
            await database.transaction(
                lambda c: c.execute(
                    insert(observations).values(
                        operation_id="absent",
                        revision=1,
                        receipt_bytes=b"{}",
                        receipt_digest="a" * 64,
                    )
                )
            )
        await database.close()

    asyncio.run(exercise())


def test_lost_ack_and_closed_provider_semantics(
    tmp_path: Path, intent: CommandIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "ack.sqlite3", "deployment-a")
        journal = DurableJournal(database)
        transaction = database.transaction

        async def lose_ack[T](action: Callable[[Connection], T]) -> T:
            await transaction(action)
            raise StorageUnavailable("lost acknowledgement")

        with monkeypatch.context() as patch:
            patch.setattr(database, "transaction", lose_ack)
            assert isinstance(await journal.admit(intent), ports.ServiceUnavailable)
        retained = await journal.find(intent.retry_key)
        assert isinstance(retained, ports.RetainedCommand)
        assert isinstance(await journal.admit(intent), ports.Existing)
        with monkeypatch.context() as patch:
            patch.setattr(database, "transaction", lose_ack)
            with pytest.raises(ports.ServiceUnavailableError):
                await journal.record(
                    retained.receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.FAILED)
                )
        current = await journal.read(retained.receipt.operation_id)
        assert (
            isinstance(current, Receipt)
            and current.state is ReceiptState.FAILED
            and current.revision == 2
        )
        await database.close()
        assert isinstance(await journal.admit(intent), ports.ServiceUnavailable)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.read(current.operation_id)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.find(intent.retry_key)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record(current.operation_id, 2, ports.ReceiptUpdate(ReceiptState.FAILED))

    asyncio.run(exercise())


def test_cancelled_admission_can_commit_and_is_found(
    tmp_path: Path, intent: CommandIntent, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "cancel.sqlite3", "deployment-a")
        journal = DurableJournal(database)
        entered, release = Event(), Event()
        transaction = database.transaction

        async def blocked[T](action: Callable[[Connection], T]) -> T:
            def pause(connection: Connection) -> T:
                entered.set()
                assert release.wait(5)
                return action(connection)

            return await transaction(pause)

        with monkeypatch.context() as patch:
            patch.setattr(database, "transaction", blocked)
            task = asyncio.create_task(journal.admit(intent))
            assert await asyncio.to_thread(entered.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            release.set()
        found = await journal.find(intent.retry_key)
        assert isinstance(found, ports.RetainedCommand)
        assert isinstance(await journal.admit(intent), ports.Existing)
        await database.close()

    asyncio.run(exercise())
