"""Assembly fixtures replace installed-package lookup only, retaining all runtime wiring."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from fixture_admission import AdmissionFixture
from fixture_dispatch import ALICE
from fixture_execution import FixtureHandoffs

from craftreport.application.capabilities import CapabilityInstance
from craftreport.application.registry import BoundOperation
from craftreport.composition import plugins
from craftreport.composition.settings import (
    ConfiguredCapability,
    GuaranteeProviders,
    HostSettings,
    PreparedCapability,
)
from craftreport.contracts import CapabilityManifest
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary


class HostFixture:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.fixture = AdmissionFixture()
        self.events: list[str] = []
        self.handoffs = FixtureHandoffs()
        self.fail_open = False
        self.fail_close = False
        boundary, credentials = PrincipalBoundary.conformance(
            "127.0.0.1",
            "deployment",
            (AuthenticatedIdentity(ALICE.subject, ALICE.permitted_scopes),),
            self.fixture.access,
        )
        self.token = credentials[0].token
        self.manifest = CapabilityManifest(
            "fixture",
            "fixture-package",
            "1.0.0",
            ">=1",
            (),
            (),
            {},
            self.fixture.registry.describe(),
            "fixture-digest",
        )
        self.selection = ConfiguredCapability("fixture-package", "fixture", self.prepare)
        self.settings = HostSettings(
            "127.0.0.1",
            ("127.0.0.1:8000",),
            ("http://127.0.0.1:8000",),
            self.fixture.journal.epoch,
            self.fixture.journal.retention_profile,
            boundary,
            (self.selection,),
        )
        monkeypatch.setattr(plugins, "_load", self.prepare)

    def prepare(self, loaded: object) -> PreparedCapability:
        return PreparedCapability(self.manifest, self.plugin)

    async def close(self) -> None:
        self.events.append("plugin-close")
        if self.fail_close:
            raise RuntimeError("plugin-close-failure")

    @asynccontextmanager
    async def plugin(self) -> AsyncGenerator[CapabilityInstance]:
        self.events.append("plugin-open")
        if self.fail_open:
            raise RuntimeError("plugin-open-failure")
        try:
            yield CapabilityInstance(self.bindings(), self.close)
        finally:
            await self.close()

    def bindings(self) -> tuple[BoundOperation, ...]:
        bound = self.fixture.registry.resolve("fixture.write", "1")
        assert bound is not None
        return (bound,)

    @asynccontextmanager
    async def providers(self) -> AsyncGenerator[GuaranteeProviders]:
        self.events.append("providers-open")
        fixture = self.fixture
        try:
            yield GuaranteeProviders(
                fixture.journal,
                fixture.target,
                fixture.evidence,
                fixture.capabilities,
                fixture.target,
                fixture.target,
                fixture.results,
                self.handoffs,
                fixture.health,
            )
        finally:
            self.events.append("providers-close")
