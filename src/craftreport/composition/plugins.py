"""Allowlisted installed capability activation with transactional publication."""

from collections.abc import AsyncGenerator, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from graphlib import TopologicalSorter
from importlib.metadata import distributions

from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version

from craftreport.application.registry import BoundOperation, ImmutableOperationRegistry
from craftreport.composition.settings import ConfiguredCapability, PreparedCapability
from craftreport.contracts import CapabilityManifest
from craftreport.contracts.capabilities import CORE_CONTRACT_VERSION


def _reserved(identity: str) -> bool:
    return identity == "craftreport" or identity.startswith("craftreport.")


def _load(selection: ConfiguredCapability) -> PreparedCapability:
    name = canonicalize_name(selection.distribution, validate=True)
    matches = [d for d in distributions() if canonicalize_name(d.metadata["Name"]) == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one installed distribution: {name}")
    distribution = matches[0]
    points = [
        p
        for p in distribution.entry_points
        if p.group == "craftreport.capabilities" and p.name == selection.entry_point
    ]
    if len(points) != 1:
        raise ValueError(f"Expected one selected entry point: {selection.entry_point}")
    loaded: object = points[0].load()
    prepared = selection.prepare(loaded)
    manifest = prepared.manifest
    if canonicalize_name(manifest.package, validate=True) != name:
        raise ValueError("Manifest package does not match installed distribution")
    if Version(manifest.version) != Version(distribution.version):
        raise ValueError("Manifest version does not match installed distribution")
    if Version(CORE_CONTRACT_VERSION) not in SpecifierSet(manifest.core_contract_range):
        raise ValueError("Incompatible core contract")
    return prepared


def _unique_names(manifests: Sequence[CapabilityManifest]) -> dict[str, tuple[str, Version]]:
    identities: set[str] = set()
    provided: dict[str, tuple[str, Version]] = {}
    tools: set[str] = set()
    for manifest in manifests:
        if manifest.identity in identities or _reserved(manifest.identity):
            raise ValueError(f"Duplicate or reserved capability identity: {manifest.identity}")
        identities.add(manifest.identity)
        for item in manifest.provided:
            if item.identity in provided or _reserved(item.identity):
                raise ValueError(f"Duplicate or reserved provided identity: {item.identity}")
            provided[item.identity] = (manifest.identity, Version(item.version))
        for operation in manifest.operations:
            name = f"{operation.key.name}.v{operation.key.contract_version}"
            if name in tools or _reserved(operation.key.name) or len(name) > 128:
                raise ValueError(f"Duplicate, reserved or oversized MCP name: {name}")
            tools.add(name)
    return provided


def _ordered(prepared: Sequence[PreparedCapability]) -> tuple[PreparedCapability, ...]:
    provided = _unique_names([item.manifest for item in prepared])
    graph: dict[str, set[str]] = {}
    by_id = {item.manifest.identity: item for item in prepared}
    for item in prepared:
        manifest = item.manifest
        dependencies: set[str] = set()
        for requirement in manifest.required:
            provider = provided.get(requirement.identity)
            if provider is None or provider[1] not in SpecifierSet(requirement.version_range):
                raise ValueError(
                    f"{manifest.identity}: missing/incompatible {requirement.identity}"
                )
            dependencies.add(provider[0])
        graph[manifest.identity] = dependencies
    return tuple(by_id[identity] for identity in TopologicalSorter(graph).static_order())


@asynccontextmanager
async def activate(
    selections: Sequence[ConfiguredCapability],
) -> AsyncGenerator[ImmutableOperationRegistry]:
    """Only yield after every selected capability has initialized and matched.

    The snapshot is valid only inside this context. Cleanup exceptions propagate;
    AsyncExitStack still attempts every already-entered context in reverse order.
    """
    prepared: list[PreparedCapability] = []
    for selection in selections:
        try:
            prepared.append(_load(selection))
        except Exception as exc:
            raise ValueError(f"{selection.distribution}/{selection.entry_point}: {exc}") from exc
    ordered = _ordered(prepared)
    async with AsyncExitStack() as stack:
        bindings: list[BoundOperation] = []
        for item in ordered:
            try:
                instance = await stack.enter_async_context(item.open())
                ImmutableOperationRegistry(instance.bindings, item.manifest.operations)
                bindings.extend(instance.bindings)
            except Exception as exc:
                raise ValueError(f"{item.manifest.identity}: initialization failed: {exc}") from exc
        yield ImmutableOperationRegistry(bindings)
