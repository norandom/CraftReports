"""Explicit temporary providers and real typed query wiring for dispatcher cases."""

from collections.abc import Callable
from dataclasses import replace

from fixture_journal import FixtureJournal
from fixture_services import AccessGrant, FixtureAccessPolicy, FixtureCapabilities, FixtureEvidence
from fixture_target import SyntheticTarget

from craftreport.adapters.validation import DecodedInvocationLimits, PydanticCodec, StrictWireModel
from craftreport.application import ports
from craftreport.application.dispatch_ports import RetainedResult
from craftreport.application.guards import InvocationGuards
from craftreport.application.registry import (
    ImmutableOperationRegistry,
    OperationBinding,
    QueryBehavior,
)
from craftreport.contracts import (
    Availability,
    Catalog,
    EvidencePolicy,
    InvocationEnvelope,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OperationLimits,
    Principal,
    ResourceRef,
)
from craftreport.contracts.values import freeze_object

KEY = OperationKey("fixture.read", "1")
RESOURCE = ResourceRef("fixture", "target")
ALICE = Principal("deployment", "alice", frozenset({"read", "catalog", "inspect"}))
BOB = Principal("deployment", "bob", frozenset({"catalog", "inspect"}))


class ReadWire(StrictWireModel):
    target: str


class ResultWire(StrictWireModel):
    value: str


class FixtureHealth:
    def __init__(self, probes: dict[str, Callable[[], bool]]) -> None:
        self.probes = probes
        self.checked: list[tuple[str, ...]] = []

    async def check(self, required: tuple[str, ...]) -> ports.ServiceUnavailable | None:
        self.checked.append(required)
        for name in required:
            probe = self.probes.get(name)
            if probe is None or not probe():
                return ports.ServiceUnavailable(name)
        return None


class FixtureResults:
    def __init__(self) -> None:
        self.available = True
        self.values: dict[tuple[str, str, str, str], JsonObject] = {}
        self.read_availability: Availability | None = None

    async def write(self, principal: Principal, operation_id: str, value: JsonObject) -> str:
        if not self.available:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("results"))
        reference = f"result-{operation_id}"
        self.values[(principal.deployment_scope, principal.subject, operation_id, reference)] = (
            freeze_object(value)
        )
        return reference

    async def read(self, principal: Principal, operation_id: str, reference: str) -> RetainedResult:
        if not self.available or self.read_availability is not None:
            return RetainedResult(reference, self.read_availability or Availability.UNAVAILABLE)
        value = self.values.get(
            (principal.deployment_scope, principal.subject, operation_id, reference)
        )
        if value is not None:
            return RetainedResult(reference, Availability.AVAILABLE, value)
        status = (
            Availability.INACCESSIBLE
            if any(key[3] == reference for key in self.values)
            else Availability.MISSING
        )
        return RetainedResult(reference, status)


class DispatchFixture:
    def __init__(self, limits: OperationLimits = OperationLimits()) -> None:
        self.journal = FixtureJournal()
        self.target = SyntheticTarget({RESOURCE: {"value": "retained"}})
        self.capabilities = FixtureCapabilities((), {})
        self.evidence = FixtureEvidence()
        self.results = FixtureResults()
        self.calls = 0
        self.access = FixtureAccessPolicy(
            self.journal,
            (
                AccessGrant(
                    "deployment", "alice", ALICE.permitted_scopes, frozenset({RESOURCE}), True
                ),
                AccessGrant("deployment", "bob", BOB.permitted_scopes, frozenset(), True),
            ),
            {KEY: "read"},
        )
        self.health = FixtureHealth(
            {
                "access": lambda: self.access.available,
                "journal": lambda: self.journal.available,
                "resources": lambda: self.target.available,
                "capabilities": lambda: self.capabilities.available,
                "results": lambda: self.results.available,
                "evidence": lambda: self.evidence.available,
            }
        )
        input_codec = PydanticCodec(
            ReadWire, lambda wire: wire.target, lambda target: {"target": target}, limits
        ).for_input()
        result_codec = PydanticCodec(
            ResultWire, lambda wire: wire.value, lambda value: {"value": value}, limits
        )
        descriptor = OperationDescriptor(
            KEY,
            OperationKind.QUERY,
            input_codec.schema(),
            result_codec.schema(),
            False,
            False,
            ("fixture",),
            (),
            (),
            limits,
            EvidencePolicy(),
        )
        self.binding = OperationBinding(
            descriptor,
            input_codec,
            result_codec,
            QueryBehavior(self.read),
            lambda target: (ResourceRef("fixture", target),),
        )
        self.registry = ImmutableOperationRegistry((self.binding.bind(),))
        self.guards = InvocationGuards(
            self.registry, self.access, self.capabilities, self.health, DecodedInvocationLimits()
        )
        self.catalog = Catalog(
            self.registry.describe(), (), self.journal.epoch, self.journal.retention_profile
        )
        self.reads = ports.ReadServices(self.evidence, self.capabilities, self.target)

    async def read(self, request: str, context: ports.ReadContext) -> str:
        self.calls += 1
        assert type(context.services) is ports.ReadServices
        assert not hasattr(context.services, "effects") and not hasattr(context, "guard")
        value = await context.services.resources.read(ResourceRef("fixture", request))
        if not isinstance(value, ports.ResourceSnapshot):
            raise ValueError("private target failure")
        content = value.content["value"]
        assert isinstance(content, str)
        return content

    def request(self, **changes: object) -> InvocationEnvelope:
        return replace(InvocationEnvelope(KEY, {"target": "target"}, "correlation"), **changes)
