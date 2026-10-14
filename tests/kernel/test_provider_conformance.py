"""Synthetic provider guarantees, without dispatcher or production durability claims."""

import asyncio
from dataclasses import replace

import pytest
from fixture_controls import Checkpoint
from fixture_journal import FixtureJournal

from craftreport.application import ports
from craftreport.application.outcomes import validate_recorded_update
from craftreport.contracts import (
    Availability,
    CommandIntent,
    EvidenceRef,
    ExpectedVersion,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    ResourceRef,
    RetryKey,
    StageResult,
    StageState,
)

KEY = OperationKey("fixture.set", "1")
RESOURCE = ResourceRef("fixture", "target")
PIN = ExpectedVersion(RESOURCE, "1")


def intent() -> CommandIntent:
    return CommandIntent(
        RetryKey("deployment", "alice", KEY, "retry"),
        "hash",
        "v1",
        "correlation",
        (),
        (RESOURCE,),
        (PIN,),
    )


def test_concurrent_atomic_admission_and_conflicts() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        barrier = asyncio.Barrier(20)

        async def contender() -> ports.Admission:
            async with asyncio.timeout(2):
                await barrier.wait()
                return await journal.admit(intent())

        results = await asyncio.gather(*(contender() for _ in range(20)))
        winners = [r for r in results if isinstance(r, ports.Admitted)]
        assert len(winners) == 1
        winner = winners[0].receipt
        assert sum(isinstance(r, ports.Existing) for r in results) == 19
        assert await journal.read(winner.operation_id) == winner
        assert isinstance(
            await journal.admit(replace(intent(), fingerprint="other")), ports.AdmissionConflict
        )
        assert isinstance(
            await journal.admit(replace(intent(), correlation_id="retry2")), ports.Existing
        )
        assert isinstance(
            await journal.admit(replace(intent(), expected_versions=(replace(PIN, version="2"),))),
            ports.AdmissionConflict,
        )

    asyncio.run(run())


def test_journal_cas_retention_and_failures() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        journal.lose_admission_ack = True
        assert isinstance(await journal.admit(intent()), ports.ServiceUnavailable)
        retained = await journal.find(intent().retry_key)
        assert isinstance(retained, ports.RetainedCommand)
        receipt = retained.receipt
        assert receipt.retention_profile == "synthetic-temporary-no-eviction"
        updated = await journal.record(
            receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.PENDING)
        )
        assert isinstance(updated, Receipt) and updated.revision == 2
        assert await journal.record(
            receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.FAILED)
        ) == ports.RevisionConflict(2)
        journal.available = False
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.find(intent().retry_key)
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.read(receipt.operation_id)
        fresh = FixtureJournal()
        assert fresh.epoch != journal.epoch
        assert isinstance(await fresh.read(receipt.operation_id), ports.Missing)
        with pytest.raises(ports.ReceiptMissingError):
            await fresh.record(receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.FAILED))

    asyncio.run(run())


@pytest.mark.parametrize(
    "key",
    [
        RetryKey("other", "alice", KEY, "retry"),
        RetryKey("deployment", "bob", KEY, "retry"),
        RetryKey("deployment", "alice", replace(KEY, name="fixture.other"), "retry"),
        RetryKey("deployment", "alice", replace(KEY, contract_version="2"), "retry"),
        RetryKey("deployment", "alice", KEY, "other"),
    ],
)
def test_retry_key_dimensions_are_independent(key: RetryKey) -> None:
    async def run() -> None:
        journal: ports.OperationJournal = FixtureJournal()
        first = await journal.admit(intent())
        second = await journal.admit(replace(intent(), retry_key=key))
        assert isinstance(first, ports.Admitted) and isinstance(second, ports.Admitted)
        assert first.receipt.operation_id != second.receipt.operation_id
        assert await journal.find(key) == ports.RetainedCommand(
            replace(intent(), retry_key=key), second.receipt
        )

    asyncio.run(run())


def test_append_history_lost_record_ack_and_terminal_immutability() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        admission = await journal.admit(intent())
        assert isinstance(admission, ports.Admitted)
        original = admission.receipt
        proof = EvidenceRef("proof", "synthetic", original.operation_id, KEY, (PIN,))
        stage = StageResult("effect", StageState.PENDING, "pending", (proof,))
        update = ports.ReceiptUpdate(ReceiptState.AMBIGUOUS, stages=(stage,), evidence=(proof,))
        journal.lose_record_ack = True
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record(original.operation_id, 1, update)
        ambiguous = await journal.read(original.operation_id)
        assert isinstance(ambiguous, Receipt)
        validate_recorded_update(original, ambiguous, update)
        with pytest.raises(ValueError, match="reconciliation"):
            await journal.record(
                original.operation_id, 2, ports.ReceiptUpdate(ReceiptState.COMPLETE)
            )
        reconciliation = replace(proof, identity="reconciled", scope="reconciliation")
        resolved = ports.ReceiptUpdate(
            ReceiptState.COMPLETE,
            evidence=(reconciliation,),
            result_ref="result",
            result_availability=Availability.AVAILABLE,
        )
        complete = await journal.record(original.operation_id, 2, resolved)
        assert isinstance(complete, Receipt)
        validate_recorded_update(ambiguous, complete, resolved)
        with pytest.raises(ValueError, match="immutable"):
            await journal.record(original.operation_id, 3, resolved)
        retained = await journal.find(intent().retry_key)
        assert isinstance(retained, ports.RetainedCommand) and retained.receipt == complete

    asyncio.run(run())


def test_concurrent_cas_has_one_winner() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        admission = await journal.admit(intent())
        assert isinstance(admission, ports.Admitted)
        results = await asyncio.gather(
            *(
                journal.record(
                    admission.receipt.operation_id, 1, ports.ReceiptUpdate(ReceiptState.FAILED)
                )
                for _ in range(20)
            )
        )
        assert sum(isinstance(result, Receipt) for result in results) == 1
        assert sum(result == ports.RevisionConflict(2) for result in results) == 19

    asyncio.run(run())


def test_query_observations_are_not_retry_reservations() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        principal = Principal("deployment", "alice", frozenset({"inspect"}))
        observation = ports.QueryObservation(
            "query",
            principal,
            KEY,
            "correlation",
            (),
            (RESOURCE,),
            (PIN,),
            ports.ReceiptUpdate(ReceiptState.COMPLETE),
        )
        receipt = await journal.record_query(observation)
        assert await journal.read("query") == receipt
        assert journal.owners["query"] == ("deployment", "alice")
        assert isinstance(await journal.find(intent().retry_key), ports.Missing)
        with pytest.raises(ValueError, match="already retained"):
            await journal.record_query(observation)
        journal.available = False
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record_query(replace(observation, operation_id="other"))
        with pytest.raises(ports.ServiceUnavailableError):
            await journal.record("query", 1, ports.ReceiptUpdate(ReceiptState.FAILED))
        assert isinstance(await journal.admit(intent()), ports.ServiceUnavailable)

    asyncio.run(run())


def test_admission_checkpoint_cancellation_does_not_reserve_identity() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        checkpoint = Checkpoint()
        journal.before_admit = checkpoint
        task = asyncio.create_task(journal.admit(intent()))
        await checkpoint.wait_until_reached()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert checkpoint.waiters == 0
        assert isinstance(await journal.find(intent().retry_key), ports.Missing)
        checkpoint.release()
        assert isinstance(await journal.admit(intent()), ports.Admitted)

    asyncio.run(run())
