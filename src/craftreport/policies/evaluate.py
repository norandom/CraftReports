"""Pure evaluation of observations from trusted preparer/app ports.

Producers authorize and read back evidence before constructing observations;
this function has no IO or public assertion-to-trust conversion.
"""

from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
    Finding,
    QualityDimension,
    QualityEvaluation,
    ReleasePolicy,
)

_PREPARATION = (CheckId.DEFINITION, CheckId.BINDINGS, CheckId.SEMANTIC_RESOLUTION)
_TARGET = (CheckId.LAYOUT_FIT, CheckId.TARGET_CONSISTENCY)
_ARTIFACT = (CheckId.ARTIFACT_CONSISTENCY, CheckId.ARTIFACT_REOPEN)
_ASSURANCE = (CheckId.METRIC_METHODOLOGY, CheckId.COMPLIANCE_STATEMENT)


def _validate_preparation_scope(scope: CheckScope) -> None:
    if type(scope) is not CheckScope:
        raise ValueError("Expected trusted preparation scope")
    pins = {pin.resource.kind: pin for pin in scope.resource_versions}
    if (
        len(scope.resource_versions) != 3
        or set(pins) != {"snapshot", "report_pack_source", "report_pack_artifact_scope"}
        or scope.target is not None
        or scope.artifact_digest is not None
    ):
        raise ValueError("Invalid preparation scope source set or target/artifact")
    if (
        pins["report_pack_source"].resource.identity
        != pins["report_pack_artifact_scope"].resource.identity
    ):
        raise ValueError("Invalid preparation scope pack identity")


def _source_unchanged(current: CheckScope, original: CheckScope) -> bool:
    return (
        current.content_digest == original.content_digest
        and current.validation_scope_digest == original.validation_scope_digest
        and set(original.resource_versions).issubset(current.resource_versions)
    )


def _scope_matches(current: CheckScope, expected: CheckScope, check: CheckObservation) -> bool:
    return check.scope == expected and (
        check.check_id not in _PREPARATION or _source_unchanged(current, expected)
    )


def _dimension(check: CheckId) -> QualityDimension:
    if check in _PREPARATION:
        return QualityDimension.TEMPLATE
    return {
        CheckId.LAYOUT_FIT: QualityDimension.LAYOUT,
        CheckId.TARGET_CONSISTENCY: QualityDimension.CONSISTENCY,
        CheckId.ARTIFACT_CONSISTENCY: QualityDimension.CONSISTENCY,
        CheckId.ARTIFACT_REOPEN: QualityDimension.CONSISTENCY,
        CheckId.METRIC_METHODOLOGY: QualityDimension.ACCURACY,
        CheckId.COMPLIANCE_STATEMENT: QualityDimension.COMPLIANCE,
    }[check]


def _invalid_reason(
    scope: CheckScope, check: CheckObservation, preparation_scope: CheckScope
) -> str | None:
    expected = preparation_scope if check.check_id in _PREPARATION else scope
    if not _scope_matches(scope, expected, check):
        return "scope_changed"
    if check.origin is CheckOrigin.EXTERNAL:
        return "externally_supplied"
    if check.check_id in _ASSURANCE:
        return "no_internal_evaluator"
    if check.check_id in (*_TARGET, *_ARTIFACT) and scope.target is None:
        return "target_unidentified"
    if check.check_id in _ARTIFACT and scope.artifact_digest is None:
        return "artifact_unidentified"
    if not check.evidence or any(
        not ref.content_digest or ref.resource_versions != expected.resource_versions
        for ref in check.evidence
    ):
        return "evidence_unavailable_or_mismatched"
    return None


def _finding(
    scope: CheckScope,
    check_id: CheckId,
    check: CheckObservation | None,
    preparation_scope: CheckScope,
) -> Finding:
    if check is None:
        status = (
            CheckStatus.NOT_APPLICABLE
            if check_id is CheckId.COMPLIANCE_STATEMENT
            else CheckStatus.UNEVALUATED
        )
        return Finding(
            check_id,
            _dimension(check_id),
            status,
            scope,
            (),
            CheckOrigin.CRAFTREPORT,
            "no_statement" if check_id is CheckId.COMPLIANCE_STATEMENT else "not_executed",
        )
    invalid = _invalid_reason(scope, check, preparation_scope)
    return Finding(
        check_id,
        _dimension(check_id),
        CheckStatus.UNEVALUATED if invalid else check.status,
        check.scope if check_id in _PREPARATION else scope,
        check.evidence,
        check.origin,
        invalid or check.reason_code,
    )


def _internal_pass(finding: Finding) -> bool:
    return finding.status is CheckStatus.PASSED and finding.origin is CheckOrigin.CRAFTREPORT


def evaluate(
    scope: CheckScope,
    policy: ReleasePolicy,
    checks: tuple[CheckObservation, ...],
    *,
    preparation_scope: CheckScope,
) -> QualityEvaluation:
    if type(scope) is not CheckScope or type(policy) is not ReleasePolicy:
        raise ValueError("Expected closed scope and release policy")
    _validate_preparation_scope(preparation_scope)
    if type(checks) is not tuple:
        raise ValueError("Expected immutable observations")
    observed: dict[CheckId, CheckObservation] = {}
    for check in checks:
        if type(check) is not CheckObservation:
            raise ValueError("Expected CheckObservation from a trusted producer")
        if check.check_id in observed and observed[check.check_id] != check:
            raise ValueError(f"Contradictory observations: {check.check_id}")
        observed[check.check_id] = check
    findings = tuple(
        _finding(scope, check, observed.get(check), preparation_scope) for check in CheckId
    )
    by_check = {finding.check_id: finding for finding in findings}
    blockers = tuple(
        check for check in policy.required_checks if not _internal_pass(by_check[check])
    )
    draft = all(_internal_pass(by_check[check]) for check in _PREPARATION)
    summary = "; ".join(
        f"{finding.check_id}: {finding.status} ({finding.origin}; {finding.reason_code})"
        for finding in findings
    )
    return QualityEvaluation(
        findings, draft, draft and not blockers, blockers, policy.scope_label, "DRAFT", summary
    )
