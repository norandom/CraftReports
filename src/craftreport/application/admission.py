"""Scoped retry admission; execution lifetime belongs to the caller of open()."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field, replace
from typing import Protocol

from craftreport.application import ports
from craftreport.application.guards import GuardedCall, InvocationGuards, authorize, rejection
from craftreport.application.registry import ObservedCommand, PreparedCommand
from craftreport.contracts import (
    CommandIntent,
    ExpectedVersion,
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    Principal,
    Receipt,
    Rejection,
    ResourceRef,
    RetryKey,
)


class RequestFingerprint(Protocol):
    @property
    def policy(self) -> str: ...
    def __call__(
        self,
        operation: OperationKey,
        content: JsonObject,
        resources: tuple[ResourceRef, ...],
        versions: tuple[ExpectedVersion, ...],
    ) -> str: ...


@dataclass(slots=True)
class AdmittedCommand:
    """One-shot authority valid only while the admission context remains open.

    An execution owner can enter open() in its own retained task, keeping the
    lease through handler completion. Returning a receipt transfers no authority.
    """

    receipt: Receipt
    principal: Principal
    prepared: PreparedCommand
    guard: ports.GuardLease
    _active: bool = field(default=True, init=False)
    _invoked: bool = field(default=False, init=False)

    def close(self) -> None:
        self._active = False

    async def invoke(
        self, services: ports.CommandServices
    ) -> ObservedCommand | ports.GuardLost | ports.VersionConflict | ports.ServiceUnavailable:
        if not self._active or self._invoked:
            raise RuntimeError("Admission authority is closed or already consumed")
        self._invoked = True
        current = await self.guard.assert_current()
        if not isinstance(current, ports.GuardCurrent):
            return current
        return await self.prepared.invoke(
            ports.CommandContext(self.receipt.operation_id, self.principal, self.guard, services)
        )


@dataclass(frozen=True, slots=True)
class CommandAdmission:
    guards: InvocationGuards
    journal: ports.OperationJournal
    execution_guard: ports.ExecutionGuard
    fingerprint: RequestFingerprint

    @asynccontextmanager
    async def open(
        self,
        principal: Principal,
        request: InvocationEnvelope,
        reserve: Callable[[], bool] = lambda: True,
    ) -> AsyncGenerator[AdmittedCommand | Receipt | Rejection]:
        async with AsyncExitStack() as stack:
            try:
                result = await self._prepare(principal, request, stack, reserve)
            except Exception:
                result = rejection(
                    request.operation, request.correlation_id, "admission", "service_unavailable"
                )
            if not isinstance(result, AdmittedCommand):
                await stack.aclose()
            try:
                yield result
            finally:
                if isinstance(result, AdmittedCommand):
                    result.close()

    async def _prepare(
        self,
        principal: Principal,
        request: InvocationEnvelope,
        stack: AsyncExitStack,
        reserve: Callable[[], bool],
    ) -> AdmittedCommand | Receipt | Rejection:
        guarded = await self.guards.prepare(principal, request)
        if isinstance(guarded, Rejection):
            return guarded
        if not isinstance(guarded.prepared, PreparedCommand) or request.retry_key is None:
            return rejection(request.operation, request.correlation_id, "input", "invalid_input")
        intent = self._intent(principal, request, guarded, request.retry_key)
        retained = await self._find(principal, intent)
        if retained is not None:
            return retained
        if not reserve():
            return rejection(request.operation, request.correlation_id, "execution", "capacity")
        if guarded.descriptor.changes_business_state and set(
            pin.resource for pin in request.expected_versions
        ) != set(guarded.prepared.resources):
            return rejection(
                request.operation,
                request.correlation_id,
                "input",
                "invalid_input",
                ("expected_versions",),
            )
        try:
            lease = await stack.enter_async_context(
                self.execution_guard.acquire(intent.expected_versions)
            )
        except ports.GuardAcquisitionError as error:
            retained = await self._find(principal, intent)
            code = (
                "version_conflict"
                if isinstance(error.reason, ports.VersionConflict)
                else "service_unavailable"
            )
            return retained or rejection(request.operation, request.correlation_id, "guard", code)
        retained = await self._find(principal, intent)
        if retained is not None:
            return retained
        return await self._admit(principal, intent, guarded.prepared, lease)

    def _intent(
        self,
        principal: Principal,
        request: InvocationEnvelope,
        guarded: GuardedCall,
        caller_key: str,
    ) -> CommandIntent:
        prepared = guarded.prepared
        return CommandIntent(
            RetryKey(principal.deployment_scope, principal.subject, request.operation, caller_key),
            self.fingerprint(
                request.operation,
                prepared.canonical_content,
                prepared.resources,
                request.expected_versions,
            ),
            self.fingerprint.policy,
            request.correlation_id,
            guarded.capability_versions,
            prepared.resources,
            request.expected_versions,
        )

    async def _find(
        self, principal: Principal, intent: CommandIntent
    ) -> Receipt | Rejection | None:
        found = await self.journal.find(intent.retry_key)
        if isinstance(found, ports.Missing):
            return None
        return await self._retained(principal, intent, found)

    async def _retained(
        self, principal: Principal, intent: CommandIntent, found: ports.RetainedCommand
    ) -> Receipt | Rejection:
        key, correlation = intent.retry_key.operation, intent.correlation_id
        # Reject a provider returning another scope before inspecting its receipt.
        if found.intent.retry_key != intent.retry_key:
            return rejection(key, correlation, "admission", "service_unavailable")
        denied = await authorize(
            self.guards.access,
            principal,
            ports.ReceiptAccess(found.receipt.operation_id),
            key,
            correlation,
        )
        if denied is not None:
            return denied
        if (
            replace(
                found.intent,
                correlation_id=intent.correlation_id,
                capability_versions=intent.capability_versions,
            )
            != intent
        ):
            return rejection(key, correlation, "admission", "retry_conflict")
        receipt = await self.journal.read(found.receipt.operation_id)
        if isinstance(receipt, ports.Missing):
            return rejection(key, correlation, "admission", "receipt_missing")
        if (
            receipt.operation_id != found.receipt.operation_id
            or receipt.operation != key
            or receipt.resources != intent.resources
            or receipt.expected_versions != intent.expected_versions
        ):
            return rejection(key, correlation, "admission", "service_unavailable")
        return receipt

    async def _admit(
        self,
        principal: Principal,
        intent: CommandIntent,
        prepared: PreparedCommand,
        lease: ports.GuardLease,
    ) -> AdmittedCommand | Receipt | Rejection:
        result = await self.journal.admit(intent)
        if isinstance(result, ports.Admitted):
            # Read back the retained identity before granting effect authority.
            retained = await self._find(principal, intent)
            if isinstance(retained, Receipt) and retained == result.receipt:
                return AdmittedCommand(retained, principal, prepared, lease)
            return retained or rejection(
                intent.retry_key.operation,
                intent.correlation_id,
                "admission",
                "service_unavailable",
            )
        if isinstance(result, ports.Existing):
            return await self._retained(principal, intent, result.command)
        if isinstance(result, ports.ServiceUnavailable):
            retained = await self._find(principal, intent)
            if retained is not None:
                return retained
        code = (
            "retry_conflict"
            if isinstance(result, ports.AdmissionConflict)
            else "service_unavailable"
        )
        return rejection(intent.retry_key.operation, intent.correlation_id, "admission", code)
