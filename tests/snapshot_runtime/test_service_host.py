"""Scoped activated capability decisions and the concrete durable host assembler."""

import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.providers import DurableResources, HealthProbe
from craftreport.application import ports
from craftreport.application.capabilities import CapabilityFactory
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.composition import snapshot_host
from craftreport.composition.plugins import ActivationSnapshot
from craftreport.composition.settings import ConfiguredCapability, HostSettings, PreparedCapability
from craftreport.composition.snapshot_host import ActivatedCapabilities
from craftreport.contracts import CapabilityManifest, CapabilityRequirement, CapabilityVersion
from craftreport.interfaces.principal import PrincipalBoundary


def activation() -> ActivationSnapshot:
    manifest = CapabilityManifest(
        "actual",
        "actual-package",
        "9.0",
        ">=1",
        (CapabilityVersion("published", "1.02.0"),),
        (),
        {},
        (),
        "digest",
    )
    return ActivationSnapshot(ImmutableOperationRegistry(()), (manifest,))


async def observed() -> None:
    await asyncio.sleep(0)


def test_exact_provided_version_mode_denial_and_permanent_binding() -> None:
    async def exercise() -> None:
        resolver = snapshot_host.ActivatedCapabilities(observed)
        requirement = CapabilityRequirement("published", ">=1,<2")
        assert isinstance(await resolver.check((), ()), ports.ServiceUnavailable)
        async with resolver.bind(activation()):
            supported = await resolver.check((requirement,), ())
            assert supported == ports.CapabilitiesSupported(
                (CapabilityVersion("published", "1.02.0"),)
            )
            for invalid in (
                replace(requirement, target_mode="browser"),
                replace(requirement, version_range=">=2"),
                replace(requirement, identity="missing"),
                replace(requirement, version_range="invalid"),
            ):
                assert await resolver.check((invalid,), ()) == ports.CapabilitiesUnsupported(
                    (invalid,)
                )
            with pytest.raises(ValueError):
                async with resolver.bind(activation()):
                    pytest.fail("overlapping binding")
        assert isinstance(await resolver.check((), ()), ports.ServiceUnavailable)
        with pytest.raises(ValueError):
            async with resolver.bind(activation()):
                pytest.fail("second binding")

    asyncio.run(exercise())


def test_failed_entry_burns_binder_and_close_during_probe_cannot_succeed() -> None:
    async def exercise() -> None:
        resolver = snapshot_host.ActivatedCapabilities(observed)
        manifest = activation().manifests[0]
        invalid = ActivationSnapshot(ImmutableOperationRegistry(()), (manifest, manifest))
        for candidate in (invalid, activation()):
            with pytest.raises(ValueError):
                async with resolver.bind(candidate):
                    pytest.fail("failed binding revived")
        entered, release = asyncio.Event(), asyncio.Event()

        async def probe() -> None:
            entered.set()
            await release.wait()

        resolver = snapshot_host.ActivatedCapabilities(probe)
        async with resolver.bind(activation()):
            check = asyncio.create_task(resolver.check((), ()))
            await entered.wait()
        release.set()
        assert isinstance(await check, ports.ServiceUnavailable)

    asyncio.run(exercise())


