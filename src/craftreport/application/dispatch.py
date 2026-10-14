"""Guarded inspection and query execution, composed with command dispatch later."""

from dataclasses import dataclass, replace
from uuid import uuid4

from craftreport.application import ports
from craftreport.application.dispatch_ports import ResultStore
from craftreport.application.guards import GuardedCall, InvocationGuards, authorize, rejection
from craftreport.application.outcomes import OutcomeFacts, ResultValidation, outcome_update
from craftreport.application.registry import ObservedCommand, PreparedQuery
from craftreport.contracts import (
    Availability,
    CapabilityView,
    Catalog,
    EffectDisposition,
    EvidenceRef,
    InvocationEnvelope,
    InvocationResult,
    OperationDescriptor,
    OperationKey,
    OperationLimits,
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
)


@dataclass(frozen=True, slots=True)
class Inspection:
    snapshot: Catalog
    access: ports.AccessPolicy
    journal: ports.OperationJournal
    results: ResultStore
    evidence: ports.EvidenceReader

    async def catalog(self, principal: Principal) -> Catalog:
        key, correlation = OperationKey("kernel.catalog", "1"), str(uuid4())
        try:
            denied = await authorize(
                self.access, principal, ports.CatalogAccess(), key, correlation
            )
            if denied is not None:
                raise ports.CatalogRejected(denied)
            visible: list[OperationDescriptor] = []
            for descriptor in self.snapshot.operations:
                decision = await self.access.authorize(
                    principal, ports.OperationAccess(descriptor.key)
                )
                if isinstance(decision, ports.ServiceUnavailable):
                    raise ports.ServiceUnavailableError(decision)
                if isinstance(decision, ports.AccessAllowed):
                    visible.append(descriptor)
            keys = {descriptor.key for descriptor in visible}
            views: list[CapabilityView] = []
            for view in self.snapshot.capabilities:
                filtered = await self._capability(principal, view, keys)
                if filtered is not None:
                    views.append(filtered)
            return replace(self.snapshot, operations=tuple(visible), capabilities=tuple(views))
        except ports.CatalogRejected:
            raise
        except Exception:
            raise ports.CatalogRejected(
                rejection(key, correlation, "catalog", "service_unavailable")
            ) from None

    async def _capability(
        self, principal: Principal, view: CapabilityView, keys: set[OperationKey]
    ) -> CapabilityView | None:
        operations = tuple(item for item in view.manifest.operations if item.key in keys)
        if not operations:
            return None
        manifest = replace(view.manifest, operations=operations, settings_schema={})
        record = view.record
        if record is not None:
            evidence: list[EvidenceRef] = []
            for ref in record.evidence:
                decision = await self.access.authorize(
                    principal, ports.ReceiptAccess(ref.operation_id)
                )
                if isinstance(decision, ports.ServiceUnavailable):
                    raise ports.ServiceUnavailableError(decision)
                if ref.operation in keys and isinstance(decision, ports.AccessAllowed):
                    evidence.append(ref)
            record = replace(record, evidence=tuple(evidence))
        return replace(view, manifest=manifest, record=record)

    async def inspect(self, principal: Principal, operation_id: str) -> Receipt | Rejection:
        key, correlation = OperationKey("kernel.inspect", "1"), str(uuid4())
        try:
            denied = await authorize(
                self.access, principal, ports.ReceiptAccess(operation_id), key, correlation
            )
            if denied is not None:
                return denied
            receipt = await self.journal.read(operation_id)
            if isinstance(receipt, ports.Missing):
                return rejection(key, correlation, "inspect", "receipt_missing")
            unavailable = await self._retained_content(principal, receipt)
            if unavailable is not None:
                return rejection(key, correlation, "inspect", unavailable)
            return receipt
        except Exception:
            return rejection(key, correlation, "inspect", "service_unavailable")

    async def _retained_content(self, principal: Principal, receipt: Receipt) -> str | None:
        if receipt.result_ref is not None:
            result = await self.results.read(principal, receipt.operation_id, receipt.result_ref)
            if result.reference != receipt.result_ref:
                return "result_unavailable"
            if result.availability is not Availability.AVAILABLE:
                return f"result_{result.availability.value}"
        refs = tuple(
            dict.fromkeys(
                (*receipt.evidence, *(ref for stage in receipt.stages for ref in stage.evidence))
            )
        )
        statuses = await self.evidence.inspect(refs) if refs else ()
        if tuple(status.reference for status in statuses) != refs:
            return "evidence_unavailable"
        for status in statuses:
            if status.availability is not Availability.AVAILABLE:
                return f"evidence_{status.availability.value}"
        return None


