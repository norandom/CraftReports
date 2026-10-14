"""Execution ownership and retained effects through the real admission path."""

import asyncio

import pytest
from fixture_admission import AdmissionFixture
from fixture_controls import Checkpoint
from fixture_dispatch import ALICE, RESOURCE
from fixture_execution import ExecutionFixture, FixtureHandoffs, executor

from craftreport.application import ports
from craftreport.contracts import Receipt, ReceiptState, RecoveryDisposition, Rejection, RetryKey


def test_complete_has_retained_result_and_independent_effect() -> None:
    asyncio.run(complete_has_retained_result_and_independent_effect())


async def complete_has_retained_result_and_independent_effect() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await owner.invoke(ALICE, fixture.request())
    assert isinstance(receipt, Receipt)
    assert receipt.state is ReceiptState.COMPLETE
    assert receipt == await fixture.journal.read(receipt.operation_id)
    snapshot = await fixture.target.read(RESOURCE)
    assert isinstance(snapshot, ports.ResourceSnapshot)
    assert snapshot.content == {"value": "changed"}
    assert receipt.result_ref is not None
    result = await fixture.results.read(ALICE, receipt.operation_id, receipt.result_ref)
    assert result.value == {"value": "changed"}


@pytest.mark.anyio
async def test_deadline_and_disconnect_leave_owned_effect_running() -> None:
    fixture = ExecutionFixture()
    fixture.target.after_effect = point = Checkpoint()
    owner = executor(fixture)
    owner.response_seconds = 0.1
    task = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await point.wait_until_reached()
    pending = await task
    assert isinstance(pending, Receipt) and pending.state is ReceiptState.PENDING
    assert fixture.target.active_lease is not None
    retry = await owner.invoke(ALICE, fixture.request())
    assert retry == pending
    assert await owner.inspect(ALICE, pending.operation_id) == pending
    point.release()
    assert await owner.shutdown()
    completed = await owner.inspect(ALICE, pending.operation_id)
    assert isinstance(completed, Receipt) and completed.state is ReceiptState.COMPLETE
    assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_cancelled_client_does_not_cancel_guard_or_execution() -> None:
    fixture = ExecutionFixture()
    fixture.target.before_effect = point = Checkpoint()
    owner = executor(fixture)
    client = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await point.wait_until_reached()
    client.cancel()
    with pytest.raises(asyncio.CancelledError):
        await client
    assert fixture.target.active_lease is not None
    retained = await owner.invoke(ALICE, fixture.request())
    assert isinstance(retained, Receipt) and retained.state is ReceiptState.PENDING
    point.release()
    assert await owner.shutdown()
    receipt = await owner.inspect(ALICE, retained.operation_id)
    assert isinstance(receipt, Receipt) and receipt.state is ReceiptState.COMPLETE
    assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_capacity_rejects_without_identity_but_allows_retry_and_inspection() -> None:
    fixture = ExecutionFixture()
    fixture.target.before_effect = point = Checkpoint()
    owner = executor(fixture)
    owner.capacity = 1
    client = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await point.wait_until_reached()
    other = fixture.request(retry_key="other")
    rejected = await owner.invoke(ALICE, other)
    assert isinstance(rejected, Rejection) and rejected.diagnostic.code == "capacity"
    assert rejected.diagnostic.recovery is RecoveryDisposition.RETRY
    assert isinstance(
        await fixture.journal.find(RetryKey("deployment", "alice", other.operation, "other")),
        ports.Missing,
    )
    retry = await owner.invoke(ALICE, fixture.request())
    assert isinstance(retry, Receipt) and await owner.inspect(ALICE, retry.operation_id) == retry
    point.release()
    assert isinstance(await client, Receipt)
    next_receipt = await owner.invoke(
        ALICE, fixture.request(retry_key="other", expected_versions=())
    )
    assert isinstance(next_receipt, Rejection) and next_receipt.diagnostic.code == "invalid_input"
    assert await owner.shutdown()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode, expected",
    [
        ("normal", ReceiptState.COMPLETE),
        ("exception", ReceiptState.AMBIGUOUS),
        ("missing", ReceiptState.PARTIAL),
        ("unavailable", ReceiptState.PARTIAL),
        ("stale", ReceiptState.PARTIAL),
        ("result", ReceiptState.PARTIAL),
        ("lost_ack", ReceiptState.COMPLETE),
    ],
)
async def test_truthful_post_effect_outcomes(mode: str, expected: ReceiptState) -> None:
    fixture = ExecutionFixture(mode)
    owner = executor(fixture)
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Receipt) and result.state is expected
    assert "credential-private" not in repr(result)
    assert await fixture.journal.read(result.operation_id) == result
    fixture.evidence.available = True
    retry = await owner.invoke(ALICE, fixture.request())
    if mode in ("missing", "result"):
        assert isinstance(retry, Rejection)
        assert retry.diagnostic.code in ("evidence_missing", "result_missing")
    else:
        assert retry == result
    assert fixture.target.effect_count == 1
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_post_effect_journal_failure_preserves_pending_without_replay() -> None:
    fixture = ExecutionFixture("journal")
    owner = executor(fixture)
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    fixture.journal.available = True
    retained = await owner.invoke(ALICE, fixture.request())
    assert isinstance(retained, Receipt) and retained.state is ReceiptState.PENDING
    assert fixture.target.effect_count == 1
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_shutdown_records_interrupted_effect_as_ambiguous() -> None:
    fixture = ExecutionFixture()
    fixture.target.after_effect = point = Checkpoint()
    owner = executor(fixture)
    owner.shutdown_seconds = 0.02
    client = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await point.wait_until_reached()
    assert await owner.shutdown()
    result = await client
    assert isinstance(result, Receipt) and result.state is ReceiptState.AMBIGUOUS
    assert await owner.invoke(ALICE, fixture.request()) == result
    assert fixture.target.effect_count == 1 and fixture.target.active_lease is None
    rejected = await owner.invoke(ALICE, fixture.request(retry_key="new"))
    assert isinstance(rejected, Rejection) and rejected.diagnostic.code == "capacity"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode, installed, expected",
    [
        ("handoff", True, ReceiptState.PENDING),
        ("handoff", False, ReceiptState.PARTIAL),
        ("handoff_foreign", True, ReceiptState.PARTIAL),
        ("handoff_stale", True, ReceiptState.PARTIAL),
        ("handoff_unavailable", True, ReceiptState.PARTIAL),
    ],
)
async def test_pending_handoff_requires_new_recorded_installed_owner(
    mode: str, installed: bool, expected: ReceiptState
) -> None:
    fixture = ExecutionFixture(mode)
    owner = executor(fixture)
    owner.handoffs = fixture.handoffs
    owner.installed_owners = frozenset({"external"}) if installed else frozenset()
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Receipt) and result.state is expected
    if expected is ReceiptState.PENDING:
        assert fixture.journal.handoffs[result.operation_id] == "transfer"
        assert len(fixture.handoffs.records) == 2
        assert result.revision == 3
    assert fixture.target.active_lease is None
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_shutdown_resistant_handler_retains_ambiguous_state_and_guard() -> None:
    fixture = ExecutionFixture("resist")
    owner = executor(fixture)
    owner.response_seconds = 0.02
    owner.shutdown_seconds = 0.03
    pending = await owner.invoke(ALICE, fixture.request())
    assert isinstance(pending, Receipt) and pending.state is ReceiptState.PENDING
    async with asyncio.timeout(0.5):
        assert not await owner.shutdown()
    retained = await owner.inspect(ALICE, pending.operation_id)
    assert isinstance(retained, Receipt) and retained.state is ReceiptState.AMBIGUOUS
    assert fixture.target.active_lease is not None
    fixture.finish.set()
    assert await owner.shutdown()
    assert await owner.inspect(ALICE, pending.operation_id) == retained
    assert fixture.target.effect_count == 1 and fixture.target.active_lease is None


@pytest.mark.anyio
async def test_local_owner_unavailable_prevents_effect_and_preserves_identity() -> None:
    fixture = ExecutionFixture()
    owner = executor(fixture)
    handoffs = FixtureHandoffs()
    handoffs.available = False
    owner.handoffs = handoffs
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Rejection)
    retained = await owner.invoke(ALICE, fixture.request())
    assert isinstance(retained, Receipt) and retained.state is ReceiptState.ACCEPTED
    assert fixture.target.effect_count == 0 and fixture.target.active_lease is None
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_retained_complete_retry_reports_missing_content_without_replay() -> None:
    fixture = ExecutionFixture()
    owner = executor(fixture)
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Receipt) and result.state is ReceiptState.COMPLETE
    fixture.results.values.clear()
    retry = await owner.invoke(ALICE, fixture.request())
    assert isinstance(retry, Rejection) and retry.diagnostic.code == "result_missing"
    assert fixture.target.effect_count == 1
    assert await owner.shutdown()
