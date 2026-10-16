"""One scoped installed activation and concrete durable guarantee assembly."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path
from typing import TYPE_CHECKING

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from craftreport.adapters.binding_codecs import BindingResultCodec, bind_codec, inspect_codec
from craftreport.adapters.snapshot_wire import (
    finalize_snapshot,
    latest_request_codec,
    latest_result_codec,
    publication_codec,
    publication_result_codec,
    snapshot_read_codec,
    snapshot_reference_codec,
)
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.guard import DurableGuard
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import (
    DurableHandoffs,
    DurableHealth,
    DurableResources,
    HealthProbe,
)
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.snapshots import Fingerprint
from craftreport.adapters.validation import PydanticCodec, StrictWireModel
from craftreport.application import ports
from craftreport.application.capabilities import CapabilityInstance
from craftreport.application.registry import BoundOperation, Codec
from craftreport.composition.app import HostedApplication, open_application
from craftreport.composition.plugins import ActivationSnapshot
from craftreport.composition.settings import (
    ConfiguredCapability,
    GuaranteeProviders,
    HostSettings,
    configure,
)
from craftreport.contracts import (
    CapabilityManifest,
    CapabilityRequirement,
    CapabilityVersion,
    Principal,
    ResourceRef,
)
from craftreport.data.values import Snapshot
from craftreport.runtime.bindings import BindingOperations
from craftreport.runtime.capability import (
    BindingCodecs,
    PublicationCodecs,
    binding_descriptors,
    binding_operations,
    publication_descriptors,
    publication_operations,
)
from craftreport.runtime.ports import SnapshotQueries
from craftreport.runtime.publication import PublicationOperations
from craftreport.runtime.values import TargetIdentity

if TYPE_CHECKING:
    from craftreport.composition.reporting import ReportingActivation


def snapshot_operation_bindings(
    resources: DurableResources,
    *,
    owner_policy: Callable[[Principal], bool],
    target_policy: Callable[[Principal, TargetIdentity], bool] = lambda _p, _t: False,
) -> tuple[BoundOperation, ...]:
    """Explicit owner policy grants inspection of that owner's retained feed history."""
    if not callable(owner_policy):
        raise ValueError("Explicit snapshot owner policy required")

    def queries(principal: Principal) -> SnapshotQueries:
        if owner_policy(principal) is not True:
            raise ValueError("Snapshot owner policy denied")
        return resources.store.queries(principal)

    handlers = PublicationOperations(
        resources.store,
        queries,
        finalize_snapshot,
        resources.store.codec,
        lambda: datetime.now(UTC),
    )
    resources.configure_bindings(bind_codec(), BindingResultCodec())
    bindings = BindingOperations(resources.bindings, bind_codec(), owner_policy, target_policy)
    return (
        *publication_operations(handlers, _publication_codecs()),
        *binding_operations(bindings, _binding_codecs()),
    )


def _binding_codecs() -> BindingCodecs:
    return BindingCodecs(bind_codec(), inspect_codec(), BindingResultCodec())


def _publication_codecs() -> PublicationCodecs:
    return PublicationCodecs(
        publication_codec(),
        publication_result_codec(),
        snapshot_reference_codec(),
        snapshot_read_codec(),
        latest_request_codec(),
        latest_result_codec(),
    )


@dataclass(frozen=True, slots=True)
class SnapshotSettings:
    """No caller-controlled provider or ownership settings in the first profile."""


SNAPSHOT_SETTINGS = PydanticCodec(
    StrictWireModel, lambda value: SnapshotSettings(), lambda value: {}
).for_input()


def implementation_digest() -> str:
    digest = sha256()
    root = Path(__file__).resolve().parents[1]
    for entry in sorted(root.rglob("*.py")):
        content = entry.read_bytes()
        name = entry.relative_to(root).as_posix().encode()
        digest.update(len(name).to_bytes(8, "big") + name)
        digest.update(len(content).to_bytes(8, "big") + content)
    return "sha256:" + digest.hexdigest()


class SnapshotFactory:
    def describe(self) -> CapabilityManifest:
        installed = distribution("craftreport")
        return CapabilityManifest(
            "snapshot",
            "craftreport",
            installed.version,
            ">=1.0,<2.0",
            (CapabilityVersion("snapshot", "1.0.0"),),
            (),
            SNAPSHOT_SETTINGS.schema(),
            (
                *publication_descriptors(_publication_codecs()),
                *binding_descriptors(_binding_codecs()),
            ),
            implementation_digest(),
        )

    @asynccontextmanager
    async def open(
        self, services: tuple[BoundOperation, ...], settings: SnapshotSettings
    ) -> AsyncGenerator[CapabilityInstance]:
        SNAPSHOT_SETTINGS.decode(SNAPSHOT_SETTINGS.encode(settings))

        async def close() -> None:
            pass  # Providers own resources; these immutable bindings acquire none.

        yield CapabilityInstance(services, close)


def snapshot_factory() -> SnapshotFactory:
    return SnapshotFactory()


