"""Executed under an isolated installed interpreter; providers are explicitly supplied.

This is an author-contract probe, not facade/activation or reporting conformance.
"""

import asyncio
import sys
from dataclasses import replace
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path

import craftreport_kernel_fixture
from craftreport_kernel_fixture import factory
from craftreport_kernel_fixture.lifecycle import FixtureServices
from craftreport_kernel_fixture.models import SETTINGS, Settings
from fixture_services import FixtureCapabilities, FixtureEvidence
from fixture_target import SyntheticTarget

import craftreport
from craftreport.adapters.canonical import WireFailure
from craftreport.application import ports
from craftreport.application.registry import (
    BoundOperation,
    ImmutableOperationRegistry,
    PreparedCommand,
    PreparedQuery,
)
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Principal,
    ResourceRef,
    StageState,
)


class Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def record(self, capability: str, event: str) -> None:
        self.events.append((capability, event))

    def names(self) -> list[str]:
        return [event for _, event in self.events]


def assert_installed() -> None:
    for module in (craftreport, craftreport_kernel_fixture):
        assert module.__file__ is not None
        assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    (point,) = distribution("craftreport-kernel-fixture").entry_points
    assert point.load() is factory


async def lifecycle() -> None:
    assert_installed()
    observer = Events()
    services = FixtureServices(observer)
    capability = factory()
    manifest = capability.describe()
    assert observer.events == []
    settings = SETTINGS.decode({"resource_kind": "synthetic"})
    assert manifest.settings_schema == SETTINGS.schema()
    async with capability.open(services, settings) as instance:
        registry = ImmutableOperationRegistry(instance.bindings, manifest.operations)
        assert len(registry.describe()) == 2
        assert observer.names() == ["acquired", "opened"]
        await instance.aclose()
        await instance.aclose()
    assert observer.names() == ["acquired", "opened", "released"]
    for invalid in (
        {},
        {"resource_kind": "synthetic", "fail_open": "true"},
        {"resource_kind": "synthetic", "secret": "hidden"},
    ):
        try:
            SETTINGS.decode(invalid)
        except WireFailure:
            pass
        else:
            raise AssertionError("Invalid settings accepted")
    assert observer.names() == ["acquired", "opened", "released"]


async def lifecycle_failures() -> None:
    for settings, expected in (
        (Settings("synthetic", fail_open=True), ["acquired", "open_failed", "released"]),
        (
            Settings("synthetic", fail_close=True),
            ["acquired", "opened", "released", "close_failed"],
        ),
    ):
        observer = Events()
        try:
            async with factory().open(FixtureServices(observer), settings):
                pass
        except RuntimeError:
            pass
        else:
            raise AssertionError("Lifecycle failure was suppressed")
        assert observer.names() == expected
    observer = Events()
    try:
        async with factory().open(FixtureServices(observer), Settings("wrong")):
            raise AssertionError("Mismatched settings opened")
    except ValueError:
        pass
    assert observer.events == []


async def lifecycle_cancellation() -> None:
    observer = Events()
    try:
        async with factory().open(FixtureServices(observer), Settings("synthetic")):
            raise asyncio.CancelledError
    except asyncio.CancelledError:
        pass
    assert observer.names() == ["acquired", "opened", "released"]


class ReadbackEffects:
    """Retain evidence only after inspecting the separate synthetic target state."""

    def __init__(self, target: SyntheticTarget, evidence: FixtureEvidence) -> None:
        self.target = target
        self.evidence = evidence

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        observed = await self.target.apply(resource, change, guard)
        if not isinstance(observed, ports.ResourceEffect):
            return observed
        if observed.effect is not EffectDisposition.APPLIED:
            return observed
        snapshot = await self.target.read(resource)
        assert isinstance(snapshot, ports.ResourceSnapshot)
        assert snapshot.content == change
        reference = EvidenceRef(
            "fixture-readback",
            "synthetic-temporary",
            "fixture-command",
            OperationKey("synthetic.write", "1"),
            observed.versions,
            sha256(str(snapshot.content["value"]).encode()).hexdigest(),
        )
        self.evidence.retain(EvidenceStatus(reference, Availability.AVAILABLE))
        return replace(observed, evidence=(reference,))


async def operations() -> None:
    assert_installed()
    resource = ResourceRef("synthetic", "target-1")
    target = SyntheticTarget({resource: {"value": "before"}})
    evidence = FixtureEvidence()
    reads = ports.ReadServices(evidence, FixtureCapabilities((), {}), target)
    services = ports.CommandServices(reads, ReadbackEffects(target, evidence))
    principal = Principal("fixture", "author", frozenset())
    async with factory().open(FixtureServices(Events()), Settings("synthetic")) as instance:
        write, read = instance.bindings
        command = write.prepare({"resource": "target-1", "value": "after"})
        query = read.prepare({"resource": "target-1"})
        assert isinstance(command, PreparedCommand) and isinstance(query, PreparedQuery)
        assert command.resources == (resource,)
        async with target.acquire((ExpectedVersion(resource, "1"),)) as guard:
            result = await command.invoke(
                ports.CommandContext("fixture-command", principal, guard, services)
            )
        assert result.effect is EffectDisposition.APPLIED
        assert result.encode_result() == {"value": "after", "version": "2"}
        assert result.stages[0].state is StageState.PASSED
        statuses = await evidence.inspect(result.evidence)
        assert len(statuses) == 1 and statuses[0].availability is Availability.AVAILABLE
        before = await target.read(resource)
        response = await query.invoke(ports.ReadContext("fixture-query", principal, reads))
        assert response.encode_result() == {"value": "after", "version": "2"}
        assert before == await target.read(resource)
        assert target.effect_count == 1
        assert not hasattr(reads, "effects")
        await unresolved(write, target, reads, principal)


async def unresolved(
    write: BoundOperation,
    target: SyntheticTarget,
    reads: ports.ReadServices,
    principal: Principal,
) -> None:
    command = write.prepare({"resource": "target-1", "value": "uncertain"})
    assert isinstance(command, PreparedCommand)
    target.interrupt_after_effect = True
    async with target.acquire(()) as guard:
        observed = await command.invoke(
            ports.CommandContext("unknown", principal, guard, ports.CommandServices(reads, target))
        )
    assert observed.effect is EffectDisposition.UNKNOWN
    assert observed.stages[0].state is StageState.PENDING
    assert observed.evidence == ()
    count = target.effect_count
    try:
        write.prepare({"resource": "target-1", "value": 42})
    except WireFailure:
        pass
    else:
        raise AssertionError("Invalid typed request admitted")
    assert count == target.effect_count


async def main() -> None:
    await lifecycle()
    await lifecycle_failures()
    await lifecycle_cancellation()
    await operations()
    print("installed author contract, lifecycle and synthetic readback verified")


if __name__ == "__main__":
    asyncio.run(main())
