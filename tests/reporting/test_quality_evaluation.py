"""Policy matrix for scoped assurance and draft/release eligibility."""

from dataclasses import replace

import pytest

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.policies.evaluate import evaluate
from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
    QualityDimension,
    ReleasePolicy,
)

PREPARATION = tuple(CheckId)[:3]
BASELINE = tuple(CheckId)[:5]


def _source_scope() -> CheckScope:
    return CheckScope(
        "a" * 64,
        (
            ExpectedVersion(ResourceRef("snapshot", "feed:1"), "e" * 64),
            ExpectedVersion(ResourceRef("report_pack_source", "public/report@1"), "source-v1"),
            ExpectedVersion(
                ResourceRef("report_pack_artifact_scope", "public/report@1"), "artifact-v1"
            ),
        ),
        None,
        None,
        "c" * 64,
    )


@pytest.fixture
def scope() -> CheckScope:
    source = _source_scope()
    target = ExpectedVersion(ResourceRef("document", "doc:one"), "1")
    return replace(
        source,
        resource_versions=source.resource_versions
        + (
            target,
            ExpectedVersion(ResourceRef("run", "run:one"), "1"),
            ExpectedVersion(ResourceRef("artifact", "artifact:one"), "b" * 64),
        ),
        target=target,
        artifact_digest="b" * 64,
    )


def observation(scope: CheckScope, check: CheckId) -> CheckObservation:
    if check in PREPARATION:
        scope = _source_scope()
    evidence = EvidenceRef(
        f"fact-{check}",
        "report-check",
        "operation-1",
        OperationKey("reports.prepare", "1"),
        scope.resource_versions,
        "d" * 64,
    )
    return CheckObservation(
        check, scope, CheckStatus.PASSED, (evidence,), CheckOrigin.CRAFTREPORT, "observed"
    )


@pytest.fixture
def prepared(scope: CheckScope) -> tuple[CheckObservation, ...]:
    return tuple(observation(scope, check) for check in PREPARATION)


def test_ingestion_only_is_draft_with_all_dimensions_and_visible_blockers(
    scope: CheckScope, prepared: tuple[CheckObservation, ...]
) -> None:
    result = evaluate(
        scope, ReleasePolicy(BASELINE, "Report only"), prepared, preparation_scope=_source_scope()
    )
    assert result.draft_eligible and (not result.validated_release_eligible)
    assert result.draft_designation == "DRAFT"
    assert result.blocking_checks == (CheckId.LAYOUT_FIT, CheckId.TARGET_CONSISTENCY)
    assert {finding.dimension for finding in result.findings} == set(QualityDimension)
    assert len(result.findings) == 9
    findings = {finding.check_id: finding for finding in result.findings}
    assert findings[CheckId.METRIC_METHODOLOGY].status is CheckStatus.UNEVALUATED
    assert findings[CheckId.COMPLIANCE_STATEMENT].status is CheckStatus.NOT_APPLICABLE
    assert "layout_fit: unevaluated" in result.validation_summary
    assert "target_consistency: unevaluated" in result.validation_summary


def test_all_required_internal_passes_release_only_named_scope(scope: CheckScope) -> None:
    checks = tuple(observation(scope, check) for check in BASELINE)
    result = evaluate(
        scope,
        ReleasePolicy(BASELINE, "Report presentation only"),
        checks,
        preparation_scope=_source_scope(),
    )
    assert result.validated_release_eligible and result.draft_eligible
    assert result.scope_label == "Report presentation only"
    assert result.blocking_checks == ()
    assert "metric_methodology: unevaluated" in result.validation_summary
    assert result == evaluate(
        scope,
        ReleasePolicy(BASELINE, result.scope_label),
        checks[::-1],
        preparation_scope=_source_scope(),
    )


@pytest.mark.parametrize("status", list(CheckStatus))
def test_required_layout_status_matrix(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], status: CheckStatus
) -> None:
    check = replace(observation(scope, CheckId.LAYOUT_FIT), status=status)
    result = evaluate(
        scope,
        ReleasePolicy((check.check_id,), "Layout"),
        (*prepared, check),
        preparation_scope=_source_scope(),
    )
    assert result.draft_eligible
    assert result.validated_release_eligible is (status is CheckStatus.PASSED)
    assert f"layout_fit: {status}" in result.validation_summary


@pytest.mark.parametrize("check_id", PREPARATION)
@pytest.mark.parametrize("status", [CheckStatus.FAILED, CheckStatus.UNEVALUATED])
def test_invalid_or_unverified_preparation_cannot_be_draft(
    scope: CheckScope,
    prepared: tuple[CheckObservation, ...],
    check_id: CheckId,
    status: CheckStatus,
) -> None:
    checks = tuple(
        replace(check, status=status) if check.check_id == check_id else check for check in prepared
    )
    result = evaluate(
        scope, ReleasePolicy((), "No target checks"), checks, preparation_scope=_source_scope()
    )
    assert not result.draft_eligible and (not result.validated_release_eligible)


