"""Functional completion policy over dispatcher-observed facts."""

from dataclasses import dataclass, replace
from enum import StrEnum

from craftreport.application.journal_values import ReceiptUpdate
from craftreport.application.registry import ObservedCommand
from craftreport.application.service_values import DiagnosticPolicy as DiagnosticPolicy
from craftreport.contracts import (
    Availability,
    Diagnostic,
    EffectDisposition,
    EvidencePolicy,
    EvidenceRef,
    EvidenceStatus,
    ExpectedVersion,
    OperationKey,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    Rejection,
    StageResult,
    StageState,
)
from craftreport.contracts.identity import check_preconditions
from craftreport.contracts.values import require_enum, require_text


class ResultValidation(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class OutcomeFacts:
    """Trusted dispatcher facts, never fields decoded from a handler proposal.

    Completion versions are authoritative observed target versions. They can
    differ from the receipt's admission preconditions after a mutation.
    """

    result_validation: ResultValidation
    result_ref: str | None
    result_availability: Availability
    completion_versions: tuple[ExpectedVersion, ...]
    evidence: tuple[EvidenceStatus, ...] = ()
    recorded_handoff: str | None = None
    reconciliation: tuple[EvidenceRef, ...] = ()
    prior_handoff: str | None = None

    def __post_init__(self) -> None:
        require_enum(self.result_validation, ResultValidation)
        require_enum(self.result_availability, Availability)
        for name in ("completion_versions", "evidence", "reconciliation"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        check_preconditions(self.completion_versions)
        for reference in (self.result_ref, self.recorded_handoff, self.prior_handoff):
            if reference is not None:
                require_text(reference, "observation reference")
        if self.result_availability is Availability.AVAILABLE and self.result_ref is None:
            raise ValueError("Available results require a result reference")


def outcome_update(
    current: Receipt,
    observation: ObservedCommand,
    facts: OutcomeFacts,
    evidence_policy: EvidencePolicy,
    diagnostic_policy: DiagnosticPolicy = DiagnosticPolicy(),
) -> ReceiptUpdate:
    """Approve observations; retry lookup must return its retained receipt directly."""
    require_enum(observation.effect, EffectDisposition)
    diagnostics = list(sanitize_diagnostics(current, observation.diagnostics, diagnostic_policy))
    failures = _completion_failures(current, observation, facts, evidence_policy)
    diagnostics.extend(_diagnostic(current, stage, code) for stage, code in failures)
    if failures or observation.effect in (EffectDisposition.UNKNOWN, EffectDisposition.PARTIAL):
        diagnostics.append(
            Diagnostic(
                current.operation,
                "effect",
                f"effect_{observation.effect.value}",
                RecoveryDisposition.RECONCILE
                if observation.effect is EffectDisposition.UNKNOWN
                else RecoveryDisposition.INSPECT,
            )
        )
    state = _state(observation, facts, bool(failures))
    if observation.handoff_ref is not None and facts.recorded_handoff != observation.handoff_ref:
        diagnostics.append(_diagnostic(current, "execution", "handoff_unverified"))
    _validate_transition(current, state, observation, facts)
    allowed_stages = set(evidence_policy.required_stages) | {
        item[0] for item in diagnostic_policy.allowed
    }
    stages = _validated_stages(observation, evidence_policy, allowed_stages, failures)
    return ReceiptUpdate(
        state,
        stages,
        tuple(diagnostics),
        observation.evidence,
        facts.result_ref,
        facts.result_availability,
        observation.handoff_ref if state is ReceiptState.PENDING else None,
    )


def _diagnostic(current: Receipt, stage: str, code: str) -> Diagnostic:
    return Diagnostic(current.operation, stage, code, RecoveryDisposition.INSPECT)


def _validated_stages(
    observation: ObservedCommand,
    policy: EvidencePolicy,
    allowed: set[str],
    failures: list[tuple[str, str]],
) -> tuple[StageResult, ...]:
    stages = [
        replace(stage, reason_code="observed")
        for stage in observation.stages
        if stage.stage in allowed and stage.stage not in policy.required_stages
    ]
    for name in policy.required_stages:
        codes = [code for stage, code in failures if stage == name]
        references = tuple(
            ref for stage in observation.stages if stage.stage == name for ref in stage.evidence
        )
        state = StageState.PASSED
        if codes:
            state = (
                StageState.FAILED
                if any(
                    code.endswith(("failed", "invalid", "mismatch", "not_applicable"))
                    for code in codes
                )
                else StageState.PENDING
            )
        stages.append(StageResult(name, state, codes[0] if codes else "verified", references))
    return tuple(stages)


def _completion_failures(
    current: Receipt,
    observation: ObservedCommand,
    facts: OutcomeFacts,
    policy: EvidencePolicy,
) -> list[tuple[str, str]]:
    failures: list[tuple[str, str]] = []
    if facts.result_validation is not ResultValidation.VALID:
        failures.append(("result", f"result_{facts.result_validation.value}"))
    if facts.result_availability is not Availability.AVAILABLE:
        failures.append(("result", f"result_{facts.result_availability.value}"))
    for name in policy.required_stages:
        stages = [stage for stage in observation.stages if stage.stage == name]
        if len(stages) > 1:
            failures.append((name, "evidence_invalid"))
            continue
        if stages and stages[0].state is not StageState.PASSED:
            failures.append((name, f"stage_{stages[0].state.value}"))
        if not stages or not stages[0].evidence:
            failures.append((name, "evidence_missing"))
            continue
        stage = stages[0]
        for reference in stage.evidence:
            code = _evidence_failure(current, reference, observation, facts)
            if code is not None:
                failures.append((name, code))
    return failures


def _evidence_failure(
    current: Receipt,
    reference: EvidenceRef,
    observation: ObservedCommand,
    facts: OutcomeFacts,
) -> str | None:
    if reference not in observation.evidence:
        return "evidence_missing"
    if (
        reference.operation_id != current.operation_id
        or reference.operation != current.operation
        or set(reference.resource_versions) != set(facts.completion_versions)
        or {pin.resource for pin in facts.completion_versions} != set(current.resources)
    ):
        return "evidence_mismatch"
    matches = [status for status in facts.evidence if status.reference == reference]
    if len(matches) != 1:
        return "evidence_unresolved"
    status = matches[0]
    if status.availability is not Availability.AVAILABLE:
        return f"evidence_{status.availability.value}"
    if status.verification is not StageState.PASSED:
        return f"evidence_{status.verification.value}"
    return None


def _state(observation: ObservedCommand, facts: OutcomeFacts, failed: bool) -> ReceiptState:
    if observation.effect is EffectDisposition.UNKNOWN:
        return ReceiptState.AMBIGUOUS
    if observation.effect is EffectDisposition.PARTIAL:
        return ReceiptState.PARTIAL
    if observation.handoff_ref is not None:
        if facts.recorded_handoff == observation.handoff_ref:
            return ReceiptState.PENDING
        failed = True
    if not failed:
        return ReceiptState.COMPLETE
    return (
        ReceiptState.PARTIAL
        if observation.effect is EffectDisposition.APPLIED
        else ReceiptState.FAILED
    )


def _validate_transition(
    current: Receipt,
    state: ReceiptState,
    observation: ObservedCommand,
    facts: OutcomeFacts,
) -> None:
    if current.state in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
        raise ValueError("Terminal receipt transition is forbidden")
    if current.state is ReceiptState.PENDING and state is ReceiptState.PENDING:
        if facts.prior_handoff is None or facts.recorded_handoff == facts.prior_handoff:
            raise ValueError("Pending receipt transition requires a new verified owner")
    if current.state is not ReceiptState.AMBIGUOUS:
        return
    if state in (ReceiptState.ACCEPTED, ReceiptState.PENDING, ReceiptState.AMBIGUOUS):
        raise ValueError("Ambiguous transition requires terminal reconciliation")
    prior = {ref.identity for ref in current.evidence}
    prior.update(ref.identity for stage in current.stages for ref in stage.evidence)
    if not facts.reconciliation or any(
        ref.identity in prior
        or ref.scope != "reconciliation"
        or _evidence_failure(current, ref, observation, facts) is not None
        for ref in facts.reconciliation
    ):
        raise ValueError("New verified reconciliation evidence is required")


def validate_recorded_update(before: Receipt, after: Receipt, update: ReceiptUpdate) -> None:
    """Check journal readback against its approved update without rewriting history.

    The dispatcher must supply an update from outcome_update; this verifies the
    journal's append/CAS contract, not evidence a second time.
    """
    expected = replace(
        before,
        revision=before.revision + 1,
        state=update.state,
        stages=before.stages + update.stages,
        diagnostics=before.diagnostics + update.diagnostics,
        evidence=before.evidence + update.evidence,
        result_ref=update.result_ref,
        result_availability=update.result_availability,
    )
    if after != expected:
        raise ValueError(
            "Recorded receipt must preserve identity, append history and advance one revision"
        )


def sanitize_diagnostics(
    current: Receipt, diagnostics: tuple[Diagnostic, ...], policy: DiagnosticPolicy
) -> tuple[Diagnostic, ...]:
    return tuple(
        diagnostic
        for diagnostic in diagnostics
        if diagnostic.operation == current.operation
        and (diagnostic.stage, diagnostic.code, diagnostic.recovery) in policy.allowed
        and diagnostic.location in policy.locations
    )


def reject_request(
    operation: OperationKey,
    correlation_id: str,
    diagnostic: Diagnostic,
    policy: DiagnosticPolicy = DiagnosticPolicy(),
) -> Rejection:
    """Reject without inventing an accepted receipt or disclosing unsafe tokens."""
    if (
        diagnostic.operation != operation
        or (diagnostic.stage, diagnostic.code, diagnostic.recovery) not in policy.allowed
        or diagnostic.location not in policy.locations
    ):
        diagnostic = Diagnostic(
            operation, "invocation", "rejected", RecoveryDisposition.DO_NOT_RETRY
        )
    return Rejection(correlation_id, diagnostic)
