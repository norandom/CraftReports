"""Temporary recorded execution owners, never a durable scheduler."""

import asyncio
from dataclasses import replace

from fixture_admission import KEY, AdmissionFixture
from fixture_dispatch import RESOURCE

from craftreport.application import ports
from craftreport.application.dispatch import Inspection, QueryDispatcher
from craftreport.application.dispatch_ports import RecordedHandoff
from craftreport.application.execution import Execution
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.contracts import (
    Availability,
    EvidencePolicy,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    OutcomeProposal,
    Principal,
    StageResult,
    StageState,
)


class FixtureHandoffs:
    def __init__(self) -> None:
        self.records: dict[str, RecordedHandoff] = {}
        self.available = True

    async def record(self, handoff: RecordedHandoff) -> None:
        if not self.available:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("handoff"))
        self.records[handoff.reference] = handoff

    async def inspect(
        self, principal: Principal, operation_id: str, reference: str
    ) -> RecordedHandoff | ports.Missing | ports.ServiceUnavailable:
        if not self.available:
            return ports.ServiceUnavailable("handoff")
        result = self.records.get(reference)
        if result is None or result.principal != principal or result.operation_id != operation_id:
            return ports.Missing()
        return result


def executor(fixture: AdmissionFixture) -> Execution:
    return Execution(
        fixture.admission,
        QueryDispatcher(
            fixture.guards, fixture.journal, fixture.reads, fixture.results, fixture.catalog
        ),
        Inspection(
            fixture.catalog, fixture.access, fixture.journal, fixture.results, fixture.evidence
        ),
        fixture.services,
        FixtureHandoffs(),
    )


class ExecutionFixture(AdmissionFixture):
    calls: int

    def __init__(self, mode: str = "normal") -> None:
        super().__init__()
        self.mode = mode
        self.handoffs = FixtureHandoffs()
        self.finish = asyncio.Event()
        bound = self.registry.resolve(KEY.name, KEY.contract_version)
        assert bound is not None
        descriptor = replace(bound.descriptor, completion_evidence=EvidencePolicy(("effect",)))
        self.registry = ImmutableOperationRegistry((replace(bound, descriptor=descriptor),))
        self.guards = replace(self.guards, registry=self.registry)
        self.admission = replace(self.admission, guards=self.guards)
        self.catalog = replace(self.catalog, operations=self.registry.describe())

    async def write(self, request: str, context: ports.CommandContext) -> OutcomeProposal[str]:
        result = await super().write(request, context)
        if self.mode == "exception":
            raise RuntimeError("credential-private")
        if self.mode == "resist":
            try:
                await self.finish.wait()
            except asyncio.CancelledError:
                await self.finish.wait()
        snapshot = await self.target.read(RESOURCE)
        assert isinstance(snapshot, ports.ResourceSnapshot)
        versions = (snapshot.version,)
        if self.mode == "stale":
            versions = (ExpectedVersion(RESOURCE, "1"),)
        ref = EvidenceRef("observed-effect", "synthetic", context.operation_id, KEY, versions)
        if self.mode != "missing":
            self.evidence.retain(EvidenceStatus(ref, Availability.AVAILABLE, StageState.PASSED))
        if self.mode == "unavailable":
            self.evidence.available = False
        self._provider_failure()
        if self.mode.startswith("handoff"):
            await self._transfer(context, versions)
            return replace(result, handoff_ref="transfer")
        return replace(
            result,
            stages=(StageResult("effect", StageState.PASSED, "observed", (ref,)),),
            evidence=(ref,),
        )

    async def _transfer(
        self, context: ports.CommandContext, versions: tuple[ExpectedVersion, ...]
    ) -> None:
        await self.handoffs.record(
            RecordedHandoff(
                context.principal, context.operation_id, "transfer", "external", versions
            )
        )
        if self.mode == "handoff_foreign":
            self.handoffs.records["transfer"] = replace(
                self.handoffs.records["transfer"], operation_id="foreign"
            )
        if self.mode == "handoff_stale":
            self.handoffs.records["transfer"] = replace(
                self.handoffs.records["transfer"], versions=(ExpectedVersion(RESOURCE, "1"),)
            )
        if self.mode == "handoff_unavailable":
            self.handoffs.available = False

    def _provider_failure(self) -> None:
        if self.mode == "journal":
            self.journal.available = False
        if self.mode == "lost_ack":
            self.journal.lose_record_ack = True
        if self.mode == "result":
            self.results.read_availability = Availability.MISSING
