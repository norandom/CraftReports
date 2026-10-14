"""Synthetic operations use runtime contexts, never test providers or global state."""

from dataclasses import dataclass

from craftreport.application import ports
from craftreport.application.registry import (
    BoundOperation,
    CommandBehavior,
    OperationBinding,
    QueryBehavior,
)
from craftreport.contracts import (
    Diagnostic,
    EffectDisposition,
    EvidencePolicy,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OutcomeProposal,
    RecoveryDisposition,
    ResourceRef,
    StageResult,
    StageState,
)

from .models import LIMITS, READ, RESULT, WRITE, ReadRequest, Result, WriteRequest


def descriptors(namespace: str, resource_kind: str) -> tuple[OperationDescriptor, ...]:
    return (
        OperationDescriptor(
            OperationKey(f"{namespace}.write", "1"),
            OperationKind.COMMAND,
            WRITE.schema(),
            RESULT.schema(),
            True,
            True,
            (resource_kind,),
            (),
            ("resources", "effects", "guard", "evidence"),
            LIMITS,
            EvidencePolicy(("effect",)),
        ),
        OperationDescriptor(
            OperationKey(f"{namespace}.read", "1"),
            OperationKind.QUERY,
            READ.schema(),
            RESULT.schema(),
            False,
            False,
            (resource_kind,),
            (),
            ("resources",),
            LIMITS,
            EvidencePolicy(),
        ),
    )


@dataclass(frozen=True)
class Operations:
    namespace: str
    resource_kind: str

    def resources(self, request: ReadRequest | WriteRequest) -> tuple[ResourceRef, ...]:
        return (ResourceRef(self.resource_kind, request.resource),)

    async def read(self, request: ReadRequest, context: ports.ReadContext) -> Result:
        snapshot = await context.services.resources.read(self.resources(request)[0])
        if not isinstance(snapshot, ports.ResourceSnapshot):
            raise RuntimeError("Synthetic resource unavailable")
        value = snapshot.content.get("value")
        if not isinstance(value, str):
            raise RuntimeError("Synthetic resource has invalid content")
        return Result(value, snapshot.version.version)

    async def write(
        self, request: WriteRequest, context: ports.CommandContext
    ) -> OutcomeProposal[Result]:
        observation = await context.services.effects.apply(
            self.resources(request)[0], {"value": request.value}, context.guard
        )
        if not isinstance(observation, ports.ResourceEffect):
            diagnostic = Diagnostic(
                OperationKey(f"{self.namespace}.write", "1"),
                "effect",
                "effect_not_started",
                RecoveryDisposition.INSPECT,
            )
            return OutcomeProposal(None, EffectDisposition.NONE, (), (), (diagnostic,))
        confirmed = observation.effect is EffectDisposition.APPLIED and bool(observation.evidence)
        stage = StageResult(
            "effect",
            StageState.PASSED if confirmed else StageState.PENDING,
            "provider_observation" if confirmed else "evidence_unresolved",
            observation.evidence,
        )
        result = (
            Result(request.value, observation.versions[0].version) if observation.versions else None
        )
        return OutcomeProposal(result, observation.effect, (stage,), observation.evidence, ())

    def bindings(self) -> tuple[BoundOperation, ...]:
        write, read = descriptors(self.namespace, self.resource_kind)
        return (
            OperationBinding(
                write, WRITE, RESULT, CommandBehavior(self.write), self.resources
            ).bind(),
            OperationBinding(read, READ, RESULT, QueryBehavior(self.read), self.resources).bind(),
        )
