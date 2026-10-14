"""Single-event-loop, temporary synthetic state and guard authority, never a remote fence."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager

from fixture_controls import Checkpoint

from craftreport.application import ports
from craftreport.contracts import EffectDisposition, ExpectedVersion, JsonObject, ResourceRef


class FixtureLease:
    def __init__(self, target: SyntheticTarget, versions: ports.Preconditions) -> None:
        self.target = target
        self.authoritative_versions = versions
        self.active = True
        self.lost = False

    async def assert_current(self) -> ports.GuardCheck:
        if not self.active or self.lost:
            return ports.GuardLost()
        if not self.target.available:
            return ports.ServiceUnavailable("target")
        actual = self.target.versions(self.authoritative_versions)
        if actual != self.authoritative_versions:
            return ports.VersionConflict(self.authoritative_versions, actual)
        return ports.GuardCurrent()


class SyntheticTarget:
    """The target owns business state; read inspects it independently of effects/receipts.

    All writes require this target's currently active lease. One lock protects the
    entire synthetic target, even for empty preconditions. Nothing survives restart.
    Acquisition is bounded and non-reentrant; lock timeout is structured unavailable.
    """

    def __init__(self, initial: Mapping[ResourceRef, JsonObject]) -> None:
        self._state = {
            resource: ports.ResourceSnapshot(ExpectedVersion(resource, "1"), value)
            for resource, value in initial.items()
        }
        self._lock = asyncio.Lock()
        self.available = True
        self.effect_count = 0
        self.before_effect: Checkpoint | None = None
        self.after_effect: Checkpoint | None = None
        self.interrupt_after_effect = False
        self.active_lease: FixtureLease | None = None
        self.acquisition_timeout = 2.0

    def versions(self, requested: ports.Preconditions) -> ports.Preconditions:
        return tuple(
            self._state[pin.resource].version for pin in requested if pin.resource in self._state
        )

    @asynccontextmanager
    async def acquire(self, preconditions: ports.Preconditions) -> AsyncGenerator[ports.GuardLease]:
        try:
            async with asyncio.timeout(self.acquisition_timeout):
                await self._lock.acquire()
        except TimeoutError as error:
            raise ports.GuardAcquisitionError(ports.ServiceUnavailable("guard")) from error
        try:
            if not self.available:
                raise ports.GuardAcquisitionError(ports.ServiceUnavailable("target"))
            actual = self.versions(preconditions)
            if actual != preconditions:
                raise ports.GuardAcquisitionError(ports.VersionConflict(preconditions, actual))
            lease = FixtureLease(self, actual)
            self.active_lease = lease
            try:
                yield lease
            finally:
                lease.active = False
                self.active_lease = None
        finally:
            self._lock.release()

    async def read(
        self, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing | ports.ServiceUnavailable:
        if not self.available:
            return ports.ServiceUnavailable("target")
        return self._state.get(resource, ports.Missing())

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        if self.before_effect is not None:
            await self.before_effect.wait()
        if guard is not self.active_lease:
            return ports.GuardLost()
        current = await guard.assert_current()
        if not isinstance(current, ports.GuardCurrent):
            return current
        prior = self._state.get(resource)
        version = ExpectedVersion(resource, str(int(prior.version.version) + 1) if prior else "1")
        self._state[resource] = ports.ResourceSnapshot(version, change)
        self.effect_count += 1
        if self.after_effect is not None:
            await self.after_effect.wait()
        if self.interrupt_after_effect:
            self.interrupt_after_effect = False
            return ports.ResourceEffect(EffectDisposition.UNKNOWN, (version,), ())
        return ports.ResourceEffect(EffectDisposition.APPLIED, (version,), ())
