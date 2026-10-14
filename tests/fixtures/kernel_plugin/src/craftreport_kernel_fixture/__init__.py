"""Independently installed synthetic fixture; trusted code, no sandbox claim."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path

from craftreport.application.capabilities import CapabilityFactory, CapabilityInstance
from craftreport.contracts import CapabilityManifest, CapabilityVersion

from .lifecycle import FixtureServices, ResourceScope
from .models import SETTINGS, Settings
from .operations import Operations, descriptors

PACKAGE = "craftreport-kernel-fixture"
IDENTITY = "synthetic"
NAMESPACE = "synthetic"
CORE_RANGE = ">=1.0,<2.0"
RESOURCE_KIND = "synthetic"


def implementation_digest() -> str:
    """Hash exact installed Python bytes with unambiguous relative names and lengths."""
    digest = sha256()
    root = Path(__file__).parent
    for path in sorted(root.rglob("*.py")):
        content = path.read_bytes()
        name = path.relative_to(root).as_posix().encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    return "sha256:" + digest.hexdigest()


class FixtureFactory:
    def __init__(self, boundary_probe: bool = False) -> None:
        self.boundary_probe = boundary_probe

    def describe(self) -> CapabilityManifest:
        return CapabilityManifest(
            IDENTITY,
            PACKAGE,
            distribution(PACKAGE).version,
            CORE_RANGE,
            (CapabilityVersion(IDENTITY, "1.0.0"),),
            (),
            SETTINGS.schema(),
            descriptors(NAMESPACE, RESOURCE_KIND, self.boundary_probe),
            implementation_digest(),
        )

    @asynccontextmanager
    async def open(
        self, services: FixtureServices, settings: Settings
    ) -> AsyncGenerator[CapabilityInstance]:
        settings = SETTINGS.decode(SETTINGS.encode(settings))
        if settings.resource_kind != RESOURCE_KIND:
            raise ValueError("Settings resource kind must match manifest")
        scope = ResourceScope(IDENTITY, services, settings.fail_close)
        try:
            if settings.fail_open:
                services.lifecycle.record(IDENTITY, "open_failed")
                raise RuntimeError("Synthetic initialization failure after acquire")
            instance = CapabilityInstance(
                Operations(NAMESPACE, settings.resource_kind).bindings(self.boundary_probe),
                scope.close,
            )
            services.lifecycle.record(IDENTITY, "opened")
            yield instance
        finally:
            await scope.close()


def factory(boundary_probe: bool = False) -> CapabilityFactory[FixtureServices, Settings]:
    return FixtureFactory(boundary_probe)
