"""Composed app resources, outer sorted guards, and evidence routing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from craftreport_gridcraft.facts import AppFacts
from craftreport_gridcraft.providers import (
    AppEvidenceReader,
    AppExecutionGuard,
    AppGuardLease,
    AppProviders,
    AppResourceEffects,
    AppResourceReader,
    compose_app_providers,
)
from craftreport_gridcraft.values import (
    AppObservationFact,
    BrowserTarget,
    CurrentObservationPointer,
)

from craftreport.application.ports import (
    GuardAcquisitionError,
    GuardLease,
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
from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import (
    Availability,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    StageState,
)
from craftreport.contracts.values import JsonObject
from craftreport.runtime.values import RunPins


class DummyUpstreamResources:
    def __init__(
        self,
        data: dict[ResourceRef, ResourceSnapshot | Missing | ServiceUnavailable],
    ) -> None:
        self.data = data
        self.reads: list[ResourceRef] = []

    async def read(self, resource: ResourceRef) -> ResourceSnapshot | Missing | ServiceUnavailable:
        self.reads.append(resource)
        return self.data.get(resource, Missing())


class DummyUpstreamLease:
    def __init__(self, versions: tuple[ExpectedVersion, ...]) -> None:
        self.authoritative_versions = versions
        self.current = True

    async def assert_current(self) -> GuardCurrent | GuardLost:
        return GuardCurrent() if self.current else GuardLost()


class DummyUpstreamGuard:
    def __init__(self) -> None:
        self.acquired_pins: list[tuple[ExpectedVersion, ...]] = []
        self.fail_conflict = False

    @asynccontextmanager
    async def acquire(
        self, preconditions: tuple[ExpectedVersion, ...]
    ) -> AsyncGenerator[GuardLease]:
        if self.fail_conflict:
            raise GuardAcquisitionError(VersionConflict(preconditions, ()))
        self.acquired_pins.append(preconditions)
        yield DummyUpstreamLease(preconditions)


class DummyUpstreamEvidence:
    def __init__(self) -> None:
        self.inspected: list[tuple[EvidenceRef, ...]] = []

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        self.inspected.append(refs)
        return tuple(EvidenceStatus(ref, Availability.AVAILABLE, StageState.PASSED) for ref in refs)


class DummyUpstreamEffects:
    def __init__(self) -> None:
        self.applied: list[tuple[ResourceRef, JsonObject]] = []

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: GuardLease
    ) -> ResourceEffect | GuardLost:
        self.applied.append((resource, change))
        return ResourceEffect(
            EffectDisposition.APPLIED,
            guard.authoritative_versions,
            (),
        )


@pytest.fixture
def facts(tmp_path: Path) -> AppFacts:
    return AppFacts(tmp_path / "app_root")


@pytest.fixture
def evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        identity="ev-1",
        scope="browser_observation",
        operation_id="op-prov-1",
        operation=OperationKey("gridcraft.apply", "1"),
        resource_versions=(),
        content_digest="e" * 64,
    )


@pytest.fixture
def recorded_document(
    facts: AppFacts,
    browser_target: BrowserTarget,
    run: RunPins,
    evidence_ref: EvidenceRef,
) -> tuple[str, AppObservationFact, CurrentObservationPointer]:
    doc_id = browser_target.identity.document_id
    obs = AppObservationFact(
        operation_id="op-prov-1",
        subject="operator-1",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        observation=None,
        candidate=None,
        evidence=(evidence_ref,),
        reason_code=None,
        created_at="2026-10-17T12:00:00Z",
    )
    pointer = CurrentObservationPointer(
        document_id=doc_id,
        operation_id="op-prov-1",
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        fact_digest=obs.content_digest,
        updated_at="2026-10-17T12:00:01Z",
    )
    facts.record_observation(obs)
    facts.update_current_index(pointer)
    return doc_id, obs, pointer


@pytest.mark.anyio
async def test_resource_reader_routes_app_documents_and_delegates(
    facts: AppFacts,
    recorded_document: tuple[str, AppObservationFact, CurrentObservationPointer],
) -> None:
    doc_id, _obs, _pointer = recorded_document
    upstream_res = ResourceRef("feed", "portfolio:one")
    upstream_snap = ResourceSnapshot(ExpectedVersion(upstream_res, "5"), {"value": 42})
    upstream_reader = DummyUpstreamResources({upstream_res: upstream_snap})

    reader = AppResourceReader(upstream_reader, facts)

    # 1. Read existing app document -> ResourceSnapshot with revision
    app_res = ResourceRef("gridcraft_document", doc_id)
    snapshot = await reader.read(app_res)
    assert isinstance(snapshot, ResourceSnapshot)
    assert snapshot.version == ExpectedVersion(app_res, "1")
    assert snapshot.content["operation_id"] == "op-prov-1"
    assert snapshot.content["outcome"] == "complete"

    # 2. Read missing app document -> Missing
    missing_res = ResourceRef("gridcraft_document", "doc-absent")
    missing_snap = await reader.read(missing_res)
    assert isinstance(missing_snap, Missing)

    # 3. Read missing app artifact -> Missing
    artifact_res = ResourceRef("gridcraft_artifact", "art-unknown")
    art_snap = await reader.read(artifact_res)
    assert isinstance(art_snap, Missing)

    # 4. Read upstream resource -> delegates to upstream
    up_read = await reader.read(upstream_res)
    assert up_read == upstream_snap
    assert upstream_res in upstream_reader.reads

    # 5. Corrupt index file returns ServiceUnavailable
    index_file = facts.indexes_dir / f"{doc_id}.json"
    index_file.write_text("{corrupt json", encoding="utf-8")
    corrupt_snap = await reader.read(app_res)
    assert isinstance(corrupt_snap, ServiceUnavailable)


@pytest.mark.anyio
async def test_execution_guard_outer_sorted_locking(
    facts: AppFacts,
) -> None:
    upstream_res = ResourceRef("feed", "portfolio:one")
    upstream_guard = DummyUpstreamGuard()
    upstream_reader = DummyUpstreamResources(
        {upstream_res: ResourceSnapshot(ExpectedVersion(upstream_res, "1"), {})}
    )
    resources = AppResourceReader(upstream_reader, facts)
    guard = AppExecutionGuard(upstream_guard, resources)

    # Reverse order concurrent acquisitions must not deadlock due to canonical sorting
    doc1 = ExpectedVersion(ResourceRef("gridcraft_document", "doc-1"), "absent")
    doc2 = ExpectedVersion(ResourceRef("gridcraft_document", "doc-2"), "absent")

    log: list[str] = []

    async def acquire_order(name: str, pins: tuple[ExpectedVersion, ...]) -> None:
        async with guard.acquire(pins) as lease:
            assert isinstance(lease, AppGuardLease)
            log.append(f"{name}_in")
            await asyncio.sleep(0.01)
            log.append(f"{name}_out")

    await asyncio.gather(
        acquire_order("A", (doc1, doc2)),
        acquire_order("B", (doc2, doc1)),
    )

    assert "A_in" in log and "A_out" in log
    assert "B_in" in log and "B_out" in log


@pytest.mark.anyio
async def test_execution_guard_acquire_and_assert_current(
    facts: AppFacts,
    recorded_document: tuple[str, AppObservationFact, CurrentObservationPointer],
) -> None:
    doc_id, _, pointer = recorded_document
    upstream_res = ResourceRef("feed", "portfolio:one")
    upstream_guard = DummyUpstreamGuard()
    upstream_reader = DummyUpstreamResources(
        {upstream_res: ResourceSnapshot(ExpectedVersion(upstream_res, "1"), {})}
    )
    resources = AppResourceReader(upstream_reader, facts)
    guard = AppExecutionGuard(upstream_guard, resources)

    app_pin = ExpectedVersion(ResourceRef("gridcraft_document", doc_id), "1")
    up_pin = ExpectedVersion(upstream_res, "1")

    # 1. Matching versions successfully acquire and assert_current
    async with guard.acquire((up_pin, app_pin)) as lease:
        assert isinstance(lease, AppGuardLease)
        check = await lease.assert_current()
        assert isinstance(check, GuardCurrent)
        assert app_pin in lease.authoritative_versions
        assert up_pin in lease.authoritative_versions

    # 2. Conflicting app version raises GuardAcquisitionError
    stale_app_pin = ExpectedVersion(ResourceRef("gridcraft_document", doc_id), "99")
    with pytest.raises(GuardAcquisitionError) as exc_info:
        async with guard.acquire((stale_app_pin, up_pin)):
            pass
    assert isinstance(exc_info.value.reason, VersionConflict)

    # 3. If version becomes stale during lease, assert_current reports VersionConflict
    async with guard.acquire((app_pin, up_pin)) as lease:
        # Simulate index advance
        new_pointer = replace(pointer, revision=2, fact_digest="f" * 64)
        facts.update_current_index(new_pointer)
        check2 = await lease.assert_current()
        assert isinstance(check2, VersionConflict)


@pytest.mark.anyio
async def test_evidence_reader_routing_and_order_preservation(
    facts: AppFacts,
    recorded_document: tuple[str, AppObservationFact, CurrentObservationPointer],
) -> None:
    doc_id, obs, _ = recorded_document
    upstream_evidence = DummyUpstreamEvidence()
    upstream_reader = DummyUpstreamResources({})
    resources = AppResourceReader(upstream_reader, facts)
    reader = AppEvidenceReader(upstream_evidence, facts, resources)

    app_ref_valid = EvidenceRef(
        identity="ev-valid",
        scope="gridcraft",
        operation_id=obs.operation_id,
        operation=OperationKey("gridcraft.apply", "1"),
        resource_versions=(ExpectedVersion(ResourceRef("gridcraft_document", doc_id), "1"),),
        content_digest=obs.content_digest,
    )
    app_ref_mismatch_digest = EvidenceRef(
        identity="ev-bad-digest",
        scope="gridcraft",
        operation_id=obs.operation_id,
        operation=OperationKey("gridcraft.apply", "1"),
        resource_versions=(),
        content_digest="0" * 64,
    )
    app_ref_missing = EvidenceRef(
        identity="ev-missing",
        scope="gridcraft",
        operation_id="op-missing",
        operation=OperationKey("gridcraft.apply", "1"),
        resource_versions=(),
        content_digest="a" * 64,
    )
    up_ref = EvidenceRef(
        identity="up-1",
        scope="synthetic",
        operation_id="op-up",
        operation=OperationKey("feed.publish", "1"),
        resource_versions=(),
        content_digest="b" * 64,
    )

    # Inspect interleaved refs
    refs = (app_ref_valid, up_ref, app_ref_mismatch_digest, app_ref_missing)
    statuses = await reader.inspect(refs)

    assert len(statuses) == 4
    # Exact order preserved:
    assert statuses[0].reference == app_ref_valid
    assert statuses[0].availability is Availability.AVAILABLE
    assert statuses[0].verification is StageState.PASSED

    assert statuses[1].reference == up_ref
    assert statuses[1].availability is Availability.AVAILABLE
    assert statuses[1].verification is StageState.PASSED

    assert statuses[2].reference == app_ref_mismatch_digest
    assert statuses[2].availability is Availability.AVAILABLE
    assert statuses[2].verification is StageState.FAILED

    assert statuses[3].reference == app_ref_missing
    assert statuses[3].availability is Availability.MISSING
    assert statuses[3].verification is StageState.PENDING


@pytest.mark.anyio
async def test_resource_effects_fails_closed_on_generic_app_changes(
    facts: AppFacts,
    recorded_document: tuple[str, AppObservationFact, CurrentObservationPointer],
) -> None:
    doc_id, _, _ = recorded_document
    upstream_effects = DummyUpstreamEffects()
    effects = AppResourceEffects(upstream_effects)

    app_res = ResourceRef("gridcraft_document", doc_id)
    up_res = ResourceRef("feed", "portfolio:one")

    lease = DummyUpstreamLease(())

    # 1. Generic app changes fail closed
    res = await effects.apply(app_res, {"key": "val"}, lease)
    assert isinstance(res, GuardLost)
    assert len(upstream_effects.applied) == 0

    # 2. Upstream resources delegate
    res2 = await effects.apply(up_res, {"value": 99}, lease)
    assert isinstance(res2, ResourceEffect)
    assert len(upstream_effects.applied) == 1


def test_compose_app_providers(
    facts: AppFacts,
) -> None:
    up_reader = DummyUpstreamResources({})
    up_guard = DummyUpstreamGuard()
    up_evidence = DummyUpstreamEvidence()
    up_effects = DummyUpstreamEffects()

    providers = compose_app_providers(
        upstream_resources=up_reader,
        upstream_guard=up_guard,
        upstream_evidence=up_evidence,
        upstream_effects=up_effects,
        facts=facts,
    )

    assert isinstance(providers, AppProviders)
    assert isinstance(providers.resources, AppResourceReader)
    assert isinstance(providers.guard, AppExecutionGuard)
    assert isinstance(providers.evidence, AppEvidenceReader)
    assert isinstance(providers.effects, AppResourceEffects)
