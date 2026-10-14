"""Synthetic operations use runtime contexts, never test providers or global state."""

from dataclasses import dataclass, replace

from craftreport.adapters.canonical import canonical_bytes
from craftreport.application import ports
from craftreport.application.registry import (
    BoundOperation,
    CommandBehavior,
    OperationBinding,
    QueryBehavior,
)
from craftreport.contracts import (
    CapabilityRequirement,
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

from .models import (
    LIMITS,
    PROBE,
    READ,
    RESULT,
    WRITE,
    ProbeRequest,
    ReadRequest,
    Result,
    WriteRequest,
)


def descriptors(
    namespace: str, resource_kind: str, boundary_probe: bool = False, capability_probe: bool = False
) -> tuple[OperationDescriptor, ...]:
    base = (
        OperationDescriptor(
            OperationKey(f"{namespace}.write", "1"),
            OperationKind.COMMAND,
            WRITE.schema(),
            RESULT.schema(),
            True,
            True,
            (resource_kind,),
            (CapabilityRequirement("synthetic-target", ">=1.0,<2.0", "native"),)
            if capability_probe
            else (),
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
    if not boundary_probe:
        return base
    return (
        *base,
        replace(base[0], key=OperationKey(f"{namespace}.probe", "1"), input_schema=PROBE.schema()),
    )


def sized_result(size: int, version: str) -> Result:
    """Return exactly size compact UTF-8 JSON bytes, retaining the observed version."""
    overhead = len(canonical_bytes({"value": "", "version": version}))
    if size < overhead:
        raise ValueError("Requested output cannot contain the observed version")
    return Result("x" * (size - overhead), version)


@dataclass(frozen=True)
class Operations:
    namespace: str
    resource_kind: str

    def resources(
        self, request: ReadRequest | WriteRequest | ProbeRequest
    ) -> tuple[ResourceRef, ...]:
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

    async def probe(
        self, request: ProbeRequest, context: ports.CommandContext
    ) -> OutcomeProposal[Result]:
        observation = await self.write(WriteRequest(request.resource, request.value), context)
        observation = replace(
            observation,
            diagnostics=tuple(
                replace(item, operation=OperationKey(f"{self.namespace}.probe", "1"))
                for item in observation.diagnostics
            ),
        )
        if observation.result is None or request.output_size == 0:
            return observation
        return replace(
            observation, result=sized_result(request.output_size, observation.result.version)
        )

    def bindings(
        self, boundary_probe: bool = False, capability_probe: bool = False
    ) -> tuple[BoundOperation, ...]:
        write, read = descriptors(
            self.namespace, self.resource_kind, capability_probe=capability_probe
        )
        base = (
            OperationBinding(
                write, WRITE, RESULT, CommandBehavior(self.write), self.resources
            ).bind(),
            OperationBinding(read, READ, RESULT, QueryBehavior(self.read), self.resources).bind(),
        )
        if not boundary_probe:
            return base
        probe = descriptors(self.namespace, self.resource_kind, True, capability_probe)[2]
        return (
            *base,
            OperationBinding(
                probe, PROBE, RESULT, CommandBehavior(self.probe), self.resources
            ).bind(),
        )