@pytest.mark.parametrize(
    "field",
    ["content_digest", "validation_scope_digest", "target", "artifact_digest", "resource_versions"],
)
def test_changed_scope_invalidates_prior_observations(scope: CheckScope, field: str) -> None:
    changes: dict[str, object] = {
        "content_digest": "e" * 64,
        "validation_scope_digest": "f" * 64,
        "target": ExpectedVersion(ResourceRef("document", "other"), "2"),
        "artifact_digest": "0" * 64,
        "resource_versions": (ExpectedVersion(ResourceRef("snapshot", "feed:one"), "2"),),
    }
    changed = replace(scope, **{field: changes[field]})
    checks = tuple(observation(scope, check) for check in BASELINE)
    result = evaluate(
        changed,
        ReleasePolicy(BASELINE, "Changed selection"),
        checks,
        preparation_scope=_source_scope(),
    )
    assert not result.validated_release_eligible
    expected = (
        CheckStatus.PASSED if field in ("target", "artifact_digest") else CheckStatus.UNEVALUATED
    )
    assert all(item.status is expected for item in result.findings[:3])
    assert all(item.scope == _source_scope() for item in result.findings[:3])
    assert all(item.status is CheckStatus.UNEVALUATED for item in result.findings[3:5])


@pytest.mark.parametrize("check_id", list(CheckId))
def test_external_claims_never_satisfy_internal_checks(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], check_id: CheckId
) -> None:
    external = replace(observation(scope, check_id), origin=CheckOrigin.EXTERNAL)
    checks = tuple(check for check in prepared if check.check_id != check_id) + (external,)
    result = evaluate(
        scope,
        ReleasePolicy((check_id,), "Internal check required"),
        checks,
        preparation_scope=_source_scope(),
    )
    finding = next(item for item in result.findings if item.check_id == check_id)
    assert finding.origin is CheckOrigin.EXTERNAL
    assert finding.evidence == external.evidence
    assert finding.status is CheckStatus.UNEVALUATED
    assert not result.validated_release_eligible


@pytest.mark.parametrize("check_id", [CheckId.METRIC_METHODOLOGY, CheckId.COMPLIANCE_STATEMENT])
def test_no_builtin_methods_or_standards_can_be_claimed(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], check_id: CheckId
) -> None:
    result = evaluate(
        scope,
        ReleasePolicy((check_id,), "Assurance"),
        (*prepared, observation(scope, check_id)),
        preparation_scope=_source_scope(),
    )
    finding = next(item for item in result.findings if item.check_id == check_id)
    assert finding.status is CheckStatus.UNEVALUATED
    assert not result.validated_release_eligible


@pytest.mark.parametrize("problem", ["empty", "no_digest", "wrong_pins"])
def test_unusable_internal_evidence_never_passes(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], problem: str
) -> None:
    check = observation(scope, CheckId.LAYOUT_FIT)
    evidence = {
        "empty": (),
        "no_digest": (replace(check.evidence[0], content_digest=None),),
        "wrong_pins": (replace(check.evidence[0], resource_versions=()),),
    }[problem]
    check = replace(check, evidence=evidence)
    result = evaluate(
        scope,
        ReleasePolicy((check.check_id,), "Layout"),
        (*prepared, check),
        preparation_scope=_source_scope(),
    )
    assert result.findings[3].status is CheckStatus.UNEVALUATED
    assert not result.validated_release_eligible


@pytest.mark.parametrize(
    "check_id",
    [
        CheckId.LAYOUT_FIT,
        CheckId.TARGET_CONSISTENCY,
        CheckId.ARTIFACT_CONSISTENCY,
        CheckId.ARTIFACT_REOPEN,
    ],
)
def test_app_observation_requires_target_and_artifact_identity(
    scope: CheckScope, check_id: CheckId
) -> None:
    scope = replace(scope, target=None, artifact_digest=None)
    checks = tuple(observation(scope, check) for check in (*PREPARATION, check_id))
    result = evaluate(
        scope, ReleasePolicy((check_id,), "App scope"), checks, preparation_scope=_source_scope()
    )
    assert not result.validated_release_eligible
    assert (
        next(item for item in result.findings if item.check_id == check_id).status
        is CheckStatus.UNEVALUATED
    )


def test_artifact_policy_requires_matching_consistency_and_reopen(scope: CheckScope) -> None:
    required = tuple(CheckId)[:7]
    checks = tuple(observation(scope, check) for check in required)
    policy = ReleasePolicy(required, "Observed artifact only")
    assert evaluate(
        scope, policy, checks, preparation_scope=_source_scope()
    ).validated_release_eligible
    assert not evaluate(
        scope, policy, checks[:-1], preparation_scope=_source_scope()
    ).validated_release_eligible


