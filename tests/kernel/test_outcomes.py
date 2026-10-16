"""Policy tests use typed observations; provider atomicity belongs to later tasks."""

from dataclasses import replace
from typing import cast

import pytest

from craftreport.application.outcomes import (
    DiagnosticPolicy,
    OutcomeFacts,
    ResultValidation,
    outcome_update,
    reject_request,
    sanitize_diagnostics,
    validate_recorded_update,
)
from craftreport.application.registry import ObservedCommand
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
    ResourceRef,
    StageResult,
    StageState,
)

KEY = OperationKey("fixture.set", "1")
RESOURCE = ResourceRef("fixture", "target")
PIN = ExpectedVersion(RESOURCE, "2")
PROOF = EvidenceRef("proof", "synthetic", "operation", KEY, (PIN,), "digest")
POLICY = EvidencePolicy(("readback",))
PASSED = EvidenceStatus(PROOF, Availability.AVAILABLE, StageState.PASSED)


def receipt(state: ReceiptState = ReceiptState.ACCEPTED) -> Receipt:
    return Receipt(
        "operation",
        KEY,
        "correlation",
        1,
        state,
        (),
        (RESOURCE,),
        (ExpectedVersion(RESOURCE, "1"),),
        "input",
        None,
        (),
        (),
        (),
        "epoch",
        "temporary",
        previous_operation_id="prior-attempt",
    )


def observation(effect: EffectDisposition = EffectDisposition.APPLIED) -> ObservedCommand:
    return ObservedCommand(
        effect,
        (StageResult("readback", StageState.PASSED, "checked", (PROOF,)),),
        (PROOF,),
        (),
        None,
        lambda: {"value": 2},
    )


def facts() -> OutcomeFacts:
    return OutcomeFacts(ResultValidation.VALID, "result", Availability.AVAILABLE, (PIN,), (PASSED,))


@pytest.mark.parametrize(
    "effect,expected",
    [
        (EffectDisposition.NONE, ReceiptState.COMPLETE),
        (EffectDisposition.APPLIED, ReceiptState.COMPLETE),
        (EffectDisposition.PARTIAL, ReceiptState.PARTIAL),
        (EffectDisposition.UNKNOWN, ReceiptState.AMBIGUOUS),
    ],
)
@pytest.mark.parametrize("validation", list(ResultValidation))
def test_effect_result_matrix(
    effect: EffectDisposition, expected: ReceiptState, validation: ResultValidation
) -> None:
    if validation is not ResultValidation.VALID and expected is ReceiptState.COMPLETE:
        expected = ReceiptState.FAILED if effect is EffectDisposition.NONE else ReceiptState.PARTIAL
    update = outcome_update(
        receipt(), observation(effect), replace(facts(), result_validation=validation), POLICY
    )
    assert update.state is expected
    if validation is not ResultValidation.VALID:
        assert any(d.code == f"effect_{effect.value}" for d in update.diagnostics)
        assert any(
            d.stage == "result" and d.code == f"result_{validation.value}"
            for d in update.diagnostics
        )


@pytest.mark.parametrize("availability", list(Availability))
def test_result_retention_is_not_result_validation(availability: Availability) -> None:
    update = outcome_update(
        receipt(), observation(), replace(facts(), result_availability=availability), POLICY
    )
    assert update.result_availability is availability
    assert (update.state is ReceiptState.COMPLETE) == (availability is Availability.AVAILABLE)


@pytest.mark.parametrize(
    "availability", [Availability.MISSING, Availability.INACCESSIBLE, Availability.UNAVAILABLE]
)
def test_evidence_availability_is_preserved(availability: Availability) -> None:
    update = outcome_update(
        receipt(),
        observation(),
        replace(facts(), evidence=(EvidenceStatus(PROOF, availability),)),
        POLICY,
    )
    assert update.state is ReceiptState.PARTIAL
    assert any(
        d.stage == "readback" and d.code == f"evidence_{availability.value}"
        for d in update.diagnostics
    )


@pytest.mark.parametrize(
    "state", [StageState.FAILED, StageState.PENDING, StageState.NOT_APPLICABLE]
)
def test_self_claimed_pass_does_not_override_reader(state: StageState) -> None:
    update = outcome_update(
        receipt(),
        observation(),
        replace(facts(), evidence=(replace(PASSED, verification=state),)),
        POLICY,
    )
    assert update.state is ReceiptState.PARTIAL
    assert update.stages[0].state is not StageState.PASSED


@pytest.mark.parametrize(
    "bad",
    [
        replace(PROOF, operation_id="other"),
        replace(PROOF, operation=OperationKey("fixture.set", "2")),
        replace(PROOF, resource_versions=()),
        replace(PROOF, resource_versions=(ExpectedVersion(RESOURCE, "3"),)),
        replace(PROOF, content_digest="different"),
        replace(PROOF, scope="other"),
    ],
)
def test_reader_must_match_full_evidence_reference(bad: EvidenceRef) -> None:
    update = outcome_update(
        receipt(),
        observation(),
        replace(facts(), evidence=(replace(PASSED, reference=bad),)),
        POLICY,
    )
    assert update.state is ReceiptState.PARTIAL


