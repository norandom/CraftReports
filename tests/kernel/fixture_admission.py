"""Admission effect fixture with real typed binding and temporary providers."""

from dataclasses import replace

from fixture_dispatch import ALICE, BOB, RESOURCE, DispatchFixture, ResultWire
from fixture_services import AccessGrant, FixtureAccessPolicy

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.validation import PydanticCodec, StrictWireModel
from craftreport.application import ports
from craftreport.application.admission import AdmittedCommand, CommandAdmission
from craftreport.application.guards import InvocationGuards
from craftreport.application.registry import (
    CommandBehavior,
    ImmutableOperationRegistry,
    OperationBinding,
)
from craftreport.contracts import (
    ExpectedVersion,
    InvocationEnvelope,
    OperationKey,
    OperationKind,
    OutcomeProposal,
    Receipt,
    Rejection,
)

KEY = OperationKey("fixture.write", "1")


class WriteWire(StrictWireModel):
    value: str = "changed"


class AdmissionFixture(DispatchFixture):
    def __init__(self) -> None:
        super().__init__()
        codec = PydanticCodec(
            WriteWire, lambda wire: wire.value, lambda value: {"value": value}
        ).for_input()
        result = PydanticCodec(ResultWire, lambda wire: wire.value, lambda value: {"value": value})
        descriptor = replace(
            self.binding.descriptor,
            key=KEY,
            kind=OperationKind.COMMAND,
            starts_business_work=True,
            changes_business_state=True,
            input_schema=codec.schema(),
            result_schema=result.schema(),
        )
        binding = OperationBinding(
            descriptor, codec, result, CommandBehavior(self.write), lambda _: (RESOURCE,)
        )
        self.command_binding = binding
        self.registry = ImmutableOperationRegistry((binding.bind(),))
        self.access = FixtureAccessPolicy(
            self.journal,
            tuple(
                AccessGrant(
                    "deployment", subject, ALICE.permitted_scopes, frozenset({RESOURCE}), True
                )
                for subject in ("alice", "bob")
            ),
            {KEY: "read"},
        )
        self.health.probes["guard"] = lambda: self.target.available
        self.guards = InvocationGuards(
            self.registry, self.access, self.capabilities, self.health, self.guards.limits
        )
        self.admission = CommandAdmission(
            self.guards, self.journal, self.target, CanonicalFingerprint()
        )
        self.services = ports.CommandServices(self.reads, self.target)
        self.bob = replace(BOB, permitted_scopes=ALICE.permitted_scopes)

    async def write(self, request: str, context: ports.CommandContext) -> OutcomeProposal[str]:
        self.calls += 1
        effect = await context.services.effects.apply(RESOURCE, {"value": request}, context.guard)
        assert isinstance(effect, ports.ResourceEffect)
        return OutcomeProposal(request, effect.effect, (), ())

    def request(self, **changes: object) -> InvocationEnvelope:
        return replace(
            InvocationEnvelope(KEY, {}, "correlation", "retry", (ExpectedVersion(RESOURCE, "1"),)),
            **changes,
        )

    async def run(self, request: InvocationEnvelope | None = None) -> Receipt | Rejection:
        async with self.admission.open(ALICE, request or self.request()) as result:
            if isinstance(result, AdmittedCommand):
                await result.invoke(self.services)
                return result.receipt
            return result
