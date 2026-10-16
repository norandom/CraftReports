"""Real durable facade with explicit test-only owner authorization."""

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import DurableHandoffs, DurableHealth
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.validation import DecodedInvocationLimits
from craftreport.application import ports
from craftreport.application.admission import CommandAdmission
from craftreport.application.dispatch import Inspection, QueryDispatcher
from craftreport.application.execution import Execution
from craftreport.application.guards import InvocationGuards
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.composition.snapshot_host import snapshot_operation_bindings
from craftreport.contracts import CapabilityRequirement, Catalog, Principal, ResourceRef
from tests.snapshot_runtime.test_providers import FEED, provider


class OwnerAccess:
    def __init__(self) -> None:
        self.denied: set[str] = set()

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        if principal.subject != "alice" or principal.deployment_scope != "deployment-a":
            return ports.AccessDenied()
        if isinstance(action, ports.OperationAccess):
            if action.operation.name in self.denied or any(
                ref.kind in self.denied
                or ref.identity != FEED.identity
                and not ref.identity.startswith(FEED.identity + ":")
                for ref in action.resources
            ):
                return ports.AccessDenied()
        return ports.AccessAllowed()


class EmptyCapabilities:
    async def check(
        self, requirements: tuple[CapabilityRequirement, ...], resources: tuple[ResourceRef, ...]
    ) -> ports.CapabilityDecision:
        return (
            ports.CapabilitiesUnsupported(requirements)
            if requirements
            else ports.CapabilitiesSupported(())
        )


async def available() -> None:
    return None


class PublicationFixture:
    def __init__(self, database: Database) -> None:
        self.resources = provider(database)
        self.journal = DurableJournal(database)
        self.evidence = DurableEvidence(database)
        self.results = DurableResults(database)
        self.access = OwnerAccess()
        capabilities = EmptyCapabilities()
        health = DurableHealth(
            database, self.resources, {"access": available, "capabilities": available}
        )
        bindings = snapshot_operation_bindings(
            self.resources, owner_policy=lambda p: p.subject == "alice"
        )
        registry = ImmutableOperationRegistry(bindings)
        guards = InvocationGuards(
            registry, self.access, capabilities, health, DecodedInvocationLimits()
        )
        catalog = Catalog(
            registry.describe(),
            (),
            database.deployment.epoch,
            database.deployment.retention_profile,
        )
        reads = ports.ReadServices(self.evidence, capabilities, self.resources)
        self.facade = Execution(
            CommandAdmission(guards, self.journal, self.resources.guard, CanonicalFingerprint()),
            QueryDispatcher(guards, self.journal, reads, self.results, catalog),
            Inspection(catalog, self.access, self.journal, self.results, self.evidence),
            ports.CommandServices(reads, self.resources),
            DurableHandoffs(database, self.resources.guard),
        )
