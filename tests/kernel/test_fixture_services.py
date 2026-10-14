"""Access, exact evidence, capability and independent synthetic target conformance."""

import asyncio
from dataclasses import replace

import pytest
from fixture_controls import Checkpoint
from fixture_journal import FixtureJournal
from fixture_services import (
    AccessGrant,
    CapabilitySupport,
    FixtureAccessPolicy,
    FixtureCapabilities,
    FixtureEvidence,
)
from fixture_target import SyntheticTarget

from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CapabilityRequirement,
    CapabilityVersion,
    CommandIntent,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    OperationKey,
    Principal,
    ResourceRef,
    RetryKey,
    StageState,
)

RESOURCE = ResourceRef("fixture", "target")
PIN = ExpectedVersion(RESOURCE, "1")
KEY = OperationKey("fixture.set", "1")


def test_guarded_effect_readback_and_stale_versions() -> None:
    async def run() -> None:
        target = SyntheticTarget({RESOURCE: {"value": 0}})
        guard: ports.ExecutionGuard = target
        effects: ports.ResourceEffects = target
        reader: ports.ResourceReader = target
        async with guard.acquire((PIN,)) as lease:
            result = await effects.apply(RESOURCE, {"value": 42}, lease)
            assert isinstance(result, ports.ResourceEffect)
            assert result.effect is EffectDisposition.APPLIED
            assert result.versions == (replace(PIN, version="2"),)
        assert isinstance(await lease.assert_current(), ports.GuardLost)
        assert isinstance(await target.apply(RESOURCE, {"value": 99}, lease), ports.GuardLost)
        assert await reader.read(RESOURCE) == ports.ResourceSnapshot(
            replace(PIN, version="2"), {"value": 42}
        )
        with pytest.raises(ports.GuardAcquisitionError) as error:
            async with guard.acquire((PIN,)):
                pytest.fail("stale lease granted")
        assert isinstance(error.value.reason, ports.VersionConflict)
        assert target.effect_count == 1
        assert target.active_lease is None

    asyncio.run(run())


def test_guard_loss_during_barrier_and_cancellation_release() -> None:
    async def run() -> None:
        target = SyntheticTarget({RESOURCE: {"value": 0}})
        checkpoint = Checkpoint()
        target.before_effect = checkpoint
        async with target.acquire((PIN,)) as lease:
            task = asyncio.create_task(target.apply(RESOURCE, {"value": 1}, lease))
            await checkpoint.wait_until_reached()
            assert target.active_lease is not None
            target.active_lease.lost = True
            checkpoint.release()
            assert isinstance(await task, ports.GuardLost)
        assert target.effect_count == 0
        target.before_effect = Checkpoint()

        async def writer() -> None:
            async with target.acquire((PIN,)) as lease:
                await target.apply(RESOURCE, {"value": 2}, lease)

        writer_task = asyncio.create_task(writer())
        await target.before_effect.wait_until_reached()
        writer_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer_task
        assert target.before_effect.waiters == 0
        assert target.active_lease is None
        async with target.acquire((PIN,)):
            pass

    asyncio.run(run())


def test_interrupted_effect_is_observable_and_barriers_are_bounded() -> None:
    async def run() -> None:
        target = SyntheticTarget({RESOURCE: {"value": 0}})
        target.interrupt_after_effect = True
        async with target.acquire((PIN,)) as lease:
            result = await target.apply(RESOURCE, {"value": 7}, lease)
        assert (
            isinstance(result, ports.ResourceEffect) and result.effect is EffectDisposition.UNKNOWN
        )
        assert await target.read(RESOURCE) == ports.ResourceSnapshot(
            replace(PIN, version="2"), {"value": 7}
        )
        assert target.effect_count == 1
        checkpoint = Checkpoint(timeout=0.001)
        with pytest.raises(TimeoutError):
            await checkpoint.wait()
        assert checkpoint.waiters == 0
        target.available = False
        with pytest.raises(ports.GuardAcquisitionError) as error:
            async with target.acquire(()):
                pytest.fail("unavailable lease granted")
        assert isinstance(error.value.reason, ports.ServiceUnavailable)
        assert isinstance(await target.read(RESOURCE), ports.ServiceUnavailable)

    asyncio.run(run())