@pytest.mark.parametrize("mismatch", [None, "scope", "epoch", "profile", "exception"])
def test_assembler_real_activation_mandatory_binder_and_owned_database_close(
    tmp_path: Path, mismatch: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolvers: list[ActivatedCapabilities] = []

    def capture(probe: HealthProbe) -> ActivatedCapabilities:
        resolver = ActivatedCapabilities(probe)
        resolvers.append(resolver)
        return resolver

    monkeypatch.setattr(snapshot_host, "ActivatedCapabilities", capture)

    async def exercise() -> None:
        seen: list[Database] = []

        def configure(database: Database, resources: DurableResources) -> HostSettings:
            assert resources.database is database
            seen.append(database)
            if mismatch == "exception":
                raise ValueError("settings failed")
            return HostSettings(
                "127.0.0.1",
                ("127.0.0.1",),
                (),
                "wrong" if mismatch == "epoch" else database.deployment.epoch,
                "wrong" if mismatch == "profile" else database.deployment.retention_profile,
                PrincipalBoundary("wrong" if mismatch == "scope" else database.deployment.identity),
            )

        fingerprint = CanonicalFingerprint()
        path = tmp_path / "host.sqlite3"
        context = snapshot_host.open_snapshot_application(
            path,
            "deployment-a",
            configure,
            codec=snapshot_codec(),
            fingerprint=fingerprint,
            normalization_policy=fingerprint.policy,
            owner_probes={"access": observed, "capabilities": observed},
        )
        if mismatch:
            with pytest.raises(ValueError):
                async with context:
                    pytest.fail("invalid configuration published")
        else:
            async with context:
                assert await resolvers[0].check((), ()) == ports.CapabilitiesSupported(())
            assert isinstance(await resolvers[0].check((), ()), ports.ServiceUnavailable)
        assert len(seen) == 1
        reopened = Database(path, "deployment-a")
        await reopened.close()

    asyncio.run(exercise())


def test_actual_installed_metadata_entry_point_is_activated_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = tmp_path / "craftreport_service_fixture-9.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: craftreport-service-fixture\nVersion: 9.0\n"
    )
    (metadata / "entry_points.txt").write_text(
        "[craftreport.capabilities]\nfixture = service_installed_fixture:factory\n"
    )
    (tmp_path / "service_installed_fixture.py").write_text("""
from contextlib import asynccontextmanager
from pathlib import Path
from craftreport.application.capabilities import CapabilityInstance
from craftreport.contracts import CapabilityManifest, CapabilityVersion
class Factory:
    def describe(self):
        return CapabilityManifest(
            "installed-fixture", "craftreport-service-fixture", "9.0", ">=1",
            (CapabilityVersion("provided.fixture", "1.02.0"),), (), {}, (), "fixture-digest")
    @asynccontextmanager
    async def open(self, services, settings):
        marker = Path(__file__).with_suffix(".state")
        if marker.exists():
            raise RuntimeError("second activation")
        marker.write_text("open")
        try:
            yield CapabilityInstance((), self.close)
        finally:
            await self.close()
    async def close(self):
        Path(__file__).with_suffix(".state").write_text("closed")
factory = Factory()
""")
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    resolvers: list[ActivatedCapabilities] = []

    def capture(probe: HealthProbe) -> ActivatedCapabilities:
        resolver = ActivatedCapabilities(probe)
        resolvers.append(resolver)
        return resolver

    monkeypatch.setattr(snapshot_host, "ActivatedCapabilities", capture)

    async def probe() -> None:
        assert (tmp_path / "service_installed_fixture.state").read_text() == "open"

    def prepare(loaded: object) -> PreparedCapability:
        factory = cast(CapabilityFactory[None, None], loaded)
        return PreparedCapability(factory.describe(), lambda: factory.open(None, None))

    def configure(database: Database, resources: DurableResources) -> HostSettings:
        return HostSettings(
            "127.0.0.1",
            ("127.0.0.1",),
            (),
            database.deployment.epoch,
            database.deployment.retention_profile,
            PrincipalBoundary(database.deployment.identity),
            (ConfiguredCapability("craftreport-service-fixture", "fixture", prepare),),
        )

    async def exercise() -> None:
        fingerprint = CanonicalFingerprint()
        async with snapshot_host.open_snapshot_application(
            tmp_path / "installed.sqlite3",
            "deployment-a",
            configure,
            codec=snapshot_codec(),
            fingerprint=fingerprint,
            normalization_policy=fingerprint.policy,
            owner_probes={"access": probe, "capabilities": probe},
        ):
            supported = await resolvers[0].check(
                (CapabilityRequirement("provided.fixture", ">=1,<2"),), ()
            )
            assert supported == ports.CapabilitiesSupported(
                (CapabilityVersion("provided.fixture", "1.02.0"),)
            )
        assert (tmp_path / "service_installed_fixture.state").read_text() == "closed"
        assert isinstance(await resolvers[0].check((), ()), ports.ServiceUnavailable)

    asyncio.run(exercise())