def test_missing_duplicate_and_unlinked_evidence_cannot_complete() -> None:
    variants = [
        replace(observation(), stages=()),
        replace(observation(), evidence=()),
        replace(observation(), stages=observation().stages * 2),
        replace(observation(), stages=(StageResult("readback", StageState.PASSED, "ok"),)),
    ]
    for observed in variants:
        assert outcome_update(receipt(), observed, facts(), POLICY).state is ReceiptState.PARTIAL
    assert (
        outcome_update(
            receipt(), observation(), replace(facts(), evidence=(PASSED, PASSED)), POLICY
        ).state
        is ReceiptState.PARTIAL
    )


def test_pending_requires_matching_recorded_installed_owner() -> None:
    observed = replace(observation(EffectDisposition.NONE), handoff_ref="owner-job")
    for recorded in (None, "different-owner-job"):
        update = outcome_update(
            receipt(), observed, replace(facts(), recorded_handoff=recorded), POLICY
        )
        assert update.state is ReceiptState.FAILED
        assert any(d.code == "handoff_unverified" for d in update.diagnostics)
    assert (
        outcome_update(
            receipt(), observed, replace(facts(), recorded_handoff="owner-job"), POLICY
        ).state
        is ReceiptState.PENDING
    )


@pytest.mark.parametrize(
    "state", [ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED]
)
def test_terminal_receipts_are_immutable(state: ReceiptState) -> None:
    with pytest.raises(ValueError, match="transition"):
        outcome_update(receipt(state), observation(), facts(), POLICY)


def test_ambiguity_requires_new_verified_reconciliation() -> None:
    before = replace(receipt(ReceiptState.AMBIGUOUS), evidence=(PROOF,))
    with pytest.raises(ValueError, match="reconciliation"):
        outcome_update(before, observation(), facts(), POLICY)
    with pytest.raises(ValueError, match="reconciliation"):
        outcome_update(before, observation(), replace(facts(), reconciliation=(PROOF,)), POLICY)
    new = replace(PROOF, identity="reconciliation-proof", scope="reconciliation")
    observed = replace(observation(), evidence=(PROOF, new))
    verified = replace(
        facts(), evidence=(PASSED, replace(PASSED, reference=new)), reconciliation=(new,)
    )
    assert outcome_update(before, observed, verified, POLICY).state is ReceiptState.COMPLETE
    assert before.evidence == (PROOF,)


def test_sanitization_rejects_token_shaped_secrets_and_wrong_identity() -> None:
    safe = Diagnostic(KEY, "result", "invalid", RecoveryDisposition.CORRECT_REQUEST, ("amount",))
    policy = DiagnosticPolicy(
        frozenset({("result", "invalid", RecoveryDisposition.CORRECT_REQUEST)}),
        frozenset({("amount",)}),
    )
    unsafe = (
        replace(safe, code="secret_password"),
        replace(safe, stage="private_schema"),
        replace(safe, location=("private_field",)),
        replace(safe, operation=OperationKey("other", "1")),
    )
    assert sanitize_diagnostics(receipt(), (safe, *unsafe), policy) == (safe,)
    update = outcome_update(receipt(), replace(observation(), diagnostics=unsafe), facts(), POLICY)
    assert not update.diagnostics
    assert all(stage.reason_code != "checked" for stage in update.stages)


def test_recorded_update_preserves_identity_history_and_revision() -> None:
    before = replace(receipt(), evidence=(PROOF,), stages=observation().stages)
    update = outcome_update(before, observation(), facts(), POLICY)
    after = replace(
        before,
        state=update.state,
        revision=2,
        evidence=before.evidence + update.evidence,
        stages=before.stages + update.stages,
        diagnostics=before.diagnostics + update.diagnostics,
        result_ref=update.result_ref,
        result_availability=update.result_availability,
    )
    validate_recorded_update(before, after, update)
    invalid = [
        replace(after, revision=1),
        replace(after, revision=3),
        replace(after, previous_operation_id=None),
        replace(after, operation_id="new"),
        replace(after, evidence=()),
        replace(after, stages=()),
    ]
    for changed in invalid:
        with pytest.raises(ValueError):
            validate_recorded_update(before, changed, update)


@pytest.mark.parametrize("effect", list(EffectDisposition))
def test_pending_may_progress_to_each_observed_terminal(effect: EffectDisposition) -> None:
    before = receipt(ReceiptState.PENDING)
    update = outcome_update(before, observation(effect), facts(), POLICY)
    assert update.state not in (ReceiptState.ACCEPTED, ReceiptState.PENDING)
    observed = replace(observation(effect), handoff_ref="owner")
    if effect in (EffectDisposition.NONE, EffectDisposition.APPLIED):
        with pytest.raises(ValueError, match="transition"):
            outcome_update(before, observed, replace(facts(), recorded_handoff="owner"), POLICY)


