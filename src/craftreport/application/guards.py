"""Fixed invocation preflight, before any query behavior or command admission."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from craftreport.application import ports
from craftreport.application.dispatch_ports import InvocationLimits, ServiceHealth, WireFailure
from craftreport.application.registry import OperationRegistry, PreparedCall
from craftreport.contracts import (
    CapabilityVersion,
    Diagnostic,
    InvocationEnvelope,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    Principal,
    RecoveryDisposition,
    Rejection,
)


def rejection(
    key: OperationKey,
    correlation: str,
    stage: str,
    code: str,
    location: tuple[str | int, ...] = (),
) -> Rejection:
    recovery = (
        RecoveryDisposition.RETRY
        if code in ("service_unavailable", "capacity")
        else RecoveryDisposition.CORRECT_REQUEST
    )
    return Rejection(correlation, Diagnostic(key, stage, code, recovery, location))


@dataclass(frozen=True, slots=True)
class GuardedCall:
    descriptor: OperationDescriptor
    prepared: PreparedCall
    capability_versions: tuple[CapabilityVersion, ...]


@dataclass(frozen=True, slots=True)
class InvocationGuards:
    registry: OperationRegistry
    access: ports.AccessPolicy
    capabilities: ports.CapabilityResolver
    health: ServiceHealth
    limits: InvocationLimits

    async def prepare(
        self, principal: Principal, request: InvocationEnvelope
    ) -> GuardedCall | Rejection:
        try:
            return await self._prepare(principal, request)
        except Exception:
            return rejection(
                request.operation, request.correlation_id, "preflight", "service_unavailable"
            )

    async def _prepare(
        self, principal: Principal, request: InvocationEnvelope
    ) -> GuardedCall | Rejection:
        denied = await authorize(
            self.access,
            principal,
            ports.OperationAccess(request.operation),
            request.operation,
            request.correlation_id,
        )
        if denied is not None:
            return denied
        bound = self.registry.resolve(request.operation.name, request.operation.contract_version)
        if bound is None:
            return rejection(
                request.operation, request.correlation_id, "resolve", "unsupported_operation"
            )
        try:
            self.limits.check(request, bound.descriptor.limits)
            prepared = bound.prepare(request.payload)
        except WireFailure as error:
            return validation_rejection(request, error, bound.descriptor)
        except Exception:
            return rejection(request.operation, request.correlation_id, "input", "invalid_input")
        denied = await authorize(
            self.access,
            principal,
            ports.OperationAccess(request.operation, prepared.resources),
            request.operation,
            request.correlation_id,
        )
        if denied is not None:
            return denied
        if any(pin.resource not in prepared.resources for pin in request.expected_versions):
            return rejection(
                request.operation,
                request.correlation_id,
                "input",
                "invalid_input",
                ("expected_versions",),
            )
        unavailable = await self.health.check(required_services(bound.descriptor))
        if unavailable is not None:
            return rejection(
                request.operation, request.correlation_id, "preflight", "service_unavailable"
            )
        decision = await self.capabilities.check(
            bound.descriptor.required_capabilities, prepared.resources
        )
        if not isinstance(decision, ports.CapabilitiesSupported):
            code = (
                "unsupported_capability"
                if isinstance(decision, ports.CapabilitiesUnsupported)
                else "service_unavailable"
            )
            return rejection(request.operation, request.correlation_id, "preflight", code)
        return GuardedCall(bound.descriptor, prepared, decision.versions)


def required_services(descriptor: OperationDescriptor) -> tuple[str, ...]:
    core = ["access", "journal", "capabilities", "results"]
    if descriptor.resources:
        core.append("resources")
    if descriptor.completion_evidence.required_stages:
        core.append("evidence")
    if descriptor.kind is OperationKind.COMMAND:
        core.append("guard")
    return tuple(dict.fromkeys((*core, *descriptor.required_services)))


async def authorize(
    access: ports.AccessPolicy,
    principal: Principal,
    action: ports.AccessAction,
    key: OperationKey,
    correlation: str,
) -> Rejection | None:
    decision = await access.authorize(principal, action)
    if isinstance(decision, ports.AccessAllowed):
        return None
    code = "access_denied" if isinstance(decision, ports.AccessDenied) else "service_unavailable"
    return rejection(key, correlation, "access", code)


def validation_rejection(
    request: InvocationEnvelope, error: WireFailure, descriptor: OperationDescriptor
) -> Rejection:
    limits = {"max_input_bytes", "max_nesting_depth", "max_output_bytes"}
    if error.limit in limits:
        return rejection(
            request.operation, request.correlation_id, "input", "limit_exceeded", (error.limit,)
        )
    properties = descriptor.input_schema.get("properties")
    fields: set[str] = set(properties) if isinstance(properties, Mapping) else set()
    location = tuple(
        part
        for part in error.location
        if (type(part) is int and part >= 0)
        or (
            isinstance(part, str)
            and part in fields
            and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}", part)
        )
    )
    return rejection(request.operation, request.correlation_id, "input", "invalid_input", location)
