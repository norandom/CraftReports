"""Host snapshots retain activation metadata and advertise bounded execution."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import FrozenInstanceError, replace

import pytest
from fixture_dispatch import ALICE, BOB, DispatchFixture

from craftreport.adapters.transport_wire import encode_catalog
from craftreport.application.capabilities import CapabilityInstance
from craftreport.application.dispatch import Inspection
from craftreport.composition import plugins
from craftreport.composition.settings import ConfiguredCapability, PreparedCapability
from craftreport.contracts import CapabilityManifest, Catalog
from craftreport.contracts.capabilities import ExecutionLimits


def test_activation_snapshot_retains_prepared_manifest_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_activation_scenario(monkeypatch))


async def _activation_scenario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    manifest = CapabilityManifest("demo", "demo", "1.0", ">=1", (), (), {}, (), "digest")

    async def close() -> None:
        events.append("closed")

    @asynccontextmanager
    async def opened() -> AsyncGenerator[CapabilityInstance]:
        events.append("opened")
        try:
            yield CapabilityInstance((), close)
        finally:
            await close()

    def prepare(loaded: object) -> PreparedCapability:
        events.append("described")
        return PreparedCapability(manifest, opened)

    def load(selection: ConfiguredCapability) -> PreparedCapability:
        events.append("loaded")
        return selection.prepare(object())

    monkeypatch.setattr(plugins, "_load", load)
    selection = ConfiguredCapability("demo", "demo", prepare)
    async with plugins.activate_snapshot([selection]) as snapshot:
        assert snapshot.manifests == (manifest,)
        assert snapshot.manifests[0] is manifest
        assert snapshot.registry.describe() == ()
        assert events == ["loaded", "described", "opened"]
        with pytest.raises(FrozenInstanceError):
            setattr(snapshot, "manifests", ())
    assert events == ["loaded", "described", "opened", "closed"]
    events.clear()
    async with plugins.activate([selection]) as registry:
        assert registry.describe() == ()
    assert events == ["loaded", "described", "opened", "closed"]


def test_inspection_preserves_execution_limits_when_filtering_catalog() -> None:
    async def scenario() -> None:
        fixture = DispatchFixture()
        limits = ExecutionLimits(3, 0.5, 2.0)
        inspection = Inspection(
            replace(fixture.catalog, execution_limits=limits),
            fixture.access,
            fixture.journal,
            fixture.results,
            fixture.evidence,
        )
        for principal in (ALICE, BOB):
            assert (await inspection.catalog(principal)).execution_limits is limits
        assert (await inspection.catalog(BOB)).operations == ()

    asyncio.run(scenario())


def test_catalog_execution_limits_serialization() -> None:
    limits = ExecutionLimits(3, 0.5, 2.0)
    catalog = Catalog((), (), "epoch", "memory", execution_limits=limits)
    assert encode_catalog(catalog)["execution_limits"] == {
        "capacity": 3,
        "response_seconds": 0.5,
        "shutdown_seconds": 2.0,
    }
    assert "execution_limits" not in encode_catalog(Catalog((), (), "epoch", "memory"))
    assert ExecutionLimits() == ExecutionLimits(16, 5.0, 10.0)
    with pytest.raises(FrozenInstanceError):
        setattr(limits, "capacity", 5)


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_execution_capacity(capacity: int) -> None:
    with pytest.raises(ValueError):
        ExecutionLimits(capacity=capacity)


@pytest.mark.parametrize("seconds", [0.0, -1.0, float("inf"), float("nan")])
def test_invalid_execution_timing(seconds: float) -> None:
    with pytest.raises(ValueError):
        ExecutionLimits(response_seconds=seconds)
    with pytest.raises(ValueError):
        ExecutionLimits(shutdown_seconds=seconds)
