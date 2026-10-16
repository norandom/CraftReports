"""Application-owned command execution, independent of response waiters."""

import asyncio
from dataclasses import dataclass, field, replace
from uuid import uuid4

from craftreport.application import ports
from craftreport.application.admission import AdmittedCommand, CommandAdmission
from craftreport.application.dispatch import Inspection, QueryDispatcher
from craftreport.application.dispatch_ports import HandoffStore, RecordedHandoff
from craftreport.application.guards import rejection
from craftreport.application.outcomes import (
    OutcomeFacts,
    ResultValidation,
    outcome_update,
    validate_recorded_update,
)
from craftreport.application.registry import ObservedCommand
from craftreport.contracts import (
    Availability,
    Catalog,
    EffectDisposition,
    ExpectedVersion,
    InvocationEnvelope,
    InvocationResult,
    OperationKind,
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
    ResultReadback,
)


@dataclass(slots=True)
class Running:
    principal: Principal
    request: InvocationEnvelope
    reserved: bool = False
    receipt: Receipt | None = None
    handoff: str | None = None
    abandoned: bool = False


@dataclass
class Execution:
    admission: CommandAdmission
    queries: QueryDispatcher
    inspection: Inspection
    services: ports.CommandServices
    handoffs: HandoffStore
    installed_owners: frozenset[str] = frozenset()
    capacity: int = 16
    response_seconds: float = 5.0
    shutdown_seconds: float = 10.0
    _owner: str = field(default_factory=lambda: str(uuid4()), init=False)
    _tasks: dict[asyncio.Task[InvocationResult], Running] = field(
        default_factory=lambda: dict[asyncio.Task[InvocationResult], Running](), init=False
    )
    _closing: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if self.capacity < 1 or self.response_seconds <= 0 or self.shutdown_seconds <= 0:
            raise ValueError("Execution limits must be positive")

    async def catalog(self, principal: Principal) -> Catalog:
        return await self.inspection.catalog(principal)

    async def inspect(self, principal: Principal, operation_id: str) -> Receipt | Rejection:
        return await self.inspection.inspect(principal, operation_id)

    async def read_result(
        self, principal: Principal, operation_id: str
    ) -> ResultReadback | Rejection:
        return await self.inspection.read_result(principal, operation_id)

    async def invoke(self, principal: Principal, request: InvocationEnvelope) -> InvocationResult:
        bound = self.admission.guards.registry.resolve(
            request.operation.name, request.operation.contract_version
        )
        if bound is not None and bound.descriptor.kind is OperationKind.QUERY:
            return await self.queries.invoke(principal, request)
        state = Running(principal, request)
        task = asyncio.create_task(self._run(state))
        self._tasks[task] = state
        task.add_done_callback(self._finished)
        try:
            async with asyncio.timeout(self.response_seconds):
                return await asyncio.shield(task)
        except TimeoutError:
            if state.receipt is not None:
                return state.receipt
            state.abandoned = True
            task.cancel()
            return rejection(
                request.operation, request.correlation_id, "admission", "service_unavailable"
            )

    def _finished(self, task: asyncio.Task[InvocationResult]) -> None:
        self._tasks.pop(task, None)
        if not task.cancelled():
            task.exception()

    def _reserve(self, state: Running) -> bool:
        if self._closing or sum(item.reserved for item in self._tasks.values()) >= self.capacity:
            return False
        state.reserved = True
        return True

    async def _run(self, state: Running) -> InvocationResult:
        try:
            async with self.admission.open(
                state.principal, state.request, lambda: self._reserve(state)
            ) as admitted:
                if not isinstance(admitted, AdmittedCommand):
                    return (
                        await self.inspect(state.principal, admitted.operation_id)
                        if isinstance(admitted, Receipt)
                        else admitted
                    )
                state.receipt = admitted.receipt
                if state.abandoned:
                    return admitted.receipt
                pending = await self._pending(state, admitted)
                if isinstance(pending, Rejection):
                    return pending
                if state.abandoned:
                    return await self._interrupted(state)
                return await self._effect(state, admitted)
        except asyncio.CancelledError:
            return await self._interrupted(state)
        except Exception:
            return self._unavailable(state)
        finally:
            state.reserved = False

    def _unavailable(self, state: Running) -> Rejection:
        return rejection(
            state.request.operation,
            state.request.correlation_id,
            "execution",
            "service_unavailable",
        )

    async def _pending(self, state: Running, admitted: AdmittedCommand) -> InvocationResult:
        reference = str(uuid4())
        handoff = RecordedHandoff(
            state.principal,
            admitted.receipt.operation_id,
            reference,
            self._owner,
            admitted.guard.authoritative_versions,
        )
        await self.handoffs.record(handoff)
        if await self.handoffs.inspect(state.principal, handoff.operation_id, reference) != handoff:
            return self._unavailable(state)
        update = ports.ReceiptUpdate(ReceiptState.PENDING, handoff_ref=reference)
        result = await self._record(state, update)
        if isinstance(result, Receipt):
            state.handoff = reference
        return result

    async def _record(self, state: Running, update: ports.ReceiptUpdate) -> InvocationResult:
        current = state.receipt
        assert current is not None
        journal = self.admission.journal
        try:
            result = await journal.record(current.operation_id, current.revision, update)
        except Exception:
            result = None
        try:
            retained = await journal.read(current.operation_id)
            if not isinstance(retained, Receipt) or isinstance(result, ports.RevisionConflict):
                return self._unavailable(state)
            validate_recorded_update(current, retained, update)
            if isinstance(result, Receipt) and result != retained:
                return self._unavailable(state)
            state.receipt = retained
            return retained
        except Exception:
            return self._unavailable(state)

    async def _effect(self, state: Running, admitted: AdmittedCommand) -> InvocationResult:
        try:
            observed = await admitted.invoke(self.services)
            if not isinstance(observed, ObservedCommand):
                observed = ObservedCommand(EffectDisposition.NONE, (), (), (), None, lambda: None)
        except (Exception, asyncio.CancelledError):
            observed = ObservedCommand(EffectDisposition.UNKNOWN, (), (), (), None, lambda: None)
        assert state.receipt is not None
        descriptor = self.admission.guards.registry.resolve(
            state.request.operation.name, state.request.operation.contract_version
        )
        assert descriptor is not None
        facts = await self.queries.retain_result(
            state.principal,
            state.receipt.operation_id,
            observed.encode_result,
            descriptor.descriptor.limits,
        )
        facts = await self._observations(state, observed, facts)
        update = outcome_update(
            state.receipt,
            observed,
            facts,
            descriptor.descriptor.completion_evidence,
            descriptor.diagnostic_policy,
        )
        return await self._record(state, update)

    async def _observations(
        self, state: Running, observed: ObservedCommand, facts: OutcomeFacts
    ) -> OutcomeFacts:
        assert state.receipt is not None
        versions: list[ExpectedVersion] = []
        try:
            for resource in state.receipt.resources:
                value = await self.services.reads.resources.read(resource)
                if (
                    not isinstance(value, ports.ResourceSnapshot)
                    or value.version.resource != resource
                ):
                    raise ValueError("Resource readback unavailable")
                versions.append(value.version)
            refs = tuple(
                dict.fromkeys(
                    (
                        *observed.evidence,
                        *(ref for stage in observed.stages for ref in stage.evidence),
                    )
                )
            )
            evidence = await self.services.reads.evidence.inspect(refs)
            if tuple(item.reference for item in evidence) != refs:
                evidence = ()
            handoff = await self._handoff(state, observed.handoff_ref, tuple(versions))
            return replace(
                facts,
                completion_versions=tuple(versions),
                evidence=evidence,
                recorded_handoff=handoff,
                prior_handoff=state.handoff,
            )
        except Exception:
            return facts

    async def _handoff(
        self, state: Running, reference: str | None, versions: tuple[ExpectedVersion, ...]
    ) -> str | None:
        if reference is None or reference == state.handoff:
            return None
        assert state.receipt is not None
        found = await self.handoffs.inspect(state.principal, state.receipt.operation_id, reference)
        if (
            isinstance(found, RecordedHandoff)
            and found.owner in self.installed_owners
            and found
            == RecordedHandoff(
                state.principal, state.receipt.operation_id, reference, found.owner, versions
            )
        ):
            return reference
        return None

    async def _interrupted(self, state: Running) -> InvocationResult:
        if state.receipt is None:
            return self._unavailable(state)
        current = state.receipt
        if current.state not in (ReceiptState.ACCEPTED, ReceiptState.PENDING):
            return current
        observed = ObservedCommand(EffectDisposition.UNKNOWN, (), (), (), None, lambda: None)
        facts = OutcomeFacts(ResultValidation.MISSING, None, Availability.MISSING, ())
        bound = self.admission.guards.registry.resolve(
            current.operation.name, current.operation.contract_version
        )
        assert bound is not None
        return await self._record(
            state, outcome_update(current, observed, facts, bound.descriptor.completion_evidence)
        )

    async def shutdown(self) -> bool:
        self._closing = True
        tasks = set(self._tasks)
        if not tasks:
            return True
        _, pending = await asyncio.wait(tasks, timeout=self.shutdown_seconds / 3)
        for task in pending:
            state = self._tasks.get(task)
            if state is not None:
                state.abandoned = True
            task.cancel()
        if pending:
            _, pending = await asyncio.wait(pending, timeout=self.shutdown_seconds / 3)
        repairs: set[asyncio.Task[InvocationResult]] = set()
        for task in pending:
            state = self._tasks.get(task)
            if state is not None:
                repair = asyncio.create_task(self._interrupted(state))
                self._tasks[repair] = state
                repair.add_done_callback(self._finished)
                repairs.add(repair)
        if pending:
            _, pending = await asyncio.wait(pending | repairs, timeout=self.shutdown_seconds / 3)
        return not pending
