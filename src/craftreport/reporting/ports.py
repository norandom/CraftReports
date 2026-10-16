"""Immutable selections and source-authorized configured pack reads."""

import json
from dataclasses import asdict, dataclass
from typing import Literal, Protocol, get_args

from craftreport.contracts.identity import CapabilityRequirement, Principal
from craftreport.contracts.outcomes import RecoveryDisposition
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.data.requirements import BindingIssue, InputRequirements
from craftreport.data.values import Scalar, SnapshotRef
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.definitions import (
    DefinitionCode,
    DefinitionIssue,
    ParameterValue,
    ReportDefinition,
    text,
)
from craftreport.reporting.prepared import PreparedReport, ResolvedPack
from craftreport.themes.resolve import CapabilityStatus, ThemeCode, ThemeFailure, validate_support
from craftreport.themes.values import PackPin, StyleOverride

type ReportIssue = DefinitionIssue | BindingIssue | ThemeFailure
type ReportCode = (
    Literal[
        "invalid_definition",
        "invalid_parameter",
        "incomplete_binding",
        "pack_missing",
        "input_unavailable",
    ]
    | ThemeCode
)


@dataclass(frozen=True, slots=True)
class ReportFailure:
    stage: Literal["prepared", "quality_evaluated"]
    code: ReportCode
    recovery: RecoveryDisposition
    issues: tuple[ReportIssue, ...]
    total_issue_count: int
    omitted_issue_count: int

    def __post_init__(self) -> None:
        require_immutable(self)
        codes = (
            "invalid_definition",
            "invalid_parameter",
            "incomplete_binding",
            "pack_missing",
            "input_unavailable",
            *get_args(ThemeCode.__value__),
        )
        if self.stage not in ("prepared", "quality_evaluated") or self.code not in codes:
            raise ValueError("Unknown report failure")
        allowed = (
            (RecoveryDisposition.RETRY,)
            if self.code == "compatibility_unavailable"
            else (RecoveryDisposition.CORRECT_REQUEST,)
        )
        if self.code == "input_unavailable":
            allowed = (RecoveryDisposition.RETRY, RecoveryDisposition.CORRECT_REQUEST)
        if type(self.recovery) is not RecoveryDisposition or self.recovery not in allowed:
            raise ValueError("Invalid report recovery")
        if any(
            type(v) is not int or not 0 <= v <= 2147483647
            for v in (self.total_issue_count, self.omitted_issue_count)
        ):
            raise ValueError("Invalid issue count")
        if (
            type(self.issues) is not tuple
            or len(self.issues) != min(self.total_issue_count, 64)
            or self.omitted_issue_count != self.total_issue_count - len(self.issues)
        ):
            raise ValueError("Inconsistent issue count")
        for issue in self.issues:
            _check_issue(issue)

    @classmethod
    def from_issues(
        cls,
        stage: Literal["prepared", "quality_evaluated"],
        code: ReportCode,
        recovery: RecoveryDisposition,
        issues: tuple[ReportIssue, ...] = (),
    ) -> "ReportFailure":
        return cls(stage, code, recovery, issues[:64], len(issues), max(0, len(issues) - 64))


def _check_issue(issue: ReportIssue) -> None:
    if type(issue) not in (DefinitionIssue, BindingIssue, ThemeFailure):
        raise ValueError("Invalid issue type")
    if type(issue) is DefinitionIssue and issue.code not in get_args(DefinitionCode.__value__):
        raise ValueError("Invalid definition issue code")
    if type(issue.location) is not tuple or len(issue.location) > 8:
        raise ValueError("Invalid issue location")
    for part in issue.location:
        if type(part) is str:
            text(part, ("issues",), empty=True)
        elif type(part) is not int or not 0 <= part <= 2147483647:
            raise ValueError("Invalid location index")
    if len(json.dumps(asdict(issue), ensure_ascii=False, separators=(",", ":")).encode()) > 4096:
        raise ValueError("Issue exceeds bound")


@dataclass(frozen=True, slots=True)
class PackSelection:
    namespace: str
    name: str
    version: str

    def __post_init__(self) -> None:
        for value in (self.namespace, self.name, self.version):
            text(value, ("selection",))

    @property
    def identity(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass(frozen=True, slots=True)
class PackSummary:
    identity: str
    version: str
    attribution: str
    artifact_visibility_scope: str


@dataclass(frozen=True, slots=True)
class PackFailure:
    code: Literal["not_found"] = "not_found"
    location: tuple[Literal["selection"]] = ("selection",)


class PackReader(Protocol):
    def discover(self, principal: Principal) -> tuple[PackSummary, ...]: ...

    def read(
        self, selection: PackSelection, principal: Principal
    ) -> ResolvedPack | PackFailure: ...


@dataclass(frozen=True, slots=True)
class EmptyRequest:
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidateRequest:
    pack: PackSelection
    definition: ReportDefinition | None = None
    parameters: tuple[ParameterValue, ...] = ()
    overrides: tuple[StyleOverride, ...] = ()
    target_support: tuple[CapabilityStatus, ...] | None = None

    def __post_init__(self) -> None:
        require_immutable(self)
        if self.target_support is not None and validate_support(self.target_support) is not None:
            raise ValueError("Invalid support group")


@dataclass(frozen=True, slots=True, kw_only=True)
class PrepareRequest(ValidateRequest):
    snapshot: SnapshotRef
    requested_designation: Literal["draft", "validated"] = "draft"

    def __post_init__(self) -> None:
        ValidateRequest.__post_init__(self)
        text(self.snapshot.feed_id, ("snapshot", "feed_id"))
        if self.requested_designation not in ("draft", "validated"):
            raise ValueError("Invalid designation")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    requirements: InputRequirements
    resolved_parameters: tuple[tuple[str, Scalar], ...]
    definition: VersionPin
    template: VersionPin
    theme: VersionPin
    pack: PackPin
    required_capabilities: tuple[CapabilityRequirement, ...]

    def __post_init__(self) -> None:
        require_immutable(self)


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    packs: tuple[PackSummary, ...]

    def __post_init__(self) -> None:
        require_immutable(self)


@dataclass(frozen=True, slots=True)
class PreparationResult:
    prepared: PreparedReport
    quality: QualityEvaluation

    def __post_init__(self) -> None:
        require_immutable(self)
