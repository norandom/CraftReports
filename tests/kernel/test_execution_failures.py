"""Provider acknowledgement, deadline and retention failures never authorize replay."""

import asyncio
from dataclasses import replace

import pytest
from fixture_admission import KEY
from fixture_controls import Checkpoint
from fixture_dispatch import ALICE
from fixture_execution import ExecutionFixture, executor
from fixture_journal import FixtureJournal

from craftreport.application import ports
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.contracts import CommandIntent, Receipt, ReceiptState, Rejection, RetryKey


class LateAdmission(FixtureJournal):
    def __init__(self) -> None:
        super().__init__()
        self.point = Checkpoint()

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        try:
            await self.point.wait()
        except asyncio.CancelledError:
            await self.point.wait()
        return await super().admit(intent)


def journal_fixture(journal: FixtureJournal) -> ExecutionFixture:
    fixture = ExecutionFixture()
    fixture.journal = journal
    fixture.access.journal = journal
    fixture.admission = replace(fixture.admission, journal=journal)
    return fixture


@pytest.mark.anyio
async def test_admission_timeout_cannot_execute_after_unavailable_response() -> None:
    journal = LateAdmission()
    fixture = journal_fixture(journal)
    owner = executor(fixture)
    normal_response_seconds = owner.response_seconds
    owner.response_seconds = 0.02
    client = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await journal.point.wait_until_reached()
    result = await client
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    journal.point.release()
    assert await owner.shutdown()
    retained = await journal.find(RetryKey("deployment", "alice", KEY, "retry"))
    assert isinstance(retained, ports.RetainedCommand)
    assert retained.receipt.state is ReceiptState.ACCEPTED
    owner.response_seconds = normal_response_seconds
    retry = await owner.invoke(ALICE, fixture.request())
    assert retry == retained.receipt
    assert fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None


class BadCompletion(FixtureJournal):
    def __init__(self, conflict: bool) -> None:
        super().__init__()
        self.conflict = conflict

    async def record(
        self, operation_id: str, expected_revision: int, update: ports.ReceiptUpdate
    ) -> ports.RecordResult:
        if update.state is ReceiptState.PENDING:
            return await super().record(operation_id, expected_revision, update)
        if self.conflict:
            return ports.RevisionConflict(expected_revision)
        result = await super().record(operation_id, expected_revision, update)
        assert isinstance(result, Receipt)
        return replace(result, operation_id="foreign")


@pytest.mark.anyio
@pytest.mark.parametrize("conflict", [False, True])
async def test_bad_conditional_update_never_returns_invented_success(conflict: bool) -> None:
    fixture = journal_fixture(BadCompletion(conflict))
    owner = executor(fixture)
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
    retained = await fixture.journal.find(RetryKey("deployment", "alice", KEY, "retry"))
    assert isinstance(retained, ports.RetainedCommand)
    assert retained.receipt.state is (ReceiptState.PENDING if conflict else ReceiptState.COMPLETE)
    assert await owner.invoke(ALICE, fixture.request()) == retained.receipt
    assert fixture.target.effect_count == 1
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_oversized_result_preserves_known_applied_effect() -> None:
    fixture = ExecutionFixture()
    bound = fixture.registry.resolve(KEY.name, KEY.contract_version)
    assert bound is not None
    descriptor = replace(
        bound.descriptor, limits=replace(bound.descriptor.limits, max_output_bytes=1)
    )
    registry = ImmutableOperationRegistry((replace(bound, descriptor=descriptor),))
    fixture.guards = replace(fixture.guards, registry=registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    owner = executor(fixture)
    result = await owner.invoke(ALICE, fixture.request())
    assert isinstance(result, Receipt) and result.state is ReceiptState.PARTIAL
    assert any(item.code == "result_invalid" for item in result.diagnostics)
    assert fixture.target.effect_count == 1 and result.result_ref is None
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_lost_admission_acknowledgement_never_grants_execution() -> None:
    fixture = ExecutionFixture()
    fixture.journal.lose_admission_ack = True
    owner = executor(fixture)
    receipt = await owner.invoke(ALICE, fixture.request())
    assert isinstance(receipt, Receipt) and receipt.state is ReceiptState.ACCEPTED
    assert await owner.invoke(ALICE, fixture.request()) == receipt
    assert fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_facade_routes_read_only_queries_and_catalog_through_existing_guards() -> None:
    fixture = ExecutionFixture()
    command = fixture.registry.resolve(KEY.name, KEY.contract_version)
    assert command is not None
    query = fixture.binding.bind()
    registry = ImmutableOperationRegistry((command, query))
    fixture.guards = replace(fixture.guards, registry=registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    fixture.access.operation_scopes[query.descriptor.key] = "read"
    fixture.catalog = replace(fixture.catalog, operations=registry.describe())
    owner = executor(fixture)
    facade: ports.Facade = owner
    catalog = await facade.catalog(ALICE)
    assert len(catalog.operations) == 2
    request = replace(
        fixture.request(),
        operation=query.descriptor.key,
        payload={"target": "target"},
        retry_key=None,
        expected_versions=(),
    )
    result = await facade.invoke(ALICE, request)
    assert isinstance(result, Receipt) and result.state is ReceiptState.COMPLETE
    assert fixture.target.effect_count == 0
    assert await facade.inspect(ALICE, result.operation_id) == result
    assert await owner.shutdown()


@pytest.mark.anyio
async def test_shutdown_blocks_late_admission_even_when_provider_ignores_cancel() -> None:
    journal = LateAdmission()
    fixture = journal_fixture(journal)
    owner = executor(fixture)
    owner.shutdown_seconds = 0.03
    client = asyncio.create_task(owner.invoke(ALICE, fixture.request()))
    await journal.point.wait_until_reached()
    assert not await owner.shutdown()
    journal.point.release()
    receipt = await client
    assert isinstance(receipt, Receipt) and receipt.state is ReceiptState.ACCEPTED
    assert fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None
    assert await owner.shutdown()
