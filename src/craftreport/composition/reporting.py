"""Compatibility boundary; report capability activation belongs to task 8."""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from craftreport.adapters import report_codecs as codecs
from craftreport.adapters.pack_reader import ConfiguredPackReader, PackSource
from craftreport.adapters.report_resources import PreparationFactWriter, ReportResources
from craftreport.adapters.storage.providers import DurableResources
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.snapshots import SnapshotStore
from craftreport.application.capabilities import CapabilityInstance
from craftreport.application.registry import BoundOperation
from craftreport.composition.settings import ConfiguredCapability, configure
from craftreport.composition.snapshot_host import (
    SNAPSHOT_SETTINGS,
    SnapshotSettings,
    implementation_digest,
)
from craftreport.contracts import CapabilityManifest, Principal
from craftreport.contracts.identity import CapabilityRequirement, CapabilityVersion
from craftreport.data.ports import SnapshotReader
from craftreport.reporting.operations import ReportOperations
from craftreport.reporting.registration import ReportCodecs, report_descriptors, report_operations


def is_compatible(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
    try:
        return version.identity == requirement.identity and Version(
            version.version
        ) in SpecifierSet(requirement.version_range)
    except (InvalidVersion, InvalidSpecifier):
        return False


def report_codecs() -> ReportCodecs:
    return ReportCodecs(
        codecs.validation_request_codec(),
        codecs.validation_result_codec(),
        codecs.discovery_request_codec(),
        codecs.discovery_result_codec(),
        codecs.preparation_request_codec(),
        codecs.preparation_result_codec(),
    )


class ReportingFactory:
    def describe(self) -> CapabilityManifest:
        return CapabilityManifest(
            "reporting",
            "craftreport",
            version("craftreport"),
            ">=1.0,<2.0",
            (CapabilityVersion("reporting", "1.0.0"),),
            (),
            SNAPSHOT_SETTINGS.schema(),
            report_descriptors(report_codecs()),
            implementation_digest(),
        )

    @asynccontextmanager
    async def open(
        self, services: tuple[BoundOperation, ...], settings: SnapshotSettings
    ) -> AsyncGenerator[CapabilityInstance]:
        SNAPSHOT_SETTINGS.decode(SNAPSHOT_SETTINGS.encode(settings))

        async def close() -> None:
            pass  # Bindings acquire no external resources; the host owns providers.

        yield CapabilityInstance(services, close)


def reporting_factory() -> ReportingFactory:
    return ReportingFactory()


@dataclass(frozen=True, slots=True)
class ReportingActivation:
    capability: ConfiguredCapability
    resources: ReportResources


def configure_reporting(
    resources: DurableResources,
    sources: tuple[PackSource, ...],
    *,
    owner_policy: Callable[[Principal], bool],
) -> ReportingActivation:
    if type(resources) is not DurableResources or type(resources.store) is not SnapshotStore:
        raise ValueError("Concrete bounded durable snapshot provider required")
    if not callable(owner_policy):
        raise ValueError("Explicit snapshot owner policy required")
    packs = ConfiguredPackReader(sources)
    observed = ReportResources(packs, sources, resources)

    def snapshots(principal: Principal) -> SnapshotReader:
        if owner_policy(principal) is not True:
            raise ValueError("Snapshot owner policy denied")
        return resources.store.queries(principal)

    handlers = ReportOperations(
        packs,
        snapshots,
        PreparationFactWriter(DurableResults(resources.database)),
        codecs.definition_identifier,
        codecs.prepared_identifier,
        codecs.validation_scope_identifier,
        is_compatible,
    )

    def adapt(loaded: object) -> ReportingFactory:
        if loaded is not reporting_factory:
            raise ValueError("Unexpected reporting capability factory")
        return reporting_factory()

    selected = configure(
        "craftreport",
        "reporting",
        adapt,
        report_operations(handlers, report_codecs()),
        SNAPSHOT_SETTINGS,
        {},
    )
    return ReportingActivation(selected, observed)