def test_explicit_authorization_scopes_and_ownership() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        principal = Principal("deployment", "alice", frozenset({"write", "catalog", "inspect"}))
        grant = AccessGrant(
            "deployment", "alice", principal.permitted_scopes, frozenset({RESOURCE}), True
        )
        policy: ports.AccessPolicy = FixtureAccessPolicy(journal, (grant,), {KEY: "write"})
        assert isinstance(
            await policy.authorize(principal, ports.CatalogAccess()), ports.AccessAllowed
        )
        assert isinstance(
            await policy.authorize(principal, ports.OperationAccess(KEY, (RESOURCE,))),
            ports.AccessAllowed,
        )
        for caller, action in (
            (replace(principal, subject="bob"), ports.CatalogAccess()),
            (replace(principal, deployment_scope="other"), ports.CatalogAccess()),
            (replace(principal, permitted_scopes=frozenset()), ports.OperationAccess(KEY)),
            (principal, ports.OperationAccess(KEY, (ResourceRef("private", "secret"),))),
            (principal, ports.ReceiptAccess("unknown")),
        ):
            assert isinstance(await policy.authorize(caller, action), ports.AccessDenied)
        admitted = await journal.admit(
            CommandIntent(
                RetryKey("deployment", "alice", KEY, "retry"),
                "hash",
                "v1",
                "correlation",
                (),
                (RESOURCE,),
                (PIN,),
            )
        )
        assert isinstance(admitted, ports.Admitted)
        own = ports.ReceiptAccess(admitted.receipt.operation_id)
        assert isinstance(await policy.authorize(principal, own), ports.AccessAllowed)
        assert isinstance(
            await policy.authorize(replace(principal, subject="bob"), own), ports.AccessDenied
        )
        revoked = FixtureAccessPolicy(
            journal, (replace(grant, resources=frozenset()),), {KEY: "write"}
        )
        assert isinstance(await revoked.authorize(principal, own), ports.AccessDenied)

    asyncio.run(run())


def test_capability_versions_and_modes_resolve_exact_requirements() -> None:
    async def run() -> None:
        version = CapabilityVersion("fixture", "1.2.3")
        provider = FixtureCapabilities(
            (CapabilitySupport(version, frozenset({"synthetic"})),), {RESOURCE: "synthetic"}
        )
        resolver: ports.CapabilityResolver = provider
        requirement = CapabilityRequirement("fixture", ">=1.2,<2", "synthetic")
        assert await resolver.check((requirement,), (RESOURCE,)) == ports.CapabilitiesSupported(
            (version,)
        )
        for req in (
            replace(requirement, version_range=">=2"),
            replace(requirement, identity="absent"),
            replace(requirement, target_mode="browser"),
            replace(requirement, version_range="invalid"),
        ):
            assert await resolver.check((req,), (RESOURCE,)) == ports.CapabilitiesUnsupported(
                (req,)
            )
        assert isinstance(
            await resolver.check((requirement,), (ResourceRef("fixture", "absent"),)),
            ports.CapabilitiesUnsupported,
        )
        provider.available = False
        assert isinstance(
            await resolver.check((requirement,), (RESOURCE,)), ports.ServiceUnavailable
        )

    asyncio.run(run())


def test_evidence_distinctions_and_exact_reference_pins() -> None:
    async def run() -> None:
        ref = EvidenceRef("proof", "synthetic", "operation", KEY, (PIN,), "digest")
        inaccessible = replace(ref, identity="restricted")
        missing = replace(ref, content_digest="wrong")
        statuses = (
            EvidenceStatus(ref, Availability.AVAILABLE, StageState.PASSED),
            EvidenceStatus(inaccessible, Availability.INACCESSIBLE),
        )
        evidence = FixtureEvidence(statuses)
        reader: ports.EvidenceReader = evidence
        assert await reader.inspect((missing, inaccessible, ref)) == (
            EvidenceStatus(missing, Availability.MISSING),
            statuses[1],
            statuses[0],
        )
        evidence.available = False
        assert [s.availability for s in await reader.inspect((ref, missing))] == [
            Availability.UNAVAILABLE
        ] * 2

    asyncio.run(run())


