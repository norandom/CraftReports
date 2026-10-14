"""Explicitly configured synthetic access, capability and evidence providers.

These fixtures make no production durability, browser or reporting-artifact claim.
Construct fresh providers for each run; retention and evidence end with that run.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from fixture_journal import FixtureJournal
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CapabilityRequirement,
    CapabilityVersion,
    EvidenceRef,
    EvidenceStatus,
    OperationKey,
    Principal,
    Receipt,
    ResourceRef,
)


@dataclass(frozen=True)
class AccessGrant:
    deployment_scope: str
    subject: str
    scopes: frozenset[str]
    resources: frozenset[ResourceRef]
    catalog: bool = False


class FixtureAccessPolicy:
    """Deny by default; trusted identity, scopes AND resource grant must match."""

    def __init__(
        self,
        journal: FixtureJournal,
        grants: tuple[AccessGrant, ...],
        operation_scopes: Mapping[OperationKey, str],
    ) -> None:
        self.journal = journal
        self.grants = grants
        self.operation_scopes = dict(operation_scopes)
        self.available = True

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        if not self.available:
            return ports.ServiceUnavailable("access")
        grants = [
            g
            for g in self.grants
            if (g.deployment_scope, g.subject) == (principal.deployment_scope, principal.subject)
        ]
        if len(grants) != 1:
            return ports.AccessDenied()
        grant = grants[0]
        scopes = grant.scopes & principal.permitted_scopes
        if isinstance(action, ports.CatalogAccess):
            allowed = grant.catalog and "catalog" in scopes
        elif isinstance(action, ports.OperationAccess):
            allowed = (
                self.operation_scopes.get(action.operation) in scopes
                and set(action.resources) <= grant.resources
            )
        else:
            return await self._receipt_access(principal, action, grant, scopes)
        return ports.AccessAllowed() if allowed else ports.AccessDenied()

    async def _receipt_access(
        self,
        principal: Principal,
        action: ports.ReceiptAccess,
        grant: AccessGrant,
        scopes: frozenset[str],
    ) -> ports.AccessDecision:
        if not self.journal.available:
            return ports.ServiceUnavailable("journal")
        if "inspect" not in scopes or self.journal.owners.get(action.operation_id) != (
            principal.deployment_scope,
            principal.subject,
        ):
            return ports.AccessDenied()
        try:
            receipt = await self.journal.read(action.operation_id)
        except ports.ServiceUnavailableError as error:
            return error.reason
        allowed = isinstance(receipt, Receipt) and set(receipt.resources) <= grant.resources
        return ports.AccessAllowed() if allowed else ports.AccessDenied()


@dataclass(frozen=True)
class CapabilitySupport:
    version: CapabilityVersion
    modes: frozenset[str] = frozenset()


class FixtureCapabilities:
    def __init__(
        self, supported: tuple[CapabilitySupport, ...], resource_modes: Mapping[ResourceRef, str]
    ) -> None:
        self.supported = {item.version.identity: item for item in supported}
        if len(self.supported) != len(supported):
            raise ValueError("Duplicate capability support")
        self.resource_modes = dict(resource_modes)
        self.available = True

    def _supports(
        self, requirement: CapabilityRequirement, resources: tuple[ResourceRef, ...]
    ) -> bool:
        support = self.supported.get(requirement.identity)
        if support is None:
            return False
        try:
            if Version(support.version.version) not in SpecifierSet(requirement.version_range):
                return False
        except (InvalidSpecifier, InvalidVersion):
            return False
        mode = requirement.target_mode
        return mode is None or (
            mode in support.modes
            and all(self.resource_modes.get(resource) == mode for resource in resources)
        )

    async def check(
        self, requirements: tuple[CapabilityRequirement, ...], resources: tuple[ResourceRef, ...]
    ) -> ports.CapabilityDecision:
        if not self.available:
            return ports.ServiceUnavailable("capabilities")
        unsupported = tuple(req for req in requirements if not self._supports(req, resources))
        if unsupported:
            return ports.CapabilitiesUnsupported(unsupported)
        versions = dict.fromkeys(self.supported[req.identity].version for req in requirements)
        return ports.CapabilitiesSupported(tuple(versions))


class FixtureEvidence:
    """Exact pinned references only; inspecting never fabricates or regenerates proof."""

    def __init__(self, statuses: tuple[EvidenceStatus, ...] = ()) -> None:
        self._statuses = {status.reference: status for status in statuses}
        self.available = True

    def retain(self, status: EvidenceStatus) -> None:
        self._statuses[status.reference] = status

    async def inspect(self, refs: tuple[EvidenceRef, ...]) -> tuple[EvidenceStatus, ...]:
        if not self.available:
            return tuple(EvidenceStatus(ref, Availability.UNAVAILABLE) for ref in refs)
        return tuple(
            self._statuses.get(ref, EvidenceStatus(ref, Availability.MISSING)) for ref in refs
        )
