"""Capability packaging and lifecycle factory for GridCraft web reports."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path

from craftreport.application.capabilities import CapabilityInstance
from craftreport.contracts import (
    CapabilityManifest,
    CapabilityVersion,
)
from craftreport_gridcraft.codecs import settings_codec
from craftreport_gridcraft.operations import (
    AppOperations,
    app_descriptors,
    app_operations,
)
from craftreport_gridcraft.values import AppSettings

PACKAGE = "craftreport-gridcraft"
IDENTITY = "gridcraft.web_reports"
CORE_RANGE = ">=0.1.0,<1.0.0"


def implementation_digest() -> str:
    digest = sha256()
    root = Path(__file__).parent
    for path in sorted(root.rglob("*.py")):
        n, c = path.relative_to(root).as_posix().encode(), path.read_bytes()
        digest.update(len(n).to_bytes(8, "big") + n + len(c).to_bytes(8, "big") + c)
    return "sha256:" + digest.hexdigest()


class GridCraftFactory:
    def __init__(self, services: AppOperations | None = None) -> None:
        self._services = services

    def describe(self) -> CapabilityManifest:
        return CapabilityManifest(
            IDENTITY,
            PACKAGE,
            distribution(PACKAGE).version,
            CORE_RANGE,
            (CapabilityVersion(IDENTITY, "1.0.0"),),
            (),
            settings_codec().schema(),
            app_descriptors(),
            implementation_digest(),
        )

    @asynccontextmanager
    async def open(
        self, services: AppOperations, settings: AppSettings
    ) -> AsyncGenerator[CapabilityInstance]:
        settings_codec().decode(settings_codec().encode(settings))
        ops = self._services or services

        async def close() -> None:
            pass

        yield CapabilityInstance(app_operations(ops), close)


def gridcraft_factory() -> GridCraftFactory:
    return GridCraftFactory()
