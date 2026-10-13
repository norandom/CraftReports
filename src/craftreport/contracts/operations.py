"""Operation declarations and invocation values, without dispatch behavior."""

from dataclasses import dataclass
from enum import StrEnum

from craftreport.contracts.identity import (
    CapabilityRequirement,
    CapabilityVersion,
    ExpectedVersion,
    OperationKey,
    ResourceRef,
    RetryKey,
    check_preconditions,
)
from craftreport.contracts.values import (
    JsonObject,
    freeze_object,
    require_enum,
    require_positive,
    require_text,
    require_unique,
)


class OperationKind(StrEnum):
    COMMAND = "command"
    QUERY = "query"


@dataclass(frozen=True, slots=True)
class OperationLimits:
    max_input_bytes: int = 1_048_576
    max_nesting_depth: int = 32
    max_output_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        require_positive(self.max_input_bytes, "max_input_bytes")
        require_positive(self.max_nesting_depth, "max_nesting_depth")
        require_positive(self.max_output_bytes, "max_output_bytes")


@dataclass(frozen=True, slots=True)
class EvidencePolicy:
    """Named completion stages whose evidence must pass outcome validation."""

    required_stages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "required_stages", tuple(self.required_stages))
        require_unique(self.required_stages, "evidence stages")
        for stage in self.required_stages:
            require_text(stage, "evidence stage")


@dataclass(frozen=True, slots=True)
class OperationDescriptor:
    key: OperationKey
    kind: OperationKind
    input_schema: JsonObject
    result_schema: JsonObject
    starts_business_work: bool
    changes_business_state: bool
    resources: tuple[str, ...]
    required_capabilities: tuple[CapabilityRequirement, ...]
    required_services: tuple[str, ...]
    limits: OperationLimits
    completion_evidence: EvidencePolicy

    def __post_init__(self) -> None:
        require_enum(self.kind, OperationKind)
        if self.kind is OperationKind.QUERY and (
            self.starts_business_work or self.changes_business_state
        ):
            raise ValueError("Business work and state changes require a command")
        object.__setattr__(self, "input_schema", freeze_object(self.input_schema))
        object.__setattr__(self, "result_schema", freeze_object(self.result_schema))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))
        object.__setattr__(self, "required_services", tuple(self.required_services))
        require_unique(self.resources, "resource kinds")
        require_unique(self.required_services, "required services")
        for name in (*self.resources, *self.required_services):
            require_text(name, "requirement name")


@dataclass(frozen=True, slots=True)
class InvocationEnvelope:
    """Decoded invocation metadata; authority is deliberately absent.

    The codec rejects unknown wire fields. The dispatcher checks retry requirements
    against the registered command/query kind.
    """

    operation: OperationKey
    payload: JsonObject
    correlation_id: str
    retry_key: str | None = None
    expected_versions: tuple[ExpectedVersion, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.correlation_id, "correlation_id")
        if self.retry_key is not None:
            require_text(self.retry_key, "retry_key")
        object.__setattr__(self, "payload", freeze_object(self.payload))
        object.__setattr__(self, "expected_versions", tuple(self.expected_versions))
        check_preconditions(self.expected_versions)


@dataclass(frozen=True, slots=True)
class CommandIntent:
    """Prepared admission metadata; journal/guard ports own its enforcement."""

    retry_key: RetryKey
    fingerprint: str
    normalization_policy: str
    correlation_id: str
    capability_versions: tuple[CapabilityVersion, ...]
    resources: tuple[ResourceRef, ...]
    expected_versions: tuple[ExpectedVersion, ...]

    def __post_init__(self) -> None:
        require_text(self.fingerprint, "fingerprint")
        require_text(self.normalization_policy, "normalization_policy")
        require_text(self.correlation_id, "correlation_id")
        object.__setattr__(self, "capability_versions", tuple(self.capability_versions))
        object.__setattr__(self, "resources", tuple(self.resources))
        object.__setattr__(self, "expected_versions", tuple(self.expected_versions))
        require_unique(self.resources, "command resources")
        check_preconditions(self.expected_versions)
        if any(pin.resource not in self.resources for pin in self.expected_versions):
            raise ValueError("Preconditions must identify declared command resources")
