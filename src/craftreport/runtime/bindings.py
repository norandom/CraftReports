"""Binding operations and pin selection; neither schedules nor starts app effects."""

from collections.abc import Callable
from dataclasses import dataclass, fields
from uuid import uuid4

from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    EffectDisposition,
    OutcomeProposal,
    Principal,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.runtime.ports import RunPreparer, RuntimeStore, SnapshotQueries
from craftreport.runtime.publication import LatestRequest, LatestSelection
from craftreport.runtime.values import (
    BindingState,
    BindRequest,
    InspectRequest,
    PreparationIssue,
    PreparedRunInputs,
    RunPins,
    TargetIdentity,
)


@dataclass(frozen=True, slots=True)
class BindingOperations:
    store: RuntimeStore
    request_codec: Codec[BindRequest]
    owner_policy: Callable[[Principal], bool]
    target_policy: Callable[[Principal, TargetIdentity], bool]

    async def bind(
        self, request: BindRequest, context: ports.CommandContext
    ) -> OutcomeProposal[BindingState | ports.VersionConflict | ports.ServiceUnavailable]:
        if not self.owner_policy(context.principal) or not self.target_policy(
            context.principal, request.spec.target
        ):
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_access"), EffectDisposition.NONE, (), ()
            )
        effect = await context.services.effects.apply(
            ResourceRef("binding", request.spec.binding_id),
            {"operation_id": context.operation_id, "request": self.request_codec.encode(request)},
            context.guard,
        )
        if isinstance(effect, ports.VersionConflict):
            return OutcomeProposal(effect, EffectDisposition.NONE, (), ())
        if isinstance(effect, ports.ServiceUnavailable):
            return OutcomeProposal(effect, EffectDisposition.UNKNOWN, (), ())
        if not isinstance(effect, ports.ResourceEffect):
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_guard"), EffectDisposition.NONE, (), ()
            )
        state = await self.store.inspect(
            context.principal, InspectRequest("binding", request.spec.binding_id)
        )
        if not isinstance(state, BindingState) or state.spec != request.spec:
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_readback"),
                EffectDisposition.UNKNOWN,
                (),
                effect.evidence,
            )
        return OutcomeProposal(
            state,
            effect.effect,
            (
                StageResult(
                    "binding_persisted", StageState.PASSED, "binding_persisted", effect.evidence
                ),
            ),
            effect.evidence,
        )

    async def inspect(
        self, request: InspectRequest, context: ports.ReadContext
    ) -> BindingState | RunPins | ports.Missing | ports.ServiceUnavailable:
        if not self.owner_policy(context.principal):
            return ports.ServiceUnavailable("binding_access")
        result = await self.store.inspect(context.principal, request)
        target = (
            result.spec.target
            if isinstance(result, BindingState)
            else result.target
            if isinstance(result, RunPins)
            else None
        )
        if target is not None and not self.target_policy(context.principal, target):
            return ports.ServiceUnavailable("binding_access")
        return result


@dataclass(frozen=True, slots=True)
class BindingRuntime:
    store: RuntimeStore
    queries: Callable[[Principal], SnapshotQueries]
    preparer: RunPreparer

    async def select(
        self, principal: Principal, binding_id: str
    ) -> (
        RunPins
        | PreparationIssue
        | ports.Missing
        | ports.VersionConflict
        | ports.ServiceUnavailable
    ):
        state = await self.store.inspect(principal, InspectRequest("binding", binding_id))
        if not isinstance(state, BindingState):
            return (
                state
                if isinstance(state, (ports.Missing, ports.ServiceUnavailable))
                else ports.ServiceUnavailable("binding")
            )
        selection = await self.queries(principal).latest(
            LatestRequest(state.spec.feed_id, state.spec.requirements)
        )
        if not isinstance(selection, LatestSelection):
            return selection
        if selection.highest_complete is None:
            return PreparationIssue(
                "incomplete_binding", tuple(i.location for i in selection.latest_issues)
            )
        prepared = await self.preparer.prepare(state.spec, selection.highest_complete)
        if not isinstance(prepared, PreparedRunInputs):
            return prepared
        shared = (
            "definition",
            "template",
            "theme",
            "pack",
            "resolved_parameters",
            "parameter_digest",
            "validation_scope",
        )
        if prepared.snapshot != selection.highest_complete or any(
            getattr(prepared, n) != getattr(state.spec, n) for n in shared
        ):
            return PreparationIssue("preparation_mismatch")
        values = {f.name: getattr(prepared, f.name) for f in fields(prepared)}
        pins = RunPins(
            run_id=uuid4().hex,
            binding_id=binding_id,
            binding_generation=state.generation,
            target=state.spec.target,
            **values,
        )
        return await self.store.select_run(principal, state, pins)
