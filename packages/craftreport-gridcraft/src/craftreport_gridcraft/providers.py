"""Composed app resources, execution guard with outer sorted locks, and evidence routing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import cast

from craftreport.application.ports import (
    EvidenceReader,
    ExecutionGuard,
    GuardAcquisitionError,
    GuardLease,
    ResourceEffects,
    ResourceReader,
)
from craftreport.application.service_values import (
    GuardCurrent,
    GuardLost,
    Missing,
    ResourceEffect,
    ResourceSnapshot,
    ServiceUnavailable,
    VersionConflict,
)
from craftreport.contracts.identity import ExpectedVersion, ResourceRef
from craftreport.contracts.outcomes import (
    Availability,
    EvidenceRef,
    EvidenceStatus,
    StageState,
)
from craftreport.contracts.values import JsonObject, freeze_object
from craftreport_gridcraft.facts import AppFacts, FactUnavailable
from craftreport_gridcraft.values import (
    AppIntentFact,
    AppObservationFact,
)

APP_RESOURCE_KINDS = frozenset({"gridcraft_document", "gridcraft_artifact"})
APP_EVIDENCE_SCOPES = frozenset(
    {"gridcraft", "browser_observation", "gridcraft_fact", "app_observation", "app_intent"}
)


class AppResourceReader(ResourceReader):
    """Route gridcraft_document and gridcraft_artifact to local durable facts; delegate others."""

    def __init__(self, upstream: ResourceReader, facts: AppFacts) -> None:
        self._upstream = upstream
        self._facts = facts

    async def read(self, resource: ResourceRef) -> ResourceSnapshot | Missing | ServiceUnavailable:
        if resource.kind not in APP_RESOURCE_KINDS:
            return await self._upstream.read(resource)
        if resource.kind == "gridcraft_document":
            return self._read_document(resource)
        return Missing()

    def _read_document(
        self, resource: ResourceRef
    ) -> ResourceSnapshot | Missing | ServiceUnavailable:
        try:
            pointer = self._facts.read_current_index(resource.identity)
        except FactUnavailable:
            return ServiceUnavailable("gridcraft_facts")
        if pointer is None:
            return Missing()
        try:
            obs = self._facts.read_observation(pointer.operation_id)
        except FactUnavailable:
            return ServiceUnavailable("gridcraft_facts")
        if obs is None:
            return Missing()
        content = {
            "document_id": pointer.document_id,
            "operation_id": pointer.operation_id,
            "revision": pointer.revision,
            "outcome": pointer.outcome,
            "fact_digest": pointer.fact_digest,
            "content_digest": pointer.content_digest,
        }
        return ResourceSnapshot(
            ExpectedVersion(resource, str(pointer.revision)),
            freeze_object(content),
        )


async def _check_pins(
    resources: ResourceReader,
    all_pins: tuple[ExpectedVersion, ...],
    app_pins: tuple[ExpectedVersion, ...],
) -> GuardCurrent | VersionConflict | ServiceUnavailable:
    for pin in app_pins:
        current = await resources.read(pin.resource)
        if isinstance(current, ServiceUnavailable):
            return current
        if isinstance(current, Missing):
            if pin.version != "absent":
                return VersionConflict(all_pins, (ExpectedVersion(pin.resource, "missing"),))
        elif pin.version != current.version.version:
            return VersionConflict(all_pins, (current.version,))
    return GuardCurrent()


class AppGuardLease(GuardLease):
    """Outer app version lease wrapping delegated upstream lease."""

    def __init__(
        self,
        app_pins: tuple[ExpectedVersion, ...],
        upstream_lease: GuardLease,
        resources: ResourceReader,
    ) -> None:
        self._app_pins = app_pins
        self._upstream_lease = upstream_lease
        self._resources = resources

    @property
    def authoritative_versions(self) -> tuple[ExpectedVersion, ...]:
        return self._app_pins + self._upstream_lease.authoritative_versions

    async def assert_current(
        self,
    ) -> GuardCurrent | GuardLost | VersionConflict | ServiceUnavailable:
        check = await self._upstream_lease.assert_current()
        if not isinstance(check, GuardCurrent):
            return check
        return await _check_pins(self._resources, self.authoritative_versions, self._app_pins)


class AppExecutionGuard(ExecutionGuard):
    """Complete-set outer sorted locking with reverse release and upstream delegation."""

    def __init__(
        self,
        upstream: ExecutionGuard,
        resources: ResourceReader,
        timeout_seconds: float = 2.0,
    ) -> None:
        self._upstream = upstream
        self._resources = resources
        self._timeout = timeout_seconds
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}

    def _get_lock(self, resource: ResourceRef) -> asyncio.Lock:
        return self._locks.setdefault((resource.kind, resource.identity), asyncio.Lock())

    async def _acquire_app_locks(self, app_pins: tuple[ExpectedVersion, ...]) -> list[asyncio.Lock]:
        acquired: list[asyncio.Lock] = []
        try:
            async with asyncio.timeout(self._timeout):
                for pin in app_pins:
                    lock = self._get_lock(pin.resource)
                    await lock.acquire()
                    acquired.append(lock)
        except TimeoutError as err:
            for lock in reversed(acquired):
                lock.release()
            raise GuardAcquisitionError(ServiceUnavailable("guard_timeout")) from err
        return acquired

    @asynccontextmanager
    async def acquire(
        self, preconditions: tuple[ExpectedVersion, ...]
    ) -> AsyncGenerator[GuardLease]:
        sorted_pins = tuple(
            sorted(preconditions, key=lambda p: (p.resource.kind, p.resource.identity))
        )
        app_pins = tuple(p for p in sorted_pins if p.resource.kind in APP_RESOURCE_KINDS)
        upstream_pins = tuple(p for p in preconditions if p.resource.kind not in APP_RESOURCE_KINDS)

        acquired = await self._acquire_app_locks(app_pins)
        try:
            check = await _check_pins(self._resources, preconditions, app_pins)
            if not isinstance(check, GuardCurrent):
                raise GuardAcquisitionError(check)
            async with self._upstream.acquire(upstream_pins) as upstream_lease:
                yield AppGuardLease(app_pins, upstream_lease, self._resources)
        finally:
            for lock in reversed(acquired):
                lock.release()


class AppEvidenceReader(EvidenceReader):
    """Route app evidence namespace to verified local facts; delegate upstream."""

    def __init__(
        self,
        upstream: EvidenceReader,
        facts: AppFacts,
        resources: ResourceReader,
    ) -> None:
        self._upstream = upstream
        self._facts = facts
        self._resources = resources

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        results: list[EvidenceStatus] = []
        for ref in refs:
            if ref.scope in APP_EVIDENCE_SCOPES or ref.identity.startswith("gridcraft:"):
                results.append(self._inspect_app_ref(ref))
            else:
                up_statuses = await self._upstream.inspect((ref,))
                results.append(up_statuses[0])
        return tuple(results)

    def _inspect_app_ref(self, ref: EvidenceRef) -> EvidenceStatus:
        try:
            obs = self._facts.read_observation(ref.operation_id)
            fact: AppObservationFact | AppIntentFact | None = obs
            if fact is None:
                fact = self._facts.read_intent(ref.operation_id)
        except FactUnavailable:
            return EvidenceStatus(ref, Availability.UNAVAILABLE, StageState.PENDING)
        if fact is None:
            return EvidenceStatus(ref, Availability.MISSING, StageState.PENDING)
        if fact.content_digest != ref.content_digest:
            return EvidenceStatus(ref, Availability.AVAILABLE, StageState.FAILED)
        return EvidenceStatus(ref, Availability.AVAILABLE, StageState.PASSED)


class AppResourceEffects(ResourceEffects):
    """Fail closed on generic app modifications; delegate upstream."""

    def __init__(self, upstream: ResourceEffects) -> None:
        self._upstream = upstream

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: GuardLease
    ) -> ResourceEffect | GuardLost | VersionConflict | ServiceUnavailable:
        if resource.kind in APP_RESOURCE_KINDS:
            return GuardLost()
        upstream_lease = getattr(guard, "_upstream_lease", guard)
        return await self._upstream.apply(resource, change, cast(GuardLease, upstream_lease))


@dataclass(frozen=True, slots=True)
class AppProviders:
    resources: AppResourceReader
    guard: AppExecutionGuard
    evidence: AppEvidenceReader
    effects: AppResourceEffects


def compose_app_providers(
    *,
    upstream_resources: ResourceReader,
    upstream_guard: ExecutionGuard,
    upstream_evidence: EvidenceReader,
    upstream_effects: ResourceEffects,
    facts: AppFacts,
) -> AppProviders:
    resources = AppResourceReader(upstream_resources, facts)
    guard = AppExecutionGuard(upstream_guard, resources)
    evidence = AppEvidenceReader(upstream_evidence, facts, resources)
    effects = AppResourceEffects(upstream_effects)
    return AppProviders(
        resources=resources,
        guard=guard,
        evidence=evidence,
        effects=effects,
    )