@pytest.mark.parametrize("check_id", [CheckId.ARTIFACT_CONSISTENCY, CheckId.ARTIFACT_REOPEN])
def test_artifact_identity_is_required_even_with_target(
    scope: CheckScope, check_id: CheckId
) -> None:
    scope = replace(scope, artifact_digest=None)
    checks = tuple(observation(scope, check) for check in (*PREPARATION, check_id))
    result = evaluate(
        scope, ReleasePolicy((check_id,), "Artifact"), checks, preparation_scope=_source_scope()
    )
    finding = next(item for item in result.findings if item.check_id == check_id)
    assert finding.status is CheckStatus.UNEVALUATED
    assert finding.reason_code == "artifact_unidentified"
    assert result.draft_eligible and (not result.validated_release_eligible)


def test_required_absent_compliance_still_blocks_release(
    scope: CheckScope, prepared: tuple[CheckObservation, ...]
) -> None:
    result = evaluate(
        scope,
        ReleasePolicy((CheckId.COMPLIANCE_STATEMENT,), "Compliance"),
        prepared,
        preparation_scope=_source_scope(),
    )
    assert result.blocking_checks == (CheckId.COMPLIANCE_STATEMENT,)
    assert result.draft_eligible and (not result.validated_release_eligible)


def test_duplicate_identical_observations_aggregate_but_contradictions_reject(
    scope: CheckScope, prepared: tuple[CheckObservation, ...]
) -> None:
    policy = ReleasePolicy(PREPARATION, "Prepared report")
    assert evaluate(scope, policy, prepared * 3, preparation_scope=_source_scope()) == evaluate(
        scope, policy, prepared, preparation_scope=_source_scope()
    )
    conflicting = replace(prepared[0], status=CheckStatus.FAILED)
    with pytest.raises(ValueError, match="Contradictory"):
        evaluate(scope, policy, (*prepared, conflicting), preparation_scope=_source_scope())


def test_absent_preparation_does_not_create_valid_input(scope: CheckScope) -> None:
    result = evaluate(
        scope, ReleasePolicy(BASELINE, "Report"), (), preparation_scope=_source_scope()
    )
    assert not result.draft_eligible and (not result.validated_release_eligible)


def test_original_preparation_scope_reused_in_extended_current_context(scope: CheckScope) -> None:
    source = _source_scope()
    policy = ReleasePolicy(tuple(CheckId)[:7], "Same retained policy")
    original = tuple(observation(source, check) for check in PREPARATION)
    initial = evaluate(source, policy, original, preparation_scope=source)
    document_scope = replace(
        scope, resource_versions=scope.resource_versions[:4], artifact_digest=None
    )
    document = evaluate(
        document_scope,
        policy,
        original
        + tuple(
            observation(document_scope, check)
            for check in (CheckId.LAYOUT_FIT, CheckId.TARGET_CONSISTENCY)
        ),
        preparation_scope=source,
    )
    current = evaluate(
        scope,
        policy,
        original + tuple(observation(scope, check) for check in tuple(CheckId)[3:7]),
        preparation_scope=source,
    )
    assert initial.draft_eligible and not initial.validated_release_eligible
    assert document.draft_eligible and not document.validated_release_eligible
    assert document.findings[:3] == initial.findings[:3]
    assert current.validated_release_eligible
    assert current.findings[:3] == initial.findings[:3]
    assert all(item.scope == scope for item in current.findings[3:7])
    reordered = replace(scope, resource_versions=scope.resource_versions[::-1])
    assert evaluate(reordered, policy, original, preparation_scope=source).draft_eligible


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("change", ["removed", "identity", "version"])
def test_every_original_dependency_must_remain_in_current(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], index: int, change: str
) -> None:
    pins = list(scope.resource_versions)
    if change == "removed":
        pins.pop(index)
    elif change == "identity":
        pins[index] = replace(pins[index], resource=replace(pins[index].resource, identity="other"))
    else:
        pins[index] = replace(pins[index], version="changed")
    current = replace(scope, resource_versions=tuple(pins))
    result = evaluate(
        current, ReleasePolicy(PREPARATION, "Source"), prepared, preparation_scope=_source_scope()
    )
    assert not result.draft_eligible
    assert all(item.status is CheckStatus.UNEVALUATED for item in result.findings[:3])
    assert all(item.scope == _source_scope() for item in result.findings[:3])


