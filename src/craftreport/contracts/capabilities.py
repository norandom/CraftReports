"""Capability discovery declarations and operator-supplied verification metadata.

Compatibility parsing and evidence identity matching belong to activation; this
module retains plain version strings and never loads a provider or package.
"""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Final

from craftreport.contracts.identity import CapabilityRequirement, CapabilityVersion
from craftreport.contracts.operations import OperationDescriptor
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.values import JsonObject, freeze_object, require_enum, require_text

CORE_CONTRACT_VERSION: Final = "1.0.0"


class VerificationState(StrEnum):
    PENDING = "pending"
    FAILED = "failed"
    PASSED = "passed"


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    identity: str
    package: str
    version: str
    core_contract_range: str
    provided: tuple[CapabilityVersion, ...]
    required: tuple[CapabilityRequirement, ...]
    settings_schema: JsonObject
    operations: tuple[OperationDescriptor, ...]
    implementation_digest: str

    def __post_init__(self) -> None:
        for value in (
            self.identity,
            self.package,
            self.version,
            self.core_contract_range,
            self.implementation_digest,
        ):
            require_text(value, "capability manifest identity")
        object.__setattr__(self, "provided", tuple(self.provided))
        object.__setattr__(self, "required", tuple(self.required))
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "settings_schema", freeze_object(self.settings_schema))


@dataclass(frozen=True, slots=True)
class VerificationRecord:
    package: str
    package_version: str
    implementation_digest: str
    core_contract_version: str
    fixture_suite: str
    dependency_versions: tuple[CapabilityVersion, ...]
    state: VerificationState
    scope: str
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        for value in (
            self.package,
            self.package_version,
            self.implementation_digest,
            self.core_contract_version,
            self.fixture_suite,
            self.scope,
        ):
            require_text(value, "verification identity")
        require_enum(self.state, VerificationState)
        object.__setattr__(self, "dependency_versions", tuple(self.dependency_versions))
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True, slots=True)
class CapabilityView:
    manifest: CapabilityManifest
    verification: VerificationState = VerificationState.PENDING
    record: VerificationRecord | None = None

    def __post_init__(self) -> None:
        require_enum(self.verification, VerificationState)
        if self.verification is not VerificationState.PENDING:
            if self.record is None or self.record.state is not self.verification:
                raise ValueError("Resolved verification requires a matching recorded outcome")


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    capacity: int = 16
    response_seconds: float = 5.0
    shutdown_seconds: float = 10.0

    def __post_init__(self) -> None:
        if type(self.capacity) is not int or self.capacity < 1:
            raise ValueError("Execution capacity must be a positive integer")
        for value in (self.response_seconds, self.shutdown_seconds):
            if not isfinite(value) or value <= 0:
                raise ValueError("Execution timings must be finite and positive")


@dataclass(frozen=True, slots=True)
class Catalog:
    operations: tuple[OperationDescriptor, ...]
    capabilities: tuple[CapabilityView, ...]
    deployment_epoch: str
    retention_profile: str
    core_contract_version: str = CORE_CONTRACT_VERSION
    execution_limits: ExecutionLimits | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", tuple(self.operations))
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        for value in (self.deployment_epoch, self.retention_profile, self.core_contract_version):
            require_text(value, "catalog identity")
