"""Retry acceptance is proven by actual handler effects and independent readback."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

import pytest
from fixture_admission import KEY, AdmissionFixture
from fixture_controls import Checkpoint
from fixture_dispatch import ALICE, RESOURCE
from fixture_journal import FixtureJournal

from craftreport.application import ports
from craftreport.application.admission import AdmittedCommand
from craftreport.application.outcomes import DiagnosticPolicy
from craftreport.application.registry import CommandBehavior, ImmutableOperationRegistry
from craftreport.contracts import (
    CommandIntent,
    Diagnostic,
    ExpectedVersion,
    Principal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    RetryKey,
)


@pytest.mark.anyio
async def test_concurrent_equivalent_commands_have_one_effect() -> None:
    fixture = AdmissionFixture()
    results = await asyncio.gather(*(fixture.run() for _ in range(20)))
    assert all(isinstance(result, Receipt) for result in results)
    assert len({result.operation_id for result in results if isinstance(result, Receipt)}) == 1
    assert fixture.target.effect_count == 1 and fixture.calls == 1
    snapshot = await fixture.target.read(RESOURCE)
    assert isinstance(snapshot, ports.ResourceSnapshot)
    assert snapshot.content == {"value": "changed"}
    assert snapshot.version.version == "2"


class RacingJournal(FixtureJournal):
    def __init__(self) -> None:
        super().__init__()
        self.arrivals = 0
        self.all_missing = asyncio.Event()

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        result = await super().find(key)
        if self.arrivals < 20:
            assert isinstance(result, ports.Missing)
            self.arrivals += 1
            if self.arrivals == 20:
                self.all_missing.set()
            async with asyncio.timeout(2):
                await self.all_missing.wait()
        return result


@pytest.mark.anyio
async def test_all_initial_lookups_missing_recheck_after_versions_advance() -> None:
    fixture = AdmissionFixture()
    journal = RacingJournal()
    fixture.access.journal = journal
    fixture.admission = replace(fixture.admission, journal=journal)
    results = await asyncio.gather(*(fixture.run() for _ in range(20)))
    assert journal.arrivals == 20
    assert all(isinstance(result, Receipt) for result in results)
    assert len({result.operation_id for result in results if isinstance(result, Receipt)}) == 1
    assert fixture.calls == fixture.target.effect_count == 1
    assert fixture.target.active_lease is None


@pytest.mark.anyio
async def test_normalized_defaults_correlation_and_conflicting_preconditions() -> None:
    fixture = AdmissionFixture()
    first = await fixture.run()
    equivalent = await fixture.run(
        fixture.request(payload={"value": "changed"}, correlation_id="other")
    )
    assert first == equivalent
    for request in (
        fixture.request(payload={"value": "different"}),
        fixture.request(expected_versions=()),
        fixture.request(expected_versions=(ExpectedVersion(RESOURCE, "2"),)),
    ):
        result = await fixture.run(request)
        assert isinstance(result, Rejection)
        assert result.diagnostic.code == "retry_conflict"
    assert fixture.target.effect_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("versions", [(), (ExpectedVersion(RESOURCE, "0"),)])
async def test_missing_required_or_stale_versions_do_not_reserve_identity(
    versions: tuple[ExpectedVersion, ...],
) -> None:
    fixture = AdmissionFixture()
    result = await fixture.run(fixture.request(expected_versions=versions))
    assert isinstance(result, Rejection)
    assert fixture.calls == fixture.target.effect_count == 0
    assert not fixture.journal.owners
    assert isinstance(await fixture.run(), Receipt)


@pytest.mark.anyio
async def test_scoped_cross_principal_key_never_returns_alice_receipt() -> None:
    fixture = AdmissionFixture()
    alice = await fixture.run()
    assert isinstance(alice, Receipt)
    async with fixture.admission.open(fixture.bob, fixture.request()) as stale:
        assert isinstance(stale, Rejection)
        assert alice.operation_id not in repr(stale)
    fresh = fixture.request(expected_versions=(ExpectedVersion(RESOURCE, "2"),))
    async with fixture.admission.open(fixture.bob, fresh) as bob:
        assert isinstance(bob, AdmittedCommand)
        assert bob.receipt.operation_id != alice.operation_id
        await bob.invoke(fixture.services)
    assert fixture.target.effect_count == 2


@pytest.mark.anyio
async def test_acknowledgement_loss_reconciles_without_effect_or_replay() -> None:
    fixture = AdmissionFixture()
    fixture.journal.lose_admission_ack = True
    result = await fixture.run()
    assert isinstance(result, Receipt)
    assert result.state is ReceiptState.ACCEPTED
    assert await fixture.run() == result
    assert fixture.target.effect_count == 0 and fixture.calls == 0
    assert fixture.target.active_lease is None


@pytest.mark.anyio
@pytest.mark.parametrize("state", [ReceiptState.AMBIGUOUS, ReceiptState.PARTIAL])
async def test_unresolved_or_partial_retained_receipts_never_replay(state: ReceiptState) -> None:
    fixture = AdmissionFixture()
    first = await fixture.run()
    assert isinstance(first, Receipt)
    retained = await fixture.journal.record(
        first.operation_id, first.revision, ports.ReceiptUpdate(state)
    )
    assert await fixture.run() == retained
    assert fixture.calls == 1


@pytest.mark.anyio
async def test_guard_loss_and_one_shot_authority() -> None:
    fixture = AdmissionFixture()
    async with fixture.admission.open(ALICE, fixture.request()) as admitted:
        assert isinstance(admitted, AdmittedCommand)
        assert fixture.target.active_lease is not None
        fixture.target.active_lease.lost = True
        assert isinstance(await admitted.invoke(fixture.services), ports.GuardLost)
        with pytest.raises(RuntimeError):
            await admitted.invoke(fixture.services)
    with pytest.raises(RuntimeError):
        await admitted.invoke(fixture.services)
    assert fixture.target.active_lease is None
    assert fixture.calls == 0


@pytest.mark.anyio
async def test_guard_unavailability_immediately_before_invoke_blocks_handler() -> None:
    fixture = AdmissionFixture()
    async with fixture.admission.open(ALICE, fixture.request()) as admitted:
        assert isinstance(admitted, AdmittedCommand)
        fixture.target.available = False
        assert isinstance(await admitted.invoke(fixture.services), ports.ServiceUnavailable)
    assert fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None


@pytest.mark.anyio
async def test_conflicting_retry_during_guarded_effect_does_not_take_authority() -> None:
    fixture = AdmissionFixture()
    checkpoint = Checkpoint()
    fixture.target.before_effect = checkpoint
    winner = asyncio.create_task(fixture.run())
    await checkpoint.wait_until_reached()
    conflict = await fixture.run(fixture.request(payload={"value": "overwrite"}))
    assert isinstance(conflict, Rejection)
    assert conflict.diagnostic.code == "retry_conflict"
    checkpoint.release()
    assert isinstance(await winner, Receipt)
    snapshot = await fixture.target.read(RESOURCE)
    assert isinstance(snapshot, ports.ResourceSnapshot)
    assert snapshot.content == {"value": "changed"}
    assert fixture.calls == fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_cancellation_inside_admission_releases_lease() -> None:
    fixture = AdmissionFixture()
    checkpoint = Checkpoint()
    fixture.journal.before_admit = checkpoint
    task = asyncio.create_task(fixture.run())
    await checkpoint.wait_until_reached()
    assert fixture.target.active_lease is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fixture.target.active_lease is None
    assert not fixture.journal.owners
    assert fixture.target.effect_count == 0


class AdmissionFaultJournal(FixtureJournal):
    def __init__(self, mode: str) -> None:
        super().__init__()
        self.mode = mode
        self.admission_attempted = False

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        if self.mode == "unavailable_absent":
            return ports.ServiceUnavailable("journal")
        result = await super().admit(intent)
        self.admission_attempted = True
        if self.mode == "existing":
            found = await super().find(intent.retry_key)
            assert isinstance(found, ports.RetainedCommand)
            return ports.Existing(found)
        return result

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        if self.admission_attempted and self.mode == "missing":
            return ports.Missing()
        if self.admission_attempted and self.mode == "unavailable":
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("journal"))
        found = await super().find(key)
        if (
            self.admission_attempted
            and self.mode == "foreign"
            and isinstance(found, ports.RetainedCommand)
        ):
            return replace(
                found, intent=replace(found.intent, retry_key=replace(key, subject="foreign"))
            )
        return found

    async def read(self, operation_id: str) -> ports.ReceiptRead:
        result = await super().read(operation_id)
        if self.admission_attempted and self.mode == "read_missing":
            return ports.Missing()
        if self.admission_attempted and self.mode == "read_foreign" and isinstance(result, Receipt):
            return replace(result, operation_id="foreign-private-operation")
        return result


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode",
    ["missing", "unavailable", "foreign", "read_missing", "read_foreign", "unavailable_absent"],
)
async def test_inconsistent_or_unavailable_admission_readback_never_grants_effect(
    mode: str,
) -> None:
    fixture = AdmissionFixture()
    journal = AdmissionFaultJournal(mode)
    fixture.access.journal = journal
    fixture.admission = replace(fixture.admission, journal=journal)
    result = await fixture.run()
    assert isinstance(result, Rejection)
    assert "foreign-private-operation" not in repr(result)
    assert fixture.calls == 0
    assert fixture.target.active_lease is None


@pytest.mark.anyio
async def test_existing_admission_releases_losing_guard_before_return() -> None:
    fixture = AdmissionFixture()
    journal = AdmissionFaultJournal("existing")
    fixture.access.journal = journal
    fixture.admission = replace(fixture.admission, journal=journal)
    async with fixture.admission.open(ALICE, fixture.request()) as result:
        assert isinstance(result, Receipt)
        assert fixture.target.active_lease is None
    assert fixture.calls == 0


@pytest.mark.anyio
async def test_receipt_access_is_rechecked_for_retry() -> None:
    fixture = AdmissionFixture()
    original = await fixture.run()
    restricted = replace(ALICE, permitted_scopes=frozenset({"read"}))
    async with fixture.admission.open(restricted, fixture.request()) as result:
        assert isinstance(result, Rejection)
        assert result.diagnostic.code == "access_denied"
        assert isinstance(original, Receipt)
        assert original.operation_id not in repr(result)
    assert fixture.calls == 1


@pytest.mark.anyio
async def test_missing_retry_key_rejected_before_admission() -> None:
    fixture = AdmissionFixture()
    result = await fixture.run(fixture.request(retry_key=None))
    assert isinstance(result, Rejection)
    assert not fixture.journal.owners
    assert fixture.calls == 0


POLICY = DiagnosticPolicy(
    frozenset({("prepared", "unsupported", RecoveryDisposition.CORRECT_REQUEST)}),
    frozenset({("target_support",)}),
)


def eligible_fixture(
    fixture: AdmissionFixture,
    callback: Callable[[str, Principal], Awaitable[Diagnostic | None]],
    policy: DiagnosticPolicy = POLICY,
) -> None:
    binding = replace(
        fixture.command_binding,
        behavior=CommandBehavior(fixture.write, eligibility=callback),
        diagnostic_policy=policy,
    )
    fixture.registry = ImmutableOperationRegistry((binding.bind(),))
    fixture.guards = replace(fixture.guards, registry=fixture.registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)


@pytest.mark.anyio
@pytest.mark.parametrize("unsafe", [False, True])
async def test_eligibility_rejection_is_sanitized_without_admission(unsafe: bool) -> None:
    fixture = AdmissionFixture()
    calls: list[tuple[str, Principal]] = []

    async def check(value: str, principal: Principal) -> Diagnostic:
        calls.append((value, principal))
        assert fixture.target.active_lease is not None
        assert not fixture.journal.owners
        return Diagnostic(
            KEY,
            "prepared",
            "unsupported",
            RecoveryDisposition.CORRECT_REQUEST,
            ("private-name",) if unsafe else ("target_support",),
        )

    eligible_fixture(fixture, check)
    result = await fixture.run()
    assert isinstance(result, Rejection)
    assert result.diagnostic.code == ("rejected" if unsafe else "unsupported")
    assert "private-name" not in repr(result)
    assert calls == [("changed", ALICE)]
    assert not fixture.journal.owners and fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None


@pytest.mark.anyio
async def test_eligibility_runs_once_before_effect_and_never_for_retained_retry() -> None:
    fixture = AdmissionFixture()
    calls: list[str] = []

    async def check(value: str, principal: Principal) -> None:
        assert principal == ALICE and fixture.calls == 0
        assert fixture.target.active_lease is not None
        calls.append(value)

    eligible_fixture(fixture, check)
    first = await fixture.run()
    assert isinstance(first, Receipt)
    assert await fixture.run() == first
    conflict = await fixture.run(fixture.request(payload={"value": "different"}))
    assert isinstance(conflict, Rejection) and conflict.diagnostic.code == "retry_conflict"
    assert calls == ["changed"] and fixture.target.effect_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["lost", "unavailable", "exception", "cancel"])
async def test_eligibility_failure_releases_original_lease_without_acceptance(mode: str) -> None:
    fixture = AdmissionFixture()
    point = Checkpoint()

    async def check(value: str, principal: Principal) -> None:
        assert value == "changed" and principal == ALICE
        lease = fixture.target.active_lease
        assert lease is not None
        if mode == "lost":
            lease.lost = True
        elif mode == "unavailable":
            fixture.target.available = False
        elif mode == "exception":
            raise RuntimeError("private-exception")
        else:
            await point.wait()

    eligible_fixture(fixture, check)
    task = asyncio.create_task(fixture.run())
    if mode == "cancel":
        await point.wait_until_reached()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert isinstance(result, Rejection) and result.diagnostic.code == "service_unavailable"
        assert "private-exception" not in repr(result)
    assert not fixture.journal.owners and fixture.calls == fixture.target.effect_count == 0
    assert fixture.target.active_lease is None


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["coarse", "resource", "health", "stale"])
async def test_eligibility_never_runs_before_shared_guards(mode: str) -> None:
    fixture = AdmissionFixture()

    async def check(value: str, principal: Principal) -> None:
        pytest.fail("Eligibility reached before required guard")

    eligible_fixture(fixture, check)
    principal = ALICE
    request = fixture.request()
    if mode == "coarse":
        principal = replace(ALICE, permitted_scopes=frozenset())
    elif mode == "resource":
        fixture.access.grants = tuple(
            replace(g, resources=frozenset()) for g in fixture.access.grants
        )
    elif mode == "health":
        fixture.results.available = False
    else:
        request = fixture.request(expected_versions=(ExpectedVersion(RESOURCE, "0"),))
    async with fixture.admission.open(principal, request) as result:
        assert isinstance(result, Rejection)
    assert not fixture.journal.owners and fixture.calls == fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_second_retry_lookup_skips_eligibility_for_concurrent_losers() -> None:
    fixture = AdmissionFixture()
    journal = RacingJournal()
    fixture.access.journal = journal
    fixture.admission = replace(fixture.admission, journal=journal)
    checks: list[str] = []

    async def check(value: str, principal: Principal) -> None:
        checks.append(value)
        assert principal == ALICE and fixture.target.active_lease is not None

    eligible_fixture(fixture, check)
    # A work-only command leaves its pins unchanged, so losers acquire a guard
    # and must perform the second retry lookup rather than use conflict recovery.
    fixture.command_binding = replace(
        fixture.command_binding,
        descriptor=replace(fixture.command_binding.descriptor, changes_business_state=False),
    )
    eligible_fixture(fixture, check)
    results = await asyncio.gather(
        *(fixture.run(fixture.request(expected_versions=())) for _ in range(20))
    )
    assert all(isinstance(result, Receipt) for result in results)
    assert len({result.operation_id for result in results if isinstance(result, Receipt)}) == 1
    assert checks == ["changed"] and fixture.calls == fixture.target.effect_count == 1
    assert fixture.target.active_lease is None


@pytest.mark.anyio
async def test_changed_version_during_eligibility_rejects_before_journal_admission() -> None:
    fixture = AdmissionFixture()

    async def check(value: str, principal: Principal) -> None:
        lease = fixture.target.active_lease
        assert lease is not None and principal == ALICE
        # Inject an independent provider version change while its check awaits.
        await fixture.target.apply(RESOURCE, {"value": value}, lease)
        await asyncio.sleep(0)

    eligible_fixture(fixture, check)
    result = await fixture.run()
    assert isinstance(result, Rejection) and result.diagnostic.code == "version_conflict"
    assert not fixture.journal.owners and fixture.calls == 0
    assert fixture.target.active_lease is None
