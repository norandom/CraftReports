"""Binding operations and pin selection; neither schedules nor starts app effects."""

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING
from uuid import uuid4

from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    OutcomeProposal,
    Principal,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.runtime.ports import (
    AppOperationCaller,
    RunPreparer,
    RuntimeStore,
    SnapshotQueries,
)
from craftreport.runtime.publication import LatestRequest, LatestSelection
from craftreport.runtime.values import (
    BindingState,
    BindRequest,
    CancellationObservation,
    ControlRequest,
    EffectObservation,
    InspectRequest,
    PreparationIssue,
    PreparedRunInputs,
    RunPins,
    TargetIdentity,
)

if TYPE_CHECKING:
    from craftreport.runtime.recovery import (
        ReconcileRequest,
        ReconcileResult,
        RecoveryUseCase,
    )
    from craftreport.runtime.scheduler import BindingScheduler


@dataclass(frozen=True, slots=True)
class BindingOperations:
    store: RuntimeStore
    request_codec: Codec[BindRequest]
    owner_policy: Callable[[Principal], bool]
    target_policy: Callable[[Principal, TargetIdentity], bool]
    scheduler: "BindingScheduler | None" = None
    recovery: "RecoveryUseCase | None" = None

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

    async def control(
        self, request: "ControlRequest", context: ports.CommandContext
    ) -> OutcomeProposal[
        BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable
    ]:
        if not self.owner_policy(context.principal) or self.scheduler is None:
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_access"), EffectDisposition.NONE, (), ()
            )
        before = await self.store.inspect(
            context.principal, InspectRequest("binding", request.binding_id)
        )
        if isinstance(before, BindingState) and not self.target_policy(
            context.principal, before.spec.target
        ):
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_access"), EffectDisposition.NONE, (), ()
            )
        result = await self.scheduler.control(context.principal, request)
        if isinstance(result, (ports.Missing, ports.VersionConflict)):
            return OutcomeProposal(result, EffectDisposition.NONE, (), ())
        if isinstance(result, ports.ServiceUnavailable):
            return OutcomeProposal(result, EffectDisposition.UNKNOWN, (), ())
        return OutcomeProposal(result, EffectDisposition.APPLIED, (), ())

    async def reconcile(
        self, request: "ReconcileRequest", context: ports.CommandContext
    ) -> OutcomeProposal[
        "ReconcileResult | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable"
    ]:
        if not self.owner_policy(context.principal) or self.recovery is None:
            return OutcomeProposal(
                ports.ServiceUnavailable("binding_access"), EffectDisposition.NONE, (), ()
            )
        result = await self.recovery.reconcile(context.principal, request, context.operation_id)
        if isinstance(result, (ports.Missing, ports.VersionConflict)):
            return OutcomeProposal(result, EffectDisposition.NONE, (), ())
        if isinstance(result, ports.ServiceUnavailable):
            return OutcomeProposal(result, EffectDisposition.NONE, (), ())
        refs = tuple(
            dict.fromkeys(
                (
                    *(
                        (result.reconciliation_ref,)
                        if result.reconciliation_ref is not None
                        else ()
                    ),
                    *result.prior_evidence,
                )
            )
        )
        stage_refs = (result.reconciliation_ref,) if result.reconciliation_ref is not None else ()
        stage = StageResult(
            "reconciled",
            StageState.PASSED if result.status != "ambiguous" else StageState.PENDING,
            "observed" if result.status != "ambiguous" else "ambiguous",
            stage_refs,
        )
        return OutcomeProposal(
            result,
            EffectDisposition.APPLIED
            if result.reconciliation_ref is not None
            else EffectDisposition.NONE,
            (stage,),
            refs,
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
    evidence: ports.EvidenceReader | None = None
    app: AppOperationCaller | None = None

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
        return await self.store.select_run(
            principal, state, pins, latest_complete=selection.highest_complete
        )

    async def verify_observation(self, observation: EffectObservation) -> EffectObservation:
        verified = False
        if self.evidence is not None and observation.verified_complete and observation.evidence:
            statuses = await self.evidence.inspect(observation.evidence)
            verified = len(statuses) == len(observation.evidence) and all(
                st.reference == ref
                and st.availability is Availability.AVAILABLE
                and st.verification is StageState.PASSED
                for st, ref in zip(statuses, observation.evidence, strict=True)
            )
        return observation if verified else replace(observation, verified_complete=False)

    async def observe_effect(
        self,
        principal: Principal,
        expected: BindingState,
        observation: EffectObservation,
    ) -> BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        sanitized = await self.verify_observation(observation)
        return await self.store.observe_effect(principal, expected, sanitized)

    async def observe_operation(
        self,
        principal: Principal,
        expected: BindingState,
        operation_id: str,
    ) -> BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        if self.app is None:
            return ports.ServiceUnavailable("app_caller")
        observed = await self.app.inspect(operation_id)
        if not isinstance(observed, EffectObservation):
            return observed
        return await self.observe_effect(principal, expected, observed)

    async def cancel_operation(
        self,
        principal: Principal,
        expected: BindingState,
        operation_id: str,
    ) -> CancellationObservation | ports.Missing | ports.ServiceUnavailable:
        if self.app is None:
            return ports.ServiceUnavailable("app_caller")
        cancelled = await self.app.cancel(operation_id)
        if isinstance(cancelled, CancellationObservation) and cancelled.observation is not None:
            await self.observe_effect(
                principal, expected, replace(cancelled.observation, verified_complete=False)
            )
        return cancelled
