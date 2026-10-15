"""One scoped installed activation and concrete durable guarantee assembly."""

from collections.abc import AsyncGenerator, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import (
    DurableHandoffs,
    DurableHealth,
    DurableResources,
    HealthProbe,
)
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.snapshots import Fingerprint
from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.composition.app import HostedApplication, open_application
from craftreport.composition.plugins import ActivationSnapshot
from craftreport.composition.settings import GuaranteeProviders, HostSettings
from craftreport.contracts import CapabilityRequirement, ResourceRef
from craftreport.data.values import Snapshot


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
) -> AsyncGenerator[HostedApplication]:
    if not {"access", "capabilities"} <= owner_probes.keys():
        raise ValueError("Explicit access and capability health owners required")
    async with AsyncExitStack() as stack:
        database = Database(path, deployment_id)
        stack.push_async_callback(database.close)
        resources = DurableResources(database, codec, fingerprint, normalization_policy)
        resolver = ActivatedCapabilities(owner_probes["capabilities"])
        handoffs = DurableHandoffs(database, resources.guard)
        stack.callback(handoffs.close)
        health = DurableHealth(
            database, resources, {**owner_probes, "capabilities": resolver.probe}
        )
        stack.callback(health.close)
        services = GuaranteeProviders(
            DurableJournal(database),
            resources.guard,
            DurableEvidence(database),
            resolver,
            resources,
            resources,
            DurableResults(database),
            handoffs,
            health,
        )
        configured = settings(database, resources)
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
