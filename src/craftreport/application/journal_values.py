"""Atomic admission and observation values; only the journal owns receipts."""

from dataclasses import dataclass, field
from typing import Literal

from craftreport.application.service_values import Missing, ServiceUnavailable
from craftreport.contracts import (
    Availability,
    CapabilityVersion,
    CommandIntent,
    Diagnostic,
    EvidenceRef,
    ExpectedVersion,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    ResourceRef,
    StageResult,
)
from craftreport.contracts.identity import check_preconditions
from craftreport.contracts.values import require_enum, require_positive, require_text


@dataclass(frozen=True, slots=True)
class RetainedCommand:
    """One scoped retry identity plus its currently retained receipt."""

    intent: CommandIntent
    receipt: Receipt

    def __post_init__(self) -> None:
        if self.intent.retry_key.operation != self.receipt.operation:
            raise ValueError("Retained receipt must match the admitted operation")
        if (
            self.intent.resources != self.receipt.resources
            or self.intent.expected_versions != self.receipt.expected_versions
        ):
            raise ValueError("Retained receipt must match admitted resource preconditions")


@dataclass(frozen=True, slots=True)
class Admitted:
    receipt: Receipt
    kind: Literal["admitted"] = field(default="admitted", init=False)

    def __post_init__(self) -> None:
        if self.receipt.state is not ReceiptState.ACCEPTED or self.receipt.revision != 1:
            raise ValueError("Admission requires the initial accepted receipt")


@dataclass(frozen=True, slots=True)
class Existing:
    command: RetainedCommand
    kind: Literal["existing"] = field(default="existing", init=False)


@dataclass(frozen=True, slots=True)
class AdmissionConflict:
    """Different normalized content/preconditions; no protected receipt disclosure."""

    kind: Literal["conflict"] = field(default="conflict", init=False)


type Admission = Admitted | Existing | AdmissionConflict | ServiceUnavailable


@dataclass(frozen=True, slots=True)
class RevisionConflict:
    current_revision: int
    kind: Literal["revision_conflict"] = field(default="revision_conflict", init=False)

    def __post_init__(self) -> None:
        require_positive(self.current_revision, "current_revision")


@dataclass(frozen=True, slots=True)
class ReceiptUpdate:
    """Core-approved update; journal applies it with compare-and-set revision.

    Stages/evidence are appended, never used to erase prior observations. Outcome
    rules validate transitions and exact evidence pins before this value is sent.
    Result content is retained separately; handlers never receive this writer.
    """

    state: ReceiptState
    stages: tuple[StageResult, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    result_ref: str | None = None
    result_availability: Availability = Availability.MISSING
    handoff_ref: str | None = None

    def __post_init__(self) -> None:
        require_enum(self.state, ReceiptState)
        require_enum(self.result_availability, Availability)
        object.__setattr__(self, "stages", tuple(self.stages))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        for ref in (self.result_ref, self.handoff_ref):
            if ref is not None:
                require_text(ref, "observation reference")
        if self.result_availability is Availability.AVAILABLE and self.result_ref is None:
            raise ValueError("Available results require a result reference")


@dataclass(frozen=True, slots=True)
class QueryObservation:
    """Dispatcher audit observation; not command admission or a retry reservation."""

    operation_id: str
    principal: Principal
    operation: OperationKey
    correlation_id: str
    capability_versions: tuple[CapabilityVersion, ...]
    resources: tuple[ResourceRef, ...]
    expected_versions: tuple[ExpectedVersion, ...]
    update: ReceiptUpdate
    input_ref: str | None = None

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")
        require_text(self.correlation_id, "correlation_id")
        object.__setattr__(self, "capability_versions", tuple(self.capability_versions))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "expected_versions", tuple(self.expected_versions))
        check_preconditions(self.expected_versions)
        if self.input_ref is not None:
            require_text(self.input_ref, "input_ref")


type ReceiptRead = Receipt | Missing
type RecordResult = Receipt | RevisionConflict