@pytest.mark.parametrize(
    "problem",
    [
        "empty",
        "one",
        "partial",
        "extra",
        "wrong_kind",
        "duplicate_kind",
        "pack_mismatch",
        "target",
        "artifact",
    ],
)
def test_malformed_required_preparation_scope_rejects_even_when_observations_agree(
    problem: str,
) -> None:
    source = _source_scope()
    cases: dict[str, dict[str, object]] = {
        "empty": {"resource_versions": ()},
        "one": {"resource_versions": source.resource_versions[:1]},
        "partial": {"resource_versions": source.resource_versions[:2]},
        "extra": {
            "resource_versions": source.resource_versions
            + (ExpectedVersion(ResourceRef("document", "extra"), "1"),)
        },
        "wrong_kind": {
            "resource_versions": (
                replace(source.resource_versions[0], resource=ResourceRef("other", "feed:1")),
            )
            + source.resource_versions[1:]
        },
        "duplicate_kind": {
            "resource_versions": (
                replace(
                    source.resource_versions[0], resource=ResourceRef("report_pack_source", "other")
                ),
            )
            + source.resource_versions[1:]
        },
        "pack_mismatch": {
            "resource_versions": source.resource_versions[:2]
            + (
                replace(
                    source.resource_versions[2],
                    resource=ResourceRef("report_pack_artifact_scope", "other"),
                ),
            )
        },
        "target": {"target": ExpectedVersion(ResourceRef("document", "extra"), "1")},
        "artifact": {"artifact_digest": "f" * 64},
    }
    malformed = replace(source, **cases[problem])
    checks = tuple(
        replace(
            observation(source, check),
            scope=malformed,
            evidence=(
                replace(
                    observation(source, check).evidence[0],
                    resource_versions=malformed.resource_versions,
                ),
            ),
        )
        for check in PREPARATION
    )
    with pytest.raises(ValueError, match="preparation scope"):
        evaluate(
            malformed, ReleasePolicy(PREPARATION, "Source"), checks, preparation_scope=malformed
        )


@pytest.mark.parametrize(
    "problem",
    [
        "partial_scope",
        "reordered_scope",
        "extra_scope",
        "partial_ref",
        "reordered_ref",
        "current_ref",
        "no_digest",
    ],
)
def test_source_observation_and_ref_require_exact_original_tuple(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], problem: str
) -> None:
    source = _source_scope()
    check = prepared[0]
    source_changes = {
        "partial_scope": source.resource_versions[:2],
        "reordered_scope": source.resource_versions[::-1],
        "extra_scope": scope.resource_versions,
    }
    if problem in source_changes:
        check = replace(check, scope=replace(source, resource_versions=source_changes[problem]))
    else:
        refs = {
            "partial_ref": source.resource_versions[:2],
            "reordered_ref": source.resource_versions[::-1],
            "current_ref": scope.resource_versions,
        }
        ref = (
            replace(check.evidence[0], content_digest=None)
            if problem == "no_digest"
            else replace(check.evidence[0], resource_versions=refs[problem])
        )
        check = replace(check, evidence=(ref,))
    result = evaluate(
        scope,
        ReleasePolicy(PREPARATION, "Source"),
        (check,) + prepared[1:],
        preparation_scope=source,
    )
    assert not result.draft_eligible
    assert result.findings[0].status is CheckStatus.UNEVALUATED
    assert result.findings[0].scope == check.scope
    assert result.findings[0].evidence == check.evidence


@pytest.mark.parametrize("change", ["document", "run", "artifact", "additional"])
def test_old_app_observations_require_exact_current_resource_tuple(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], change: str
) -> None:
    pins = list(scope.resource_versions)
    if change == "additional":
        pins.append(ExpectedVersion(ResourceRef("app", "additional"), "1"))
    else:
        index = {"document": 3, "run": 4, "artifact": 5}[change]
        pins[index] = replace(pins[index], version="changed")
    current = replace(scope, resource_versions=tuple(pins))
    checks = prepared + tuple(observation(scope, check) for check in tuple(CheckId)[3:7])
    result = evaluate(
        current, ReleasePolicy(tuple(CheckId)[:7], "App"), checks, preparation_scope=_source_scope()
    )
    assert result.draft_eligible and not result.validated_release_eligible
    assert all(item.status is CheckStatus.UNEVALUATED for item in result.findings[3:7])


@pytest.mark.parametrize("problem", ["source_only", "final_artifact"])
def test_app_evidence_cannot_reuse_source_or_provisional_artifact_scope(
    scope: CheckScope, prepared: tuple[CheckObservation, ...], problem: str
) -> None:
    observed_scope = (
        _source_scope() if problem == "source_only" else replace(scope, artifact_digest="f" * 64)
    )
    checks = prepared + tuple(observation(observed_scope, check) for check in tuple(CheckId)[3:7])
    result = evaluate(
        scope, ReleasePolicy(tuple(CheckId)[:7], "App"), checks, preparation_scope=_source_scope()
    )
    assert result.draft_eligible and not result.validated_release_eligible
    assert all(item.status is CheckStatus.UNEVALUATED for item in result.findings[3:7])
