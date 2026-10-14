"""Framework-free guarantees supplied to the dispatcher and capability handlers.

These protocols specify obligations, not implementations. Authorization precedes
private diagnostics, lookup, and inspection. Concrete providers and dispatcher
enforcement are separate tasks; no local fallback can supply absent guarantees.
"""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from craftreport.application.journal_values import (
    Admission as Admission,
)
from craftreport.application.journal_values import (
    AdmissionConflict as AdmissionConflict,
)
from craftreport.application.journal_values import (
    Admitted as Admitted,
)
from craftreport.application.journal_values import (
    Existing as Existing,
)
from craftreport.application.journal_values import (
    QueryObservation as QueryObservation,
)
from craftreport.application.journal_values import (
    ReceiptRead as ReceiptRead,
)
from craftreport.application.journal_values import (
    ReceiptUpdate as ReceiptUpdate,
)
from craftreport.application.journal_values import (
    RecordResult as RecordResult,
)
from craftreport.application.journal_values import (
    RetainedCommand as RetainedCommand,
)
from craftreport.application.journal_values import (
    RevisionConflict as RevisionConflict,
)
from craftreport.application.service_values import (
    AccessAction as AccessAction,
)
from craftreport.application.service_values import (
    AccessAllowed as AccessAllowed,
)
from craftreport.application.service_values import (
    AccessDecision as AccessDecision,
)
from craftreport.application.service_values import (
    AccessDenied as AccessDenied,
)
from craftreport.application.service_values import (
    CapabilitiesSupported as CapabilitiesSupported,
)
from craftreport.application.service_values import (
    CapabilitiesUnsupported as CapabilitiesUnsupported,
)
from craftreport.application.service_values import (
    CapabilityDecision as CapabilityDecision,
)
from craftreport.application.service_values import (
    CatalogAccess as CatalogAccess,
)
from craftreport.application.service_values import (
    GuardCheck as GuardCheck,
)
from craftreport.application.service_values import (
    GuardCurrent as GuardCurrent,
)
from craftreport.application.service_values import (
    GuardLost as GuardLost,
)
from craftreport.application.service_values import (
    Missing as Missing,
)
from craftreport.application.service_values import (
    OperationAccess as OperationAccess,
)
from craftreport.application.service_values import (
    Preconditions as Preconditions,
)
from craftreport.application.service_values import (
    ReceiptAccess as ReceiptAccess,
)
from craftreport.application.service_values import (
    ResourceEffect as ResourceEffect,
)
from craftreport.application.service_values import (
    ResourceEffectResult as ResourceEffectResult,
)
from craftreport.application.service_values import (
    ResourceSnapshot as ResourceSnapshot,
)
from craftreport.application.service_values import (
    ServiceUnavailable as ServiceUnavailable,
)
from craftreport.application.service_values import (
    VersionConflict as VersionConflict,
)
from craftreport.contracts import (
    CapabilityRequirement,
    Catalog,
    CommandIntent,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    InvocationEnvelope,
    InvocationResult,
    JsonObject,
    Principal,
    Receipt,
    Rejection,
    ResourceRef,
    ResultReadback,
    RetryKey,
)
from craftreport.contracts.values import require_text


class CatalogRejected(Exception):
    """Structured discovery rejection; never expose raw provider exceptions."""

    def __init__(self, rejection: Rejection) -> None:
        super().__init__("Catalog discovery rejected")
        self.rejection = rejection


class GuardAcquisitionError(Exception):
    """Expected structured acquisition failure; no lease was granted."""

    def __init__(self, reason: VersionConflict | ServiceUnavailable) -> None:
        super().__init__("Version guard acquisition failed")
        self.reason = reason


class ServiceUnavailableError(Exception):
    """Expected provider failure, distinct from authoritative missing content."""

    def __init__(self, reason: ServiceUnavailable) -> None:
        super().__init__("Required service unavailable")
        self.reason = reason


class ReceiptMissingError(Exception):
    """A conditional update cannot apply because its receipt is not retained."""

    def __init__(self, operation_id: str) -> None:
        require_text(operation_id, "operation_id")
        super().__init__("Receipt unavailable for conditional update")
        self.operation_id = operation_id
        self.reason = Missing()


class Facade(Protocol):
    """All ingress shares these authorized operations.

    Catalog is filtered per operation; inspection applies receipt/resource
    visibility. Missing/unavailable or denied content is a safe Rejection, never
    an invented successful receipt. Discovery raises CatalogRejected for denial
    or unavailability. Built-in inspection creates no business work.
    """

    async def invoke(
        self, principal: Principal, request: InvocationEnvelope
    ) -> InvocationResult: ...

    async def catalog(self, principal: Principal) -> Catalog: ...

    async def inspect(self, principal: Principal, operation_id: str) -> Receipt | Rejection: ...

    async def read_result(
        self, principal: Principal, operation_id: str
    ) -> ResultReadback | Rejection: ...


