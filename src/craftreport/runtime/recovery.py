"""Trusted runtime-owned recovery use case over kernel outcome_update and journal CAS."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from craftreport.application import ports
from craftreport.application.outcomes import OutcomeFacts, ResultValidation, outcome_update
from craftreport.application.registry import Codec, ObservedCommand
from craftreport.contracts import (
    Availability,
    Diagnostic,
    EffectDisposition,
    EvidencePolicy,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    RecoveryDisposition,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.contracts.values import require_enum, require_text
from craftreport.runtime.ports import (
    PublicationDecisionReader,
    RecoveryJournal,
    RecoveryResults,
    RuntimeStore,
)
from craftreport.runtime.publication import PublicationResult
from craftreport.runtime.scheduler import BindingScheduler
from craftreport.runtime.values import (
    BindingState,
    EffectObservation,
    InspectRequest,
    RunPins,
    TargetIdentity,
)


@dataclass(frozen=True, slots=True)
class ReconcileRequest:
    operation_id: str | None = None
    binding_id: str | None = None
    expected_generation: int = 0
    run_id: str | None = None
    observation: EffectObservation | None = None

    def __post_init__(self) -> None:
        if (self.operation_id, self.binding_id, self.run_id) == (None, None, None):
            raise ValueError("Reconciliation requires an operation, binding or run target")
        for label, val in (
            ("operation_id", self.operation_id),
            ("binding_id", self.binding_id),
            ("run_id", self.run_id),
        ):
            if val is not None:
                require_text(val, label)
        low = 1 if self.binding_id is not None else 0
        if type(self.expected_generation) is not int or not low <= self.expected_generation < 2**63:
            raise ValueError("expected_generation out of range")
        if self.observation is not None and type(self.observation) is not EffectObservation:
            raise TypeError("observation requires EffectObservation")


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    status: Literal["reconciled", "already_terminal", "ambiguous"]
    operation_id: str | None = None
    operation_state: ReceiptState | None = None
    reconciliation_ref: EvidenceRef | None = None
    prior_evidence: tuple[EvidenceRef, ...] = ()
    binding: BindingState | None = None
    run: RunPins | None = None

    def __post_init__(self) -> None:
        if self.status not in ("reconciled", "already_terminal", "ambiguous"):
            raise ValueError("Unsupported reconciliation status")
        if self.operation_id is not None:
            require_text(self.operation_id, "operation_id")
        if self.operation_state is not None:
            require_enum(self.operation_state, ReceiptState)
        object.__setattr__(self, "prior_evidence", tuple(self.prior_evidence))


def _prior_evidence(receipt: Receipt) -> tuple[EvidenceRef, ...]:
    return tuple(
        dict.fromkeys(
            (*receipt.evidence, *(ref for stage in receipt.stages for ref in stage.evidence))
        )
    )


async def _mark_ambiguous(
    journal: RecoveryJournal, receipt: Receipt
) -> Receipt | ports.ServiceUnavailable:
    diag = Diagnostic(
        receipt.operation, "execution", "interrupted_startup", RecoveryDisposition.RECONCILE
    )
    observed = ObservedCommand(EffectDisposition.UNKNOWN, (), (), (diag,), None, lambda: None)
    facts = OutcomeFacts(
        ResultValidation.MISSING if receipt.result_ref is None else ResultValidation.VALID,
        receipt.result_ref,
        receipt.result_availability or Availability.MISSING,
        receipt.expected_versions,
    )
    recorded = await journal.record(
        receipt.operation_id,
        receipt.revision,
        outcome_update(receipt, observed, facts, EvidencePolicy()),
    )
    return recorded if isinstance(recorded, Receipt) else ports.ServiceUnavailable("journal")


async def sweep_startup_orphans(journal: RecoveryJournal, bindings: RuntimeStore) -> None:
    nonterminal = await journal.list_nonterminal()
    if isinstance(nonterminal, ports.ServiceUnavailable):
        raise RuntimeError("Recovery journal enumeration unavailable")
    for _, retained in nonterminal:
        if retained.receipt.state in (ReceiptState.ACCEPTED, ReceiptState.PENDING):
            if not isinstance(await _mark_ambiguous(journal, retained.receipt), Receipt):
                raise RuntimeError("Startup orphan ambiguity update failed")
    recoverable = await bindings.list_recoverable()
    if isinstance(recoverable, ports.ServiceUnavailable):
        raise RuntimeError("Recovery binding enumeration unavailable")
    for owner, state in recoverable:
        active = (
            state.intent == "running"
            or state.pending_operation_id is not None
            or state.pause_pending
        )
        if active and (not state.recovery_required or state.pause_pending):
            next_state = replace(
                state, revision=state.revision + 1, recovery_required=True, pause_pending=False
            )
            if not isinstance(await bindings.save_binding(owner, state, next_state), BindingState):
                raise RuntimeError("Startup binding suspension failed")


@dataclass(frozen=True, slots=True)
class RecoveryUseCase:
    journal: RecoveryJournal
    results: RecoveryResults
    evidence: ports.EvidenceReader
    resources: ports.ResourceReader
    snapshots: PublicationDecisionReader
    bindings: RuntimeStore
    scheduler: BindingScheduler
    publication_result_codec: Codec[PublicationResult]
    binding_result_codec: Codec[
        BindingState | RunPins | ports.Missing | ports.ServiceUnavailable | ports.VersionConflict
    ]
    owner_policy: Callable[[Principal], bool]
    target_policy: Callable[[Principal, TargetIdentity], bool]

    async def startup_sweep(self) -> None:
        await sweep_startup_orphans(self.journal, self.bindings)

    async def _retain_fact(
        self,
        operation_id: str,
        operation: OperationKey,
        versions: tuple[ExpectedVersion, ...],
        outcome: Literal["complete", "partial", "failed"],
        prior: tuple[EvidenceRef, ...],
    ) -> EvidenceRef | ports.ServiceUnavailable:
        fact: JsonObject = {
            "schema_version": "1",
            "operation_id": operation_id,
            "outcome": outcome,
            "prior_evidence": tuple(ref.identity for ref in prior),
        }
        raw = json.dumps(fact, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        ref = EvidenceRef(
            uuid4().hex,
            "reconciliation",
            operation_id,
            operation,
            versions,
            sha256(raw).hexdigest(),
        )
        return await self.results.retain_reconciliation_fact(ref, fact)

    async def _resource_versions(
        self, resources: tuple[ResourceRef, ...], fallback: tuple[ExpectedVersion, ...]
    ) -> tuple[ExpectedVersion, ...] | ports.ServiceUnavailable:
        if not resources:
            return fallback
        items: list[ExpectedVersion] = []
        for res in resources:
            snap = await self.resources.read(res)
            if isinstance(snap, ports.ServiceUnavailable):
                return snap
            items.append(
                ExpectedVersion(res, "absent") if isinstance(snap, ports.Missing) else snap.version
            )
        return tuple(items)

    async def _commit_update(
        self,
        current: Receipt,
        effect: EffectDisposition,
        stages: tuple[StageResult, ...],
        ev_refs: tuple[EvidenceRef, ...],
        recon_ref: EvidenceRef,
        versions: tuple[ExpectedVersion, ...],
        result_ref: object | None,
        policy: EvidencePolicy,
    ) -> ReconcileResult | ports.ServiceUnavailable:
        all_refs = (*ev_refs, recon_ref)
        statuses = await self.evidence.inspect(all_refs)
        observed = ObservedCommand(effect, stages, all_refs, (), None, lambda: None)
        valid = result_ref is not None
        facts = OutcomeFacts(
            ResultValidation.VALID if valid else ResultValidation.MISSING,
            result_ref,  # type: ignore[arg-type]
            Availability.AVAILABLE if valid else Availability.MISSING,
            versions,
            statuses,
            reconciliation=(recon_ref,),
        )
        updated = await self.journal.record(
            current.operation_id, current.revision, outcome_update(current, observed, facts, policy)
        )
        return (
            ReconcileResult("reconciled", current.operation_id, updated.state, recon_ref, ev_refs)
            if isinstance(updated, Receipt)
            else ports.ServiceUnavailable("journal")
        )

    async def _record_committed(
        self,
        principal: Principal,
        current: Receipt,
        encoded_result: JsonObject,
        effect: EffectDisposition,
        stage_name: str,
        versions: tuple[ExpectedVersion, ...],
        ev_refs: tuple[EvidenceRef, ...],
    ) -> ReconcileResult | ports.ServiceUnavailable:
        try:
            result_ref = await self.results.write(principal, current.operation_id, encoded_result)
        except ports.ServiceUnavailableError as error:
            return error.reason
        recon_ref = await self._retain_fact(
            current.operation_id, current.operation, versions, "complete", ev_refs
        )
        if isinstance(recon_ref, ports.ServiceUnavailable):
            return recon_ref
        return await self._commit_update(
            current,
            effect,
            (StageResult(stage_name, StageState.PASSED, "verified", ev_refs),),
            ev_refs,
            recon_ref,
            versions,
            result_ref,
            EvidencePolicy((stage_name,)),
        )

    async def _record_absent(
        self,
        current: Receipt,
        prior: tuple[EvidenceRef, ...],
        policy: EvidencePolicy,
    ) -> ReconcileResult | ports.ServiceUnavailable:
        versions = await self._resource_versions(current.resources, current.expected_versions)
        if isinstance(versions, ports.ServiceUnavailable):
            return versions
        recon_ref = await self._retain_fact(
            current.operation_id, current.operation, versions, "failed", prior
        )
        if isinstance(recon_ref, ports.ServiceUnavailable):
            return recon_ref
        stages = tuple(
            StageResult(name, StageState.FAILED, "effect_absent", ())
            for name in policy.required_stages
        )
        res = await self._commit_update(
            current, EffectDisposition.NONE, stages, (), recon_ref, versions, None, policy
        )
        return replace(res, prior_evidence=prior) if isinstance(res, ReconcileResult) else res

    async def _reconcile_local(
        self,
        principal: Principal,
        current: Receipt,
        prior: tuple[EvidenceRef, ...],
    ) -> ReconcileResult | ports.ServiceUnavailable | None:
        if current.operation == OperationKey("snapshot.publish", "1"):
            dec = await self.snapshots.read_decision(current.operation_id)
            if isinstance(dec, (ports.ServiceUnavailable, ports.Missing)):
                return (
                    dec
                    if isinstance(dec, ports.ServiceUnavailable)
                    else await self._record_absent(
                        current, prior, EvidencePolicy(("publication_decided",))
                    )
                )
            return await self._record_committed(
                principal,
                current,
                self.publication_result_codec.encode(dec.result),
                dec.effect,
                "publication_decided",
                dec.completion_pins,
                dec.evidence,
            )
        if current.operation == OperationKey("runtime.bind", "1"):
            bdec = await self.bindings.read_decision(current.operation_id)
            if isinstance(bdec, (ports.ServiceUnavailable, ports.Missing)):
                return (
                    bdec
                    if isinstance(bdec, ports.ServiceUnavailable)
                    else await self._record_absent(
                        current, prior, EvidencePolicy(("binding_persisted",))
                    )
                )
            state, versions, ev_refs = bdec
            res = await self._record_committed(
                principal,
                current,
                self.binding_result_codec.encode(state),
                EffectDisposition.APPLIED,
                "binding_persisted",
                versions,
                ev_refs,
            )
            return replace(res, binding=state) if isinstance(res, ReconcileResult) else res
        return None

    async def reconcile_operation(
        self,
        principal: Principal,
        operation_id: str,
        external: EffectObservation | None = None,
    ) -> ReconcileResult | ports.Missing | ports.ServiceUnavailable:
        retained = await self.journal.read_command(principal, operation_id)
        if not isinstance(retained, ports.RetainedCommand):
            return retained
        current = retained.receipt
        prior = _prior_evidence(current)
        if current.state in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
            return ReconcileResult("already_terminal", operation_id, current.state, None, prior)
        if current.state in (ReceiptState.ACCEPTED, ReceiptState.PENDING):
            marked = await _mark_ambiguous(self.journal, current)
            if not isinstance(marked, Receipt):
                return marked
            current = marked
        local = await self._reconcile_local(principal, current, prior)
        return (
            local
            if local is not None
            else await self._reconcile_external(principal, current, prior, external)
        )

    async def _reconcile_external(
        self,
        principal: Principal,
        current: Receipt,
        prior: tuple[EvidenceRef, ...],
        external: EffectObservation | None,
    ) -> ReconcileResult | ports.ServiceUnavailable:
        if external is None and self.scheduler.runtime.app is not None:
            inspected = await self.scheduler.runtime.app.inspect(current.operation_id)
            if isinstance(inspected, ports.ServiceUnavailable):
                return inspected
            external = inspected if isinstance(inspected, EffectObservation) else None
        if external is None:
            if current.operation == OperationKey("runtime.control", "1"):
                return await self._record_absent(current, prior, EvidencePolicy())
            return ReconcileResult(
                "ambiguous", current.operation_id, ReceiptState.AMBIGUOUS, None, prior
            )
        sanitized = await self.scheduler.runtime.verify_observation(external)
        if sanitized.effect is EffectDisposition.UNKNOWN:
            return ReconcileResult(
                "ambiguous", current.operation_id, ReceiptState.AMBIGUOUS, None, prior
            )
        versions = await self._resource_versions(current.resources, current.expected_versions)
        if isinstance(versions, ports.ServiceUnavailable):
            return versions
        outcome: Literal["complete", "partial", "failed"] = (
            "complete"
            if sanitized.verified_complete
            else "partial"
            if sanitized.effect in (EffectDisposition.APPLIED, EffectDisposition.PARTIAL)
            else "failed"
        )
        recon_ref = await self._retain_fact(
            current.operation_id, current.operation, versions, outcome, prior
        )
        if isinstance(recon_ref, ports.ServiceUnavailable):
            return recon_ref
        result_ref = current.result_ref if outcome == "complete" else None
        if outcome == "complete" and result_ref is None:
            try:
                result_ref = await self.results.write(
                    principal,
                    current.operation_id,
                    {"reconciled": True, "run_id": sanitized.run_id},
                )
            except ports.ServiceUnavailableError as error:
                return error.reason
        eff = sanitized.effect if outcome != "partial" else EffectDisposition.PARTIAL
        res = await self._commit_update(
            current, eff, (), (), recon_ref, versions, result_ref, EvidencePolicy()
        )
        return replace(res, prior_evidence=prior) if isinstance(res, ReconcileResult) else res

    async def reconcile(
        self,
        principal: Principal,
        request: ReconcileRequest,
        current_operation_id: str,
    ) -> ReconcileResult | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        if not self.owner_policy(principal):
            return ports.ServiceUnavailable("binding_access")
        run: RunPins | None = None
        if request.run_id is not None:
            found_run = await self.bindings.inspect(
                principal, InspectRequest("run", request.run_id)
            )
            if not isinstance(found_run, RunPins):
                return (
                    found_run
                    if isinstance(found_run, (ports.Missing, ports.ServiceUnavailable))
                    else ports.ServiceUnavailable("run_inspect")
                )
            if not self.target_policy(principal, found_run.target) or (
                request.binding_id is not None and found_run.binding_id != request.binding_id
            ):
                return ports.ServiceUnavailable("binding_access")
            run = found_run
        if request.binding_id is not None:
            return await self._reconcile_binding(principal, request, current_operation_id, run)
        if request.operation_id is not None:
            res = await self.reconcile_operation(
                principal, request.operation_id, request.observation
            )
            return (
                replace(res, run=run)
                if isinstance(res, ReconcileResult) and run is not None
                else res
            )
        assert run is not None
        pin = ExpectedVersion(ResourceRef("run", run.run_id), run.prepared_digest)
        ref = await self._retain_fact(
            current_operation_id, OperationKey("runtime.reconcile", "1"), (pin,), "complete", ()
        )
        return (
            ref
            if isinstance(ref, ports.ServiceUnavailable)
            else ReconcileResult("reconciled", reconciliation_ref=ref, run=run)
        )

    async def _load_binding(
        self, principal: Principal, binding_id: str, expected_generation: int
    ) -> BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        current = await self.bindings.inspect(principal, InspectRequest("binding", binding_id))
        if not isinstance(current, BindingState):
            return (
                current
                if isinstance(current, (ports.Missing, ports.ServiceUnavailable))
                else ports.ServiceUnavailable("binding_inspect")
            )
        if not self.target_policy(principal, current.spec.target):
            return ports.ServiceUnavailable("target_unavailable")
        res = ResourceRef("binding", binding_id)
        if current.generation != expected_generation:
            return ports.VersionConflict(
                (ExpectedVersion(res, str(expected_generation)),),
                (ExpectedVersion(res, str(current.generation)),),
            )
        return current

    async def _reconcile_binding(
        self,
        principal: Principal,
        request: ReconcileRequest,
        current_operation_id: str,
        run: RunPins | None,
    ) -> ReconcileResult | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        assert request.binding_id is not None
        slot = self.scheduler.fence_for(request.binding_id, principal)
        async with slot.fence:
            loaded = await self._load_binding(
                principal, request.binding_id, request.expected_generation
            )
            if not isinstance(loaded, BindingState):
                return loaded
            op_id = request.operation_id or loaded.pending_operation_id
            current, ambig = await self._apply_binding_observation(
                principal, loaded, op_id, request.observation
            )
            if not isinstance(current, BindingState):
                return current
            op_res = (
                await self.reconcile_operation(principal, op_id, request.observation)
                if op_id is not None
                else None
            )
            if isinstance(op_res, ports.ServiceUnavailable):
                return op_res
            if ambig or (isinstance(op_res, ReconcileResult) and op_res.status == "ambiguous"):
                return ReconcileResult(
                    "ambiguous", op_id, ReceiptState.AMBIGUOUS, None, (), current, run
                )
            if current.recovery_required or current.pending_operation_id is not None:
                saved = await self.bindings.save_binding(
                    principal,
                    current,
                    replace(
                        current,
                        revision=current.revision + 1,
                        recovery_required=False,
                        pending_operation_id=None,
                    ),
                )
                if not isinstance(saved, BindingState):
                    return saved
                current = saved
            if current.intent == "running":
                self.scheduler.resume_recovered(request.binding_id, slot)
        return await self._finalize_binding_reconcile(
            request.binding_id, current_operation_id, op_id, op_res, current, run
        )

    async def _finalize_binding_reconcile(
        self,
        binding_id: str,
        current_operation_id: str,
        op_id: str | None,
        op_res: ReconcileResult | ports.Missing | None,
        current: BindingState,
        run: RunPins | None,
    ) -> ReconcileResult | ports.ServiceUnavailable:
        recon_ref = op_res.reconciliation_ref if isinstance(op_res, ReconcileResult) else None
        prior = op_res.prior_evidence if isinstance(op_res, ReconcileResult) else ()
        if recon_ref is None:
            res = ResourceRef("binding", binding_id)
            pins = (
                (ExpectedVersion(res, str(current.revision)),)
                if run is None
                else (
                    ExpectedVersion(res, str(current.revision)),
                    ExpectedVersion(ResourceRef("run", run.run_id), run.prepared_digest),
                )
            )
            created = await self._retain_fact(
                current_operation_id,
                OperationKey("runtime.reconcile", "1"),
                pins,
                "complete",
                prior,
            )
            if isinstance(created, ports.ServiceUnavailable):
                return created
            recon_ref = created
        return ReconcileResult(
            "reconciled",
            op_id,
            op_res.operation_state if isinstance(op_res, ReconcileResult) else None,
            recon_ref,
            prior,
            current,
            run,
        )

    async def _apply_binding_observation(
        self,
        principal: Principal,
        current: BindingState,
        op_id: str | None,
        observation: EffectObservation | None,
    ) -> tuple[
        BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable, bool
    ]:
        if observation is None and op_id is not None and self.scheduler.runtime.app is not None:
            inspected = await self.scheduler.runtime.app.inspect(op_id)
            if isinstance(inspected, ports.ServiceUnavailable):
                return inspected, False
            observation = inspected if isinstance(inspected, EffectObservation) else None
        if observation is None:
            return current, False
        sanitized = await self.scheduler.runtime.verify_observation(observation)
        updated = await self.bindings.observe_effect(principal, current, sanitized)
        if (
            not isinstance(updated, BindingState)
            or sanitized.effect is not EffectDisposition.UNKNOWN
        ):
            return updated, False
        saved = await self.bindings.save_binding(
            principal,
            updated,
            replace(
                updated,
                revision=updated.revision + 1,
                recovery_required=True,
                pending_operation_id=op_id,
            ),
        )
        return saved, True
