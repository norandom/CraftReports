"""Immutable pack observations and original durable preparation facts."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from types import MappingProxyType
from typing import cast
from uuid import uuid4

from pydantic import TypeAdapter
from sqlalchemy.engine import Connection

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.pack_reader import ConfiguredPackReader, PackSource
from craftreport.adapters.storage.providers import DurableResources
from craftreport.adapters.storage.results import DurableResults
from craftreport.application import ports
from craftreport.contracts import EvidenceRef, ExpectedVersion, JsonObject, Principal, ResourceRef
from craftreport.contracts.pins import VersionPin
from craftreport.reporting.ports import PackFailure, PackSelection, PreparationFact

_fact = TypeAdapter(PreparationFact)
_pin = TypeAdapter(VersionPin)
_REPORT_KINDS = ("report_pack_source", "report_pack_artifact_scope")


def observations(
    reader: ConfiguredPackReader, sources: tuple[PackSource, ...], deployment: str
) -> Mapping[ResourceRef, ports.ResourceSnapshot]:
    values: dict[ResourceRef, ports.ResourceSnapshot] = {}
    for scope in sorted({source.source_visibility_scope for source in sources}):
        principal = Principal(deployment, "report_activation", frozenset({scope}))
        for summary in reader.discover(principal):
            namespace, name = summary.identity.split("/")
            selection = PackSelection(namespace, name, summary.version)
            pack = reader.read(selection, principal)
            if isinstance(pack, PackFailure):
                raise ValueError("Configured pack observation unavailable")
            identity = f"{selection.identity}@{selection.version}"
            pin = cast(JsonObject, _pin.dump_python(pack.pin.version_pin, mode="json"))
            metadata: tuple[JsonObject, JsonObject] = (
                {
                    "pack": pin,
                    "source_visibility_scope": scope,
                    "template_digest": pack.template.content_digest,
                    "theme_digest": pack.theme.version_pin.content_digest,
                },
                {
                    "pack": pin,
                    "attribution": pack.pin.attribution,
                    "artifact_visibility_scope": pack.pin.artifact_visibility_scope,
                },
            )
            for kind, content in zip(_REPORT_KINDS, metadata, strict=True):
                resource = ResourceRef(kind, identity)
                token = sha256(canonical_bytes(content)).hexdigest()
                values[resource] = ports.ResourceSnapshot(ExpectedVersion(resource, token), content)
    return MappingProxyType(values)


@dataclass(frozen=True, slots=True)
class ReportResources:
    packs: ConfiguredPackReader
    sources: tuple[PackSource, ...]
    upstream: DurableResources
    observations: Mapping[ResourceRef, ports.ResourceSnapshot] = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observations",
            observations(self.packs, self.sources, self.upstream.database.deployment.identity),
        )

    def combined_read(
        self, connection: Connection, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing:
        if resource.kind in _REPORT_KINDS:
            return self.observations.get(resource, ports.Missing())
        return self.upstream.combined_read(connection, resource)

    async def read(
        self, resource: ResourceRef
    ) -> ports.ResourceSnapshot | ports.Missing | ports.ServiceUnavailable:
        if resource.kind in _REPORT_KINDS:
            return self.observations.get(resource, ports.Missing())
        return await self.upstream.read(resource)

    async def health(self) -> ports.ServiceUnavailable | None:
        # ConfiguredPackReader validated every opened asset at immutable activation.
        # DurableHealth independently checks database lifetime and fact retention.
        if not self.observations:
            return ports.ServiceUnavailable("report_packs")
        return None


@dataclass(frozen=True, slots=True)
class ReportAccessPolicy:
    upstream: ports.AccessPolicy
    resources: ReportResources

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        decision = await self.upstream.authorize(principal, action)
        if not isinstance(decision, ports.AccessAllowed):
            return decision
        if isinstance(action, ports.OperationAccess):
            for resource in action.resources:
                if resource.kind not in _REPORT_KINDS:
                    continue
                observed = self.resources.observations.get(resource)
                key = (
                    "source_visibility_scope"
                    if resource.kind == "report_pack_source"
                    else "artifact_visibility_scope"
                )
                if observed is None or observed.content[key] not in principal.permitted_scopes:
                    return ports.AccessDenied()
            for resource in action.resources:
                if resource.kind == "report_pack_source":
                    decision = await self._statement_access(principal, resource)
                    if not isinstance(decision, ports.AccessAllowed):
                        return decision
        return decision

    async def _statement_access(
        self, principal: Principal, resource: ResourceRef
    ) -> ports.AccessDecision:
        for summary in self.resources.packs.discover(principal):
            if f"{summary.identity}@{summary.version}" != resource.identity:
                continue
            namespace, name = summary.identity.split("/")
            pack = self.resources.packs.read(
                PackSelection(namespace, name, summary.version), principal
            )
            if isinstance(pack, PackFailure):
                return ports.AccessDenied()
            statement = pack.definition.compliance_statement
            if statement is not None:
                for operation_id in dict.fromkeys(ref.operation_id for ref in statement.evidence):
                    decision = await self.upstream.authorize(
                        principal, ports.ReceiptAccess(operation_id)
                    )
                    if not isinstance(decision, ports.AccessAllowed):
                        return decision
            return ports.AccessAllowed()
        return ports.AccessDenied()


@dataclass(frozen=True, slots=True)
class PreparationFactWriter:
    results: DurableResults

    async def record(self, fact: PreparationFact) -> EvidenceRef | ports.ServiceUnavailable:
        content = cast(
            JsonObject,
            _fact.dump_python(
                fact,
                mode="json",
                exclude={"operation_id", "operation", "resource_versions"},
            ),
        )
        reference = EvidenceRef(
            uuid4().hex,
            fact.stage,
            fact.operation_id,
            fact.operation,
            fact.resource_versions,
            sha256(canonical_bytes(content)).hexdigest(),
        )
        # This existing method verifies closed fields, original command, all pins,
        # exact bytes/digests and independent DurableEvidence readback atomically.
        return await self.results.retain_preparation_fact(reference, content)