def configure_snapshot(
    resources: DurableResources,
    *,
    owner_policy: Callable[[Principal], bool],
    target_policy: Callable[[Principal, TargetIdentity], bool] = lambda _p, _t: False,
) -> ConfiguredCapability:
    def adapt(loaded: object) -> SnapshotFactory:
        if loaded is not snapshot_factory:
            raise ValueError("Unexpected snapshot capability factory")
        return snapshot_factory()

    return configure(
        "craftreport",
        "snapshot",
        adapt,
        snapshot_operation_bindings(
            resources, owner_policy=owner_policy, target_policy=target_policy
        ),
        SNAPSHOT_SETTINGS,
        {},
    )


class ActivatedCapabilities:
    def __init__(self, probe: HealthProbe) -> None:
        self._owner_probe = probe
        self._attempted = False
        self._snapshot: ActivationSnapshot | None = None

    @asynccontextmanager
    async def bind(self, snapshot: ActivationSnapshot) -> AsyncGenerator[None]:
        if self._attempted:
            raise ValueError("Activation binding is one-shot")
        self._attempted = True
        try:
            identities: set[str] = set()
            for manifest in snapshot.manifests:
                for provided in manifest.provided:
                    if provided.identity in identities:
                        raise ValueError("Duplicate activated capability")
                    identities.add(provided.identity)
                    Version(provided.version)
            self._snapshot = snapshot
            yield
        finally:
            self._snapshot = None

    async def probe(self) -> ports.ServiceUnavailable | None:
        snapshot = self._snapshot
        if snapshot is not None:
            try:
                result = await self._owner_probe()
                if result is None and self._snapshot is snapshot:
                    return None
            except Exception:
                pass
        return ports.ServiceUnavailable("capabilities")

    async def check(
        self, requirements: tuple[CapabilityRequirement, ...], resources: tuple[ResourceRef, ...]
    ) -> ports.CapabilityDecision:
        if await self.probe() is not None or self._snapshot is None:
            return ports.ServiceUnavailable("capabilities")
        provided = {
            item.identity: item
            for manifest in self._snapshot.manifests
            for item in manifest.provided
        }
        unsupported: list[CapabilityRequirement] = []
        for requirement in requirements:
            candidate = provided.get(requirement.identity)
            try:
                supported = (
                    candidate is not None
                    and requirement.target_mode is None
                    and Version(candidate.version) in SpecifierSet(requirement.version_range)
                )
            except InvalidSpecifier:
                supported = False
            if not supported:
                unsupported.append(requirement)
        return (
            ports.CapabilitiesUnsupported(tuple(unsupported))
            if unsupported
            else ports.CapabilitiesSupported(
                tuple(dict.fromkeys(provided[req.identity] for req in requirements))
            )
        )


@asynccontextmanager
async def open_snapshot_application(
    path: Path,
    deployment_id: str,
    settings: Callable[[Database, DurableResources], HostSettings],
    *,
    codec: Codec[Snapshot],
    fingerprint: Fingerprint,
    normalization_policy: str,
    owner_probes: Mapping[str, HealthProbe],
    reporting: Callable[[Database, DurableResources], "ReportingActivation"] | None = None,
) -> AsyncGenerator[HostedApplication]:
    if not {"access", "capabilities"} <= owner_probes.keys():
        raise ValueError("Explicit access and capability health owners required")
    async with AsyncExitStack() as stack:
        database = Database(path, deployment_id)
        stack.push_async_callback(database.close)
        resources = DurableResources(database, codec, fingerprint, normalization_policy)
        activation = reporting(database, resources) if reporting is not None else None
        if activation is not None:
            if activation.resources.upstream is not resources or "report_packs" in owner_probes:
                raise ValueError("Reporting provider identity or health owner differs")
            resources.guard = DurableGuard(database, activation.resources.combined_read)
        resolver = ActivatedCapabilities(owner_probes["capabilities"])
        handoffs = DurableHandoffs(database, resources.guard)
        stack.callback(handoffs.close)
        health = DurableHealth(
            database,
            resources,
            {
                **owner_probes,
                "capabilities": resolver.probe,
                **({"report_packs": activation.resources.health} if activation is not None else {}),
            },
        )
        stack.callback(health.close)
        services = GuaranteeProviders(
            DurableJournal(database),
            resources.guard,
            DurableEvidence(database, resources.verify_binding),
            resolver,
            activation.resources if activation is not None else resources,
            resources,
            DurableResults(database),
            handoffs,
            health,
        )
        configured = settings(database, resources)
        if activation is not None:
            from craftreport.adapters.report_resources import ReportAccessPolicy

            configured = replace(
                configured,
                selections=(*configured.selections, activation.capability),
                principal=replace(
                    configured.principal,
                    policy=ReportAccessPolicy(
                        configured.principal.access_policy, activation.resources
                    ),
                ),
            )
        if (
            configured.principal.deployment_scope,
            configured.deployment_epoch,
            configured.retention_profile,
        ) != (
            database.deployment.identity,
            database.deployment.epoch,
            database.deployment.retention_profile,
        ):
            raise ValueError("Host and retained deployment identities differ")

        @asynccontextmanager
        async def providers() -> AsyncGenerator[GuaranteeProviders]:
            yield services

        host = await stack.enter_async_context(
            open_application(configured, providers(), on_activation=resolver.bind)
        )
        yield host
