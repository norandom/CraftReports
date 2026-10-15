"""Immutable selections and source-authorized configured pack reads."""

from dataclasses import dataclass
from typing import Literal, Protocol

from craftreport.contracts.identity import CapabilityRequirement, Principal
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.data.requirements import InputRequirements
from craftreport.data.values import Scalar, SnapshotRef
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.definitions import ParameterValue, ReportDefinition, text
from craftreport.reporting.prepared import PreparedReport, ResolvedPack
from craftreport.themes.resolve import CapabilityStatus, validate_support
from craftreport.themes.values import PackPin, StyleOverride


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