@pytest.mark.parametrize(
    "state", [StageState.FAILED, StageState.PENDING, StageState.NOT_APPLICABLE]
)
def test_failed_required_stage_cannot_be_overruled_by_passing_reader(state: StageState) -> None:
    observed = replace(observation(), stages=(replace(observation().stages[0], state=state),))
    update = outcome_update(receipt(), observed, facts(), POLICY)
    assert update.state is ReceiptState.PARTIAL
    assert any(
        d.stage == "readback" and d.code == f"stage_{state.value}" for d in update.diagnostics
    )


@pytest.mark.parametrize("change", ["operation", "versions", "absent", "failed", "old_identity"])
def test_reconciliation_must_prove_this_operation_and_versions(change: str) -> None:
    new = replace(PROOF, identity="fresh", scope="reconciliation")
    if change == "operation":
        new = replace(new, operation_id="another-operation")
    if change == "versions":
        new = replace(new, resource_versions=(ExpectedVersion(RESOURCE, "wrong"),))
    if change == "old_identity":
        new = replace(new, identity=PROOF.identity)
    status = replace(PASSED, reference=new)
    if change == "failed":
        status = replace(status, verification=StageState.FAILED)
    verified = replace(facts(), evidence=(PASSED, status), reconciliation=(new,))
    observed = replace(observation(), evidence=(PROOF,) if change == "absent" else (PROOF, new))
    before = replace(receipt(ReceiptState.AMBIGUOUS), evidence=(PROOF,))
    with pytest.raises(ValueError, match="reconciliation"):
        outcome_update(before, observed, verified, POLICY)


def test_malformed_effect_is_not_success_and_deferred_encoder_is_never_called() -> None:
    with pytest.raises(ValueError, match="EffectDisposition"):
        outcome_update(
            receipt(),
            replace(observation(), effect=cast(EffectDisposition, "applied")),
            facts(),
            POLICY,
        )

    def failed_encoder() -> None:
        raise AssertionError("Outcome policy must consume dispatcher validation facts")

    observed = replace(observation(), encode_result=failed_encoder)
    assert outcome_update(receipt(), observed, facts(), POLICY).state is ReceiptState.COMPLETE


def test_required_evidence_matches_even_when_reader_claims_wrong_pins_pass() -> None:
    wrong = replace(PROOF, resource_versions=(ExpectedVersion(RESOURCE, "wrong"),))
    observed = replace(
        observation(),
        evidence=(wrong,),
        stages=(replace(observation().stages[0], evidence=(wrong,)),),
    )
    update = outcome_update(
        receipt(), observed, replace(facts(), evidence=(replace(PASSED, reference=wrong),)), POLICY
    )
    assert update.state is ReceiptState.PARTIAL
    assert any(d.code == "evidence_mismatch" for d in update.diagnostics)


def test_rejection_preserves_correlation_without_accepted_identity_or_secret() -> None:
    unsafe = Diagnostic(KEY, "private", "secret_token", RecoveryDisposition.RETRY)
    rejected = reject_request(KEY, "request-correlation", unsafe)
    assert rejected.correlation_id == "request-correlation"
    assert not hasattr(rejected, "operation_id")
    assert rejected.diagnostic == Diagnostic(
        KEY, "invocation", "rejected", RecoveryDisposition.DO_NOT_RETRY
    )
    safe = Diagnostic(KEY, "input", "invalid", RecoveryDisposition.CORRECT_REQUEST, ("amount",))
    policy = DiagnosticPolicy(
        frozenset({("input", "invalid", RecoveryDisposition.CORRECT_REQUEST)}),
        frozenset({("amount",)}),
    )
    assert reject_request(KEY, "correlation", safe, policy).diagnostic == safe


@pytest.mark.parametrize("state", [StageState.FAILED, StageState.PENDING, StageState.PASSED])
def test_required_stage_without_evidence_preserves_failed_state(state: StageState) -> None:
    observed = replace(
        observation(EffectDisposition.NONE),
        stages=(StageResult("readback", state, "private-reason"),),
        evidence=(),
    )
    update = outcome_update(receipt(), observed, facts(), POLICY)
    stage = update.stages[0]
    assert update.state is ReceiptState.FAILED
    assert stage.state is (StageState.FAILED if state is StageState.FAILED else StageState.PENDING)
    assert stage.reason_code == (
        "evidence_missing" if state is StageState.PASSED else f"stage_{state.value}"
    )
    assert any(item.code == "evidence_missing" for item in update.diagnostics)
    assert "private-reason" not in repr(update)
