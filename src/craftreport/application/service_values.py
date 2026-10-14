"""Provider decisions and resource observations, without concrete providers."""

from dataclasses import dataclass, field
from typing import Literal

from craftreport.contracts import (
    CapabilityRequirement,
    CapabilityVersion,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    ResourceRef,
)
from craftreport.contracts.identity import check_preconditions
from craftreport.contracts.values import freeze_object, require_enum, require_text


@dataclass(frozen=True, slots=True)
class Missing:
    """Authoritative absence in the provider's declared retention scope."""

    kind: Literal["missing"] = field(default="missing", init=False)


@dataclass(frozen=True, slots=True)
class ServiceUnavailable:
    """No reliable decision; includes lost acknowledgement/unknown retention.

    Admission unavailability requires lookup/reconciliation before any effect,
    even if an initial accepted record might already exist. Never treat as missing.
    """

    service: str
    kind: Literal["unavailable"] = field(default="unavailable", init=False)

    def __post_init__(self) -> None:
        require_text(self.service, "service")


@dataclass(frozen=True, slots=True)
class OperationAccess:
    """Empty resources is the coarse check before private request validation."""

    operation: OperationKey
    resources: tuple[ResourceRef, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "resources", tuple(self.resources))


@dataclass(frozen=True, slots=True)
class CatalogAccess:
    """Permission to discover; each returned operation needs its own check."""


@dataclass(frozen=True, slots=True)
class ReceiptAccess:
    operation_id: str

    def __post_init__(self) -> None:
        require_text(self.operation_id, "operation_id")


type AccessAction = OperationAccess | CatalogAccess | ReceiptAccess


@dataclass(frozen=True, slots=True)
class AccessAllowed:
    kind: Literal["allowed"] = field(default="allowed", init=False)


@dataclass(frozen=True, slots=True)
class AccessDenied:
    """No protected resource or other caller's receipt is included in denial."""

    kind: Literal["denied"] = field(default="denied", init=False)


type AccessDecision = AccessAllowed | AccessDenied | ServiceUnavailable


@dataclass(frozen=True, slots=True)
class CapabilitiesSupported:
    versions: tuple[CapabilityVersion, ...]
    kind: Literal["supported"] = field(default="supported", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "versions", tuple(self.versions))


@dataclass(frozen=True, slots=True)
class CapabilitiesUnsupported:
    requirements: tuple[CapabilityRequirement, ...]
    kind: Literal["unsupported"] = field(default="unsupported", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", tuple(self.requirements))
        if not self.requirements:
            raise ValueError("Unsupported decision must identify a requirement")


type CapabilityDecision = CapabilitiesSupported | CapabilitiesUnsupported | ServiceUnavailable
type Preconditions = tuple[ExpectedVersion, ...]


@dataclass(frozen=True, slots=True)
class VersionConflict:
    expected: Preconditions
    authoritative: Preconditions
    kind: Literal["version_conflict"] = field(default="version_conflict", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", tuple(self.expected))
        object.__setattr__(self, "authoritative", tuple(self.authoritative))
        check_preconditions(self.expected)
        check_preconditions(self.authoritative)


@dataclass(frozen=True, slots=True)
class GuardCurrent:
    kind: Literal["current"] = field(default="current", init=False)


@dataclass(frozen=True, slots=True)
class GuardLost:
    """Stop dependent work; an unstoppable in-flight effect remains ambiguous."""

    kind: Literal["lost"] = field(default="lost", init=False)


type GuardCheck = GuardCurrent | GuardLost | VersionConflict | ServiceUnavailable


@dataclass(frozen=True, slots=True)
class ResourceSnapshot:
    """Inspection-only snapshot, with owned immutable decoded content."""

    version: ExpectedVersion
    content: JsonObject

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", freeze_object(self.content))


@dataclass(frozen=True, slots=True)
class ResourceEffect:
    """Effect observation, never a canonical receipt or completion decision."""

    effect: EffectDisposition
    versions: tuple[ExpectedVersion, ...]
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        require_enum(self.effect, EffectDisposition)
        object.__setattr__(self, "versions", tuple(self.versions))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        check_preconditions(self.versions)


type ResourceEffectResult = ResourceEffect | VersionConflict | GuardLost | ServiceUnavailable
