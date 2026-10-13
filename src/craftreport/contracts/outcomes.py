"""Recorded outcome values; completion and transition policy lives in application."""

import re
from dataclasses import dataclass
from enum import StrEnum

from craftreport.contracts.identity import (
    CapabilityVersion,
    ExpectedVersion,
    OperationKey,
    ResourceRef,
    check_preconditions,
)
from craftreport.contracts.values import (
    require_enum,
    require_immutable,
    require_positive,
    require_text,
)


class ReceiptState(StrEnum):
    ACCEPTED = "accepted"
    PENDING = "pending"
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    FAILED = "failed"


class StageState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"


class Availability(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"
    UNAVAILABLE = "unavailable"


class EffectDisposition(StrEnum):
    NONE = "none"
    APPLIED = "applied"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class RecoveryDisposition(StrEnum):
    DO_NOT_RETRY = "do_not_retry"
    CORRECT_REQUEST = "correct_request"
    RETRY = "retry"
    INSPECT = "inspect"
    RECONCILE = "reconcile"


def _require_token(value: str, field: str) -> None:
    if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]{0,63}", value) is None:
        raise ValueError(f"{field} must be a structured token")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Structured fields only; the outcome boundary authorizes token disclosure."""

    operation: OperationKey
    stage: str
    code: str
    recovery: RecoveryDisposition
    location: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        _require_token(self.stage, "stage")
        _require_token(self.code, "code")
        require_enum(self.recovery, RecoveryDisposition)
        object.__setattr__(self, "location", tuple(self.location))
        for segment in self.location:
            if isinstance(segment, str):
                _require_token(segment, "location")
            elif type(segment) is not int or segment < 0:
                raise ValueError("Location indices must be nonnegative integers")


@dataclass(frozen=True, slots=True)
class Rejection:
    """No accepted operation identity exists for a rejected invocation."""

    correlation_id: str
    diagnostic: Diagnostic

    def __post_init__(self) -> None:
        require_text(self.correlation_id, "correlation_id")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    identity: str
    scope: str
    operation_id: str
    operation: OperationKey
    resource_versions: tuple[ExpectedVersion, ...] = ()
    content_digest: str | None = None

    def __post_init__(self) -> None:
        require_text(self.identity, "evidence identity")
        if "/" in self.identity or "\\" in self.identity or self.identity in (".", ".."):
            raise ValueError("Evidence identity must be opaque, not a filesystem path")
        require_text(self.scope, "evidence scope")
        require_text(self.operation_id, "operation_id")
        if self.content_digest is not None:
            require_text(self.content_digest, "content_digest")
        object.__setattr__(self, "resource_versions", tuple(self.resource_versions))
        check_preconditions(self.resource_versions)


@dataclass(frozen=True, slots=True)
class StageResult:
    stage: str
    state: StageState
    reason_code: str
    evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        _require_token(self.stage, "stage")
        _require_token(self.reason_code, "reason_code")
        require_enum(self.state, StageState)
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True, slots=True)
class EvidenceStatus:
    reference: EvidenceRef
    availability: Availability
    verification: StageState = StageState.PENDING

    def __post_init__(self) -> None:
        require_enum(self.availability, Availability)
        require_enum(self.verification, StageState)
        if (
            self.availability is not Availability.AVAILABLE
            and self.verification is not StageState.PENDING
        ):
            raise ValueError("Unavailable content cannot carry an observed verification result")


@dataclass(frozen=True, slots=True)
class OutcomeProposal[R]:
    """Handler observation, without authority to assign canonical receipt state."""

    result: R | None
    effect: EffectDisposition
    stages: tuple[StageResult, ...]
    evidence: tuple[EvidenceRef, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    handoff_ref: str | None = None

    def __post_init__(self) -> None:
        require_immutable(self.result)
        require_enum(self.effect, EffectDisposition)
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.handoff_ref is not None:
            require_text(self.handoff_ref, "handoff_ref")


@dataclass(frozen=True, slots=True)
class Receipt:
    operation_id: str
    operation: OperationKey
    correlation_id: str
    revision: int
    state: ReceiptState
    capability_versions: tuple[CapabilityVersion, ...]
    resources: tuple[ResourceRef, ...]
    expected_versions: tuple[ExpectedVersion, ...]
    input_ref: str | None
    result_ref: str | None
    stages: tuple[StageResult, ...]
    diagnostics: tuple[Diagnostic, ...]
    evidence: tuple[EvidenceRef, ...]
    deployment_epoch: str
    retention_profile: str
    result_availability: Availability = Availability.MISSING
    previous_operation_id: str | None = None

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")
        require_text(self.correlation_id, "correlation_id")
        require_text(self.deployment_epoch, "deployment_epoch")
        require_text(self.retention_profile, "retention_profile")
        require_positive(self.revision, "revision")
        require_enum(self.state, ReceiptState)
        require_enum(self.result_availability, Availability)
        if self.result_availability is Availability.AVAILABLE and self.result_ref is None:
            raise ValueError("Available results require a result reference")
        for ref in (self.input_ref, self.result_ref, self.previous_operation_id):
            if ref is not None:
                require_text(ref, "receipt reference")
        object.__setattr__(self, "capability_versions", tuple(self.capability_versions))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "expected_versions", tuple(self.expected_versions))
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        check_preconditions(self.expected_versions)


type InvocationResult = Receipt | Rejection
