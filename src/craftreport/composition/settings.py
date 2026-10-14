"""Typed deployment selections close over their own services and settings codec."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass

from craftreport.application import ports
from craftreport.application.capabilities import CapabilityFactory, CapabilityInstance
from craftreport.application.dispatch_ports import HandoffStore, ResultStore, ServiceHealth
from craftreport.application.registry import Codec
from craftreport.application.verification import VerificationIdentity
from craftreport.contracts import CapabilityManifest, JsonObject
from craftreport.contracts.capabilities import ExecutionLimits, VerificationRecord
from craftreport.contracts.values import freeze_object, require_positive, require_text
from craftreport.interfaces.principal import PrincipalBoundary


@dataclass(frozen=True, slots=True)
class PreparedCapability:
    manifest: CapabilityManifest
    open: Callable[[], AbstractAsyncContextManager[CapabilityInstance]]


@dataclass(frozen=True, slots=True)
class ConfiguredCapability:
    distribution: str
    entry_point: str
    prepare: Callable[[object], PreparedCapability]


def configure[Services, Settings](
    distribution: str,
    entry_point: str,
    adapt: Callable[[object], CapabilityFactory[Services, Settings]],
    services: Services,
    codec: Codec[Settings],
    settings: JsonObject,
) -> ConfiguredCapability:
    """Adapt trusted entry-point code explicitly; retain all generic types locally.

    The adapter receives the loaded callable and checks its author contract. The
    codec must strictly validate input, as PydanticCodec.for_input does. No service
    lookup or untyped global container is passed to the capability.
    """
    values = freeze_object(settings)

    def prepare(loaded: object) -> PreparedCapability:
        factory = adapt(loaded)
        manifest = factory.describe()
        if manifest.settings_schema != freeze_object(codec.schema()):
            raise ValueError("Settings codec does not match manifest schema")
        validated = codec.decode(values)
        return PreparedCapability(manifest, lambda: factory.open(services, validated))

    return ConfiguredCapability(distribution, entry_point, prepare)


@dataclass(frozen=True, slots=True)
class GuaranteeProviders:
    """Explicit deployment providers; no synthetic or permissive defaults."""

    journal: ports.OperationJournal
    guard: ports.ExecutionGuard
    evidence: ports.EvidenceReader
    capabilities: ports.CapabilityResolver
    resources: ports.ResourceReader
    effects: ports.ResourceEffects
    results: ResultStore
    handoffs: HandoffStore
    health: ServiceHealth


@dataclass(frozen=True, slots=True)
class VerificationExpectation:
    identity: VerificationIdentity
    record: VerificationRecord | None = None


@dataclass(frozen=True, slots=True)
class HostSettings:
    bind_host: str
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    deployment_epoch: str
    retention_profile: str
    principal: PrincipalBoundary
    selections: tuple[ConfiguredCapability, ...] = ()
    verification: tuple[VerificationExpectation, ...] = ()
    execution: ExecutionLimits = ExecutionLimits()
    max_raw_bytes: int = 4 * 1024 * 1024
    installed_owners: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for value in (self.bind_host, self.deployment_epoch, self.retention_profile):
            require_text(value, "host identity")
        require_positive(self.max_raw_bytes, "max_raw_bytes")
        if not self.allowed_hosts or any(value == "*" for value in self.allowed_hosts):
            raise ValueError("Explicit allowed hosts are required")
        if any(value == "*" for value in self.allowed_origins):
            raise ValueError("Explicit allowed origins are required")
        packages = [item.identity.package for item in self.verification]
        if len(set(packages)) != len(packages):
            raise ValueError("Duplicate verification expectations")
        self.principal.validate_bind(self.bind_host)