@dataclass(frozen=True, slots=True)
class QueryDispatcher:
    """Real query path; the final Facade adds command admission/execution separately."""

    guards: InvocationGuards
    journal: ports.OperationJournal
    reads: ports.ReadServices
    results: ResultStore
    snapshot: Catalog

    async def invoke(self, principal: Principal, request: InvocationEnvelope) -> InvocationResult:
        guarded = await self.guards.prepare(principal, request)
        if isinstance(guarded, Rejection):
            return guarded
        if not isinstance(guarded.prepared, PreparedQuery):
            return rejection(request.operation, request.correlation_id, "resolve", "query_required")
        return await self.execute(principal, request, guarded, guarded.prepared)

    async def execute(
        self,
        principal: Principal,
        request: InvocationEnvelope,
        guarded: GuardedCall,
        prepared: PreparedQuery,
    ) -> InvocationResult:
        operation_id = str(uuid4())
        current = Receipt(
            operation_id,
            request.operation,
            request.correlation_id,
            1,
            ReceiptState.ACCEPTED,
            guarded.capability_versions,
            prepared.resources,
            request.expected_versions,
            None,
            None,
            (),
            (),
            (),
            self.snapshot.deployment_epoch,
            self.snapshot.retention_profile,
        )
        facts = await self._query_result(
            principal, operation_id, prepared, guarded.descriptor.limits
        )
        observation = ObservedCommand(EffectDisposition.NONE, (), (), (), None, lambda: None)
        update = outcome_update(current, observation, facts, guarded.descriptor.completion_evidence)
        try:
            recorded = await self.journal.record_query(
                ports.QueryObservation(
                    operation_id,
                    principal,
                    request.operation,
                    request.correlation_id,
                    guarded.capability_versions,
                    prepared.resources,
                    request.expected_versions,
                    update,
                )
            )
            expected = replace(
                current,
                state=update.state,
                stages=update.stages,
                diagnostics=update.diagnostics,
                evidence=update.evidence,
                result_ref=update.result_ref,
                result_availability=update.result_availability,
            )
            if recorded != expected:
                raise ValueError("Query observation readback mismatch")
            return recorded
        except Exception:
            return rejection(
                request.operation, request.correlation_id, "journal", "service_unavailable"
            )

    async def _query_result(
        self,
        principal: Principal,
        operation_id: str,
        prepared: PreparedQuery,
        limits: OperationLimits,
    ) -> OutcomeFacts:
        try:
            observed = await prepared.invoke(ports.ReadContext(operation_id, principal, self.reads))
        except Exception:
            return OutcomeFacts(ResultValidation.MISSING, None, Availability.MISSING, ())
        try:
            value = observed.encode_result()
            self.guards.limits.check_result(value, limits)
        except Exception:
            return OutcomeFacts(ResultValidation.INVALID, None, Availability.MISSING, ())
        reference = None
        try:
            reference = await self.results.write(principal, operation_id, value)
            retained = await self.results.read(principal, operation_id, reference)
            availability = retained.availability
            if retained.reference != reference or (
                availability is Availability.AVAILABLE and retained.value != value
            ):
                availability = Availability.UNAVAILABLE
            return OutcomeFacts(ResultValidation.VALID, reference, availability, ())
        except Exception:
            return OutcomeFacts(ResultValidation.VALID, reference, Availability.UNAVAILABLE, ())