class AccessPolicy(Protocol):
    """Apply trusted principal scope to operation, referenced resources or receipt.

    Unavailable is not permission. Providers must not disclose protected content
    in denials; coarse operation checks precede private schema validation.
    """

    async def authorize(self, principal: Principal, action: AccessAction) -> AccessDecision: ...


class OperationJournal(Protocol):
    """Canonical owner of accepted identity and append-only observations.

    find is scoped by server-derived deployment and subject plus exact operation,
    contract version and caller key. Missing asserts known absence; uncertain
    retention raises ServiceUnavailableError. No automatic eviction in conformance runs.
    admit atomically stores that identity and initial receipt before admitted;
    concurrent equivalent requests get existing; different normalized content or
    preconditions conflict. Lost acknowledgement requires lookup/reconciliation,
    never a blind effect or second execution. Retention/epoch is reported in receipts.
    record compares the revision, applies legal transitions and appends evidence
    atomically with a monotonically incremented revision. Terminal observations
    cannot be overwritten; resolving ambiguity needs new reconciliation evidence.
    Providers retain ownership metadata so access decisions can protect reads.
    All methods except admit raise ServiceUnavailableError on provider failure;
    admit returns its mandated unavailable variant. record raises ReceiptMissingError
    for known missing retention. Missing must never stand in for uncertain retention.
    """

    async def find(self, key: RetryKey) -> RetainedCommand | Missing: ...

    async def admit(self, intent: CommandIntent) -> Admission: ...

    async def record(
        self, operation_id: str, expected_revision: int, update: ReceiptUpdate
    ) -> RecordResult: ...

    async def read(self, operation_id: str) -> ReceiptRead: ...

    async def record_query(self, observation: QueryObservation) -> Receipt: ...


class GuardLease(Protocol):
    """Provider-owned authoritative version protection, valid only inside acquire.

    assert_current must run immediately before effect; unavailable or lost blocks
    starting dependent work. On loss stop ongoing work where possible, otherwise
    report unknown effect requiring reconciliation. This is no distributed fence.
    """

    @property
    def authoritative_versions(self) -> tuple[ExpectedVersion, ...]: ...

    async def assert_current(self) -> GuardCheck: ...


class ExecutionGuard(Protocol):
    """Compare expected versions with authoritative state while obtaining lease.

    A conflicting/unavailable acquisition raises GuardAcquisitionError on entry,
    yielding no lease. Exit releases resources even for cancellation or a losing
    admission race; it never cancels admitted execution owned elsewhere.
    Implementations must document their fence scope.
    """

    def acquire(self, preconditions: Preconditions) -> AbstractAsyncContextManager[GuardLease]: ...


class CapabilityResolver(Protocol):
    """Check exact capability/version requirements and target modes before effect."""

    async def check(
        self, requirements: tuple[CapabilityRequirement, ...], resources: tuple[ResourceRef, ...]
    ) -> CapabilityDecision: ...


class EvidenceReader(Protocol):
    """One status per input reference in input order; never regenerate content.

    Available, missing, inaccessible and provider-unavailable remain distinct.
    Whole-service failure returns unavailable for every requested reference;
    callers must authorize references and preflight required provider health.
    """

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]: ...


class ResourceReader(Protocol):
    """Inspect existing authorized resource state without starting business work."""

    async def read(
        self, resource: ResourceRef
    ) -> ResourceSnapshot | Missing | ServiceUnavailable: ...


class ResourceEffects(Protocol):
    """Apply a declared resource change with the current provider guard.

    Change fields follow the capability's validated operation schema; no method
    names, registry dispatch or journal completion are accepted. Domain behavior
    remains in the handler, which combines this observation into OutcomeProposal.
    Extra purpose-specific collaborators may be factory-injected into handlers.
    """

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: GuardLease
    ) -> ResourceEffectResult: ...


@dataclass(frozen=True, slots=True)
class ReadServices:
    evidence: EvidenceReader
    capabilities: CapabilityResolver
    resources: ResourceReader


@dataclass(frozen=True, slots=True)
class CommandServices:
    reads: ReadServices
    effects: ResourceEffects


@dataclass(frozen=True, slots=True)
class ReadContext:
    operation_id: str
    principal: Principal
    services: ReadServices

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")
        if type(self.services) is not ReadServices:
            raise TypeError("ReadContext requires explicitly read-only services")


@dataclass(frozen=True, slots=True)
class CommandContext:
    operation_id: str
    principal: Principal
    guard: GuardLease
    services: CommandServices

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")
