"""Framework-independent caller and versioned resource identities."""

import re
from dataclasses import dataclass

from craftreport.contracts.values import require_text, require_unique


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated scope supplied by the trusted server boundary."""

    deployment_scope: str
    subject: str
    permitted_scopes: frozenset[str]

    def __post_init__(self) -> None:
        require_text(self.deployment_scope, "deployment_scope")
        require_text(self.subject, "subject")
        object.__setattr__(self, "permitted_scopes", frozenset(self.permitted_scopes))
        for scope in self.permitted_scopes:
            require_text(scope, "permitted_scope")


@dataclass(frozen=True, slots=True)
class OperationKey:
    name: str
    contract_version: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_.]{0,47}", self.name) is None:
            raise ValueError("Invalid operation name")
        if re.fullmatch(r"[1-9][0-9]*", self.contract_version) is None:
            raise ValueError("Contract version must be a positive integer string")


@dataclass(frozen=True, slots=True)
class RetryKey:
    """Scoped by authenticated identity, never by caller-supplied tenant fields."""

    deployment_scope: str
    subject: str
    operation: OperationKey
    caller_key: str

    def __post_init__(self) -> None:
        require_text(self.deployment_scope, "deployment_scope")
        require_text(self.subject, "subject")
        require_text(self.caller_key, "caller_key")


@dataclass(frozen=True, slots=True)
class CapabilityVersion:
    identity: str
    version: str

    def __post_init__(self) -> None:
        require_text(self.identity, "capability identity")
        require_text(self.version, "capability version")


@dataclass(frozen=True, slots=True)
class CapabilityRequirement:
    identity: str
    version_range: str
    target_mode: str | None = None

    def __post_init__(self) -> None:
        require_text(self.identity, "capability identity")
        require_text(self.version_range, "capability range")
        if self.target_mode is not None:
            require_text(self.target_mode, "target_mode")


@dataclass(frozen=True, slots=True)
class ResourceRef:
    kind: str
    identity: str

    def __post_init__(self) -> None:
        require_text(self.kind, "resource kind")
        require_text(self.identity, "resource identity")


@dataclass(frozen=True, slots=True)
class ExpectedVersion:
    resource: ResourceRef
    version: str

    def __post_init__(self) -> None:
        require_text(self.version, "expected version")


def check_preconditions(versions: tuple[ExpectedVersion, ...]) -> None:
    require_unique(tuple(pin.resource for pin in versions), "resource preconditions")
