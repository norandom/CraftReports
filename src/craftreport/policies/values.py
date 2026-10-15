"""Frozen reporting evidence values; no methodology or release evaluation."""

import json
import re
from dataclasses import asdict, dataclass, is_dataclass
from enum import StrEnum

from craftreport.contracts.identity import ExpectedVersion, ResourceRef, check_preconditions
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.values import require_enum, require_immutable, require_unique


class CheckId(StrEnum):
    DEFINITION = "definition"
    BINDINGS = "bindings"
    SEMANTIC_RESOLUTION = "semantic_resolution"
    LAYOUT_FIT = "layout_fit"
    TARGET_CONSISTENCY = "target_consistency"
    ARTIFACT_CONSISTENCY = "artifact_consistency"
    ARTIFACT_REOPEN = "artifact_reopen"
    METRIC_METHODOLOGY = "metric_methodology"
    COMPLIANCE_STATEMENT = "compliance_statement"


class QualityDimension(StrEnum):
    LAYOUT = "layout"
    TEMPLATE = "template"
    CONSISTENCY = "consistency"
    COMPLIANCE = "compliance"
    ACCURACY = "accuracy"


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    UNEVALUATED = "unevaluated"
    NOT_APPLICABLE = "not_applicable"


class CheckOrigin(StrEnum):
    CRAFTREPORT = "craftreport"
    EXTERNAL = "external"


def _text(value: str, maximum: int) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError("Expected nonempty bounded text")
    if len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > maximum:
        raise ValueError("Text exceeds serialized UTF-8 limit")


def _digest(value: str) -> None:
    if type(value) is not str or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("Expected lowercase SHA-256 hex digest")


def _size(value: object, maximum: int) -> None:
    require_immutable(value)
    if not is_dataclass(value) or isinstance(value, type):
        raise ValueError("Expected frozen contract")
    # Validate the closed value's size, without exposing a wire codec inward.
    if len(json.dumps(asdict(value), ensure_ascii=False, separators=(",", ":")).encode()) > maximum:
        raise ValueError("Contract exceeds serialized UTF-8 limit")


def _pin(value: ExpectedVersion) -> None:
    if type(value) is not ExpectedVersion or type(value.resource) is not ResourceRef:
        raise ValueError("Expected kernel resource version")
    for text in (value.resource.kind, value.resource.identity, value.version):
        _text(text, 1024)


@dataclass(frozen=True, slots=True)
class CheckScope:
    content_digest: str
    resource_versions: tuple[ExpectedVersion, ...]
    target: ExpectedVersion | None
    artifact_digest: str | None
    validation_scope_digest: str

    def __post_init__(self) -> None:
        _digest(self.content_digest)
        _digest(self.validation_scope_digest)
        if self.artifact_digest is not None:
            _digest(self.artifact_digest)
        if type(self.resource_versions) is not tuple or len(self.resource_versions) > 8:
            raise ValueError("Scope requires at most eight immutable resource pins")
        for pin in self.resource_versions:
            _pin(pin)
        check_preconditions(self.resource_versions)
        if self.target is not None:
            _pin(self.target)
        _size(self, 3072)


def _evidence(values: tuple[EvidenceRef, ...]) -> None:
    if type(values) is not tuple or len(values) > 8:
        raise ValueError("Expected at most eight immutable evidence references")
    for value in values:
        if type(value) is not EvidenceRef:
            raise ValueError("Expected kernel EvidenceRef")
        _size(value, 3072)


@dataclass(frozen=True, slots=True)
class ReleasePolicy:
    required_checks: tuple[CheckId, ...]
    scope_label: str

    def __post_init__(self) -> None:
        if type(self.required_checks) is not tuple or len(self.required_checks) > 9:
            raise ValueError("Policy requires immutable closed check membership")
        for check in self.required_checks:
            require_enum(check, CheckId)
        require_unique(self.required_checks, "required checks")
        _text(self.scope_label, 512)


@dataclass(frozen=True, slots=True)
class ExternalStatement:
    text: str
    scope: str
    issuer: str
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        _text(self.text, 32768)
        _text(self.scope, 2048)
        _text(self.issuer, 512)
        _evidence(self.evidence)
        if not self.evidence:
            raise ValueError("Supplied statement requires external evidence")
        _size(self, 32768)


def _observation(value: "CheckObservation | Finding") -> None:
    require_enum(value.check_id, CheckId)
    require_enum(value.status, CheckStatus)
    require_enum(value.origin, CheckOrigin)
    if type(value.scope) is not CheckScope:
        raise ValueError("Expected CheckScope")
    _evidence(value.evidence)
    if (
        type(value.reason_code) is not str
        or re.fullmatch("[a-z][a-z0-9_]{0,63}", value.reason_code) is None
    ):
        raise ValueError("Expected bounded reason code")
    _size(value, 36864)


@dataclass(frozen=True, slots=True)
class CheckObservation:
    check_id: CheckId
    scope: CheckScope
    status: CheckStatus
    evidence: tuple[EvidenceRef, ...]
    origin: CheckOrigin
    reason_code: str

    def __post_init__(self) -> None:
        _observation(self)


@dataclass(frozen=True, slots=True)
class Finding:
    check_id: CheckId
    dimension: QualityDimension
    status: CheckStatus
    scope: CheckScope
    evidence: tuple[EvidenceRef, ...]
    origin: CheckOrigin
    reason_code: str

    def __post_init__(self) -> None:
        require_enum(self.dimension, QualityDimension)
        _observation(self)
        dimensions = (
            QualityDimension.TEMPLATE,
            QualityDimension.TEMPLATE,
            QualityDimension.TEMPLATE,
            QualityDimension.LAYOUT,
            QualityDimension.CONSISTENCY,
            QualityDimension.CONSISTENCY,
            QualityDimension.CONSISTENCY,
            QualityDimension.ACCURACY,
            QualityDimension.COMPLIANCE,
        )
        if self.dimension != dimensions[tuple(CheckId).index(self.check_id)]:
            raise ValueError("Check has a different quality dimension")


@dataclass(frozen=True, slots=True)
class QualityEvaluation:
    findings: tuple[Finding, ...]
    draft_eligible: bool
    validated_release_eligible: bool
    blocking_checks: tuple[CheckId, ...]
    scope_label: str
    draft_designation: str
    validation_summary: str

    def __post_init__(self) -> None:
        require_immutable(self)
        if type(self.findings) is not tuple or len(self.findings) != len(CheckId):
            raise ValueError("Evaluation requires one finding per closed check")
        if any(type(finding) is not Finding for finding in self.findings):
            raise ValueError("Expected Finding")
        require_unique(tuple(finding.check_id for finding in self.findings), "finding checks")
        if type(self.blocking_checks) is not tuple or len(self.blocking_checks) > 9:
            raise ValueError("Expected bounded immutable blocking checks")
        for check in self.blocking_checks:
            require_enum(check, CheckId)
        require_unique(self.blocking_checks, "blocking checks")
        if (
            type(self.draft_eligible) is not bool
            or type(self.validated_release_eligible) is not bool
        ):
            raise ValueError("Expected boolean eligibility")
        if self.validated_release_eligible and (self.blocking_checks or not self.draft_eligible):
            raise ValueError("Validated release cannot have blockers or invalid input")
        if self.draft_designation != "DRAFT":
            raise ValueError("Draft designation must remain visible")
        _text(self.scope_label, 512)
        _text(self.validation_summary, 4096)