def test_cancelled_waiter_and_reentrant_timeout_preserve_authority() -> None:
    async def run() -> None:
        other = ResourceRef("fixture", "other")
        other_pin = ExpectedVersion(other, "1")
        target = SyntheticTarget({RESOURCE: {"value": 0}, other: {"value": 1}})
        entered = asyncio.Event()

        async def waiter() -> None:
            entered.set()
            async with target.acquire((PIN, other_pin)):
                pytest.fail("waiter entered occupied guard")

        async with target.acquire((other_pin, PIN)) as lease:
            assert lease.authoritative_versions == (other_pin, PIN)
            task = asyncio.create_task(waiter())
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert isinstance(await lease.assert_current(), ports.GuardCurrent)
            target.acquisition_timeout = 0.001
            with pytest.raises(ports.GuardAcquisitionError) as error:
                async with target.acquire(()):
                    pytest.fail("reentrant acquisition")
            assert isinstance(error.value.reason, ports.ServiceUnavailable)
            assert isinstance(await lease.assert_current(), ports.GuardCurrent)
        async with target.acquire((PIN, other_pin)):
            pass
        absent = ResourceRef("fixture", "absent")
        assert isinstance(await target.read(absent), ports.Missing)
        with pytest.raises(ports.GuardAcquisitionError) as error:
            async with target.acquire((ExpectedVersion(absent, "1"),)):
                pytest.fail("missing precondition admitted")
        assert error.value.reason == ports.VersionConflict((ExpectedVersion(absent, "1"),), ())

    asyncio.run(run())


def test_post_effect_cancellation_keeps_independent_state_and_releases_guard() -> None:
    async def run() -> None:
        target = SyntheticTarget({RESOURCE: {"value": 0}})
        checkpoint = Checkpoint()
        target.after_effect = checkpoint

        async def writer() -> None:
            async with target.acquire((PIN,)) as lease:
                await target.apply(RESOURCE, {"value": 8}, lease)

        task = asyncio.create_task(writer())
        await checkpoint.wait_until_reached()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert checkpoint.waiters == 0 and target.active_lease is None
        assert target.effect_count == 1
        assert await target.read(RESOURCE) == ports.ResourceSnapshot(
            replace(PIN, version="2"), {"value": 8}
        )
        async with target.acquire((replace(PIN, version="2"),)):
            pass

    asyncio.run(run())


def test_access_outage_and_forged_guard_block_dependent_work() -> None:
    async def run() -> None:
        journal = FixtureJournal()
        principal = Principal("deployment", "alice", frozenset({"inspect"}))
        policy = FixtureAccessPolicy(
            journal,
            (AccessGrant("deployment", "alice", principal.permitted_scopes, frozenset()),),
            {},
        )
        policy.available = False
        assert isinstance(
            await policy.authorize(principal, ports.CatalogAccess()), ports.ServiceUnavailable
        )
        policy.available = True
        journal.available = False
        assert isinstance(
            await policy.authorize(principal, ports.ReceiptAccess("owned")),
            ports.ServiceUnavailable,
        )
        target = SyntheticTarget({RESOURCE: {"value": 0}})
        other = SyntheticTarget({RESOURCE: {"value": 0}})
        async with other.acquire((PIN,)) as foreign:
            assert isinstance(await target.apply(RESOURCE, {"value": 9}, foreign), ports.GuardLost)
        async with target.acquire((PIN,)) as lease:
            target.available = False
            assert isinstance(
                await target.apply(RESOURCE, {"value": 9}, lease), ports.ServiceUnavailable
            )
        assert target.effect_count == 0

    asyncio.run(run())
