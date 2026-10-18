"""Runtime integration: RunPreparer, AppOperationCaller, and capability composition."""

from __future__ import annotations

from collections.abc import Callable

from craftreport.application.ports import Facade
from craftreport.application.service_values import Missing, ServiceUnavailable
from craftreport.composition.settings import ConfiguredCapability, configure
from craftreport.contracts import (
    EffectDisposition,
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    ResultReadback,
    StageState,
)
from craftreport.data.values import SnapshotRef
from craftreport.reporting.ports import PreparationResult, ReportFailure
from craftreport.runtime.ports import AppOperationCaller, RunPreparer
from craftreport.runtime.values import (
    BindingSpec,
    CancellationObservation,
    EffectObservation,
    PreparationIssue,
    PreparedRunInputs,
    RunPins,
    TargetIdentity,
)
from craftreport_gridcraft.app_values import AppSettings
from craftreport_gridcraft.capability import GridCraftFactory
from craftreport_gridcraft.codecs import (
    apply_codec,
    observation_fact_codec,
    parameter_digest,
    prepare_payload,
    settings_codec,
    validation_scope_identifier,
)
from craftreport_gridcraft.facts import AppFacts
from craftreport_gridcraft.operations import AppOperations
from craftreport_gridcraft.values import (
    ApplyRequest,
    AppObservationFact,
)


class AppRunPreparer(RunPreparer):
    def __init__(
        self,
        facade: Facade,
        principal: Principal,
        decode_preparation: Callable[[JsonObject], PreparationResult | ReportFailure],
    ) -> None:
        self._facade = facade
        self._principal = principal
        self._decode = decode_preparation

    async def prepare(
        self, binding: BindingSpec, snapshot: SnapshotRef
    ) -> PreparedRunInputs | PreparationIssue | ServiceUnavailable:
        payload = prepare_payload(binding, snapshot)
        key = f"prepare:{binding.binding_id}:{snapshot.content_digest}"
        envelope = InvocationEnvelope(
            OperationKey("reports.prepare", "1"),
            payload,
            correlation_id=key,
            retry_key=key,
        )
        receipt = await self._facade.invoke(self._principal, envelope)
        if not isinstance(receipt, Receipt):
            return ServiceUnavailable("reports.prepare")
        if receipt.state is not ReceiptState.COMPLETE or receipt.result_ref is None:
            return PreparationIssue("preparation_unavailable")
        if not isinstance(
            res := await self._facade.read_result(self._principal, receipt.operation_id),
            ResultReadback,
        ):
            return ServiceUnavailable("reports.prepare")
        decoded = self._decode(res.value)
        if not isinstance(decoded, PreparationResult):
            return PreparationIssue("preparation_mismatch")
        prep = decoded.prepared
        stage = next(
            (
                s
                for s in receipt.stages
                if s.stage == "prepared" and s.state is StageState.PASSED and s.evidence
            ),
            None,
        )
        if (
            prep.snapshot,
            prep.definition,
            prep.template,
            prep.theme,
            prep.pack.version_pin,
            prep.resolved_parameters,
        ) != (
            snapshot,
            binding.definition,
            binding.template,
            binding.theme,
            binding.pack,
            binding.resolved_parameters,
        ) or stage is None:
            return PreparationIssue("preparation_mismatch")
        return PreparedRunInputs(
            prep.snapshot,
            prep.definition,
            prep.template,
            prep.theme,
            prep.pack.version_pin,
            prep.resolved_parameters,
            parameter_digest(prep.resolved_parameters),
            validation_scope_identifier(prep.release_policy),
            receipt.operation_id,
            receipt.result_ref,
            prep.content_digest,
        )


class GridCraftOperationCaller(AppOperationCaller):
    def __init__(self, facade: Facade, principal: Principal, facts: AppFacts) -> None:
        self._facade = facade
        self._principal = principal
        self._facts = facts
        self._runs: dict[str, RunPins] = {}

    async def start(self, run: RunPins) -> str | ServiceUnavailable:
        ptr = self._facts.read_current_index(run.target.document_id)
        payload = apply_codec().encode(ApplyRequest(run, ptr.revision if ptr is not None else 1))
        envelope = InvocationEnvelope(
            OperationKey("gridcraft.apply", "1"),
            payload,
            correlation_id=f"apply:{run.run_id}",
            retry_key=f"apply:{run.run_id}",
        )
        receipt = await self._facade.invoke(self._principal, envelope)
        if not isinstance(receipt, Receipt):
            return ServiceUnavailable("gridcraft.apply")
        self._runs[receipt.operation_id] = run
        return receipt.operation_id

    async def inspect(self, operation_id: str) -> EffectObservation | Missing | ServiceUnavailable:
        receipt = await self._facade.inspect(self._principal, operation_id)
        if not isinstance(receipt, Receipt):
            return Missing()
        res = (
            await self._facade.read_result(self._principal, operation_id)
            if receipt.state is ReceiptState.COMPLETE
            else None
        )
        fact = (
            observation_fact_codec().decode(res.value) if isinstance(res, ResultReadback) else None
        )
        f = fact if isinstance(fact, AppObservationFact) else None
        run = f.run if f else self._runs.get(operation_id)
        complete = f is not None and f.outcome == "complete"
        eff = {
            "complete": EffectDisposition.APPLIED,
            "partial": EffectDisposition.PARTIAL,
            "ambiguous": EffectDisposition.UNKNOWN,
        }.get(f.outcome if f else "", EffectDisposition.NONE)
        tgt = run.target if run else TargetIdentity("gridcraft", "browser", "session", "doc")
        return EffectObservation(
            run_id=run.run_id if run else "",
            target=tgt,
            binding_generation=run.binding_generation if run else 1,
            effect=eff,
            stages=receipt.stages,
            evidence=receipt.evidence if complete else (),
            verified_complete=complete,
        )

    async def cancel(
        self, operation_id: str
    ) -> CancellationObservation | Missing | ServiceUnavailable:
        receipt = await self._facade.inspect(self._principal, operation_id)
        if not isinstance(receipt, Receipt):
            return Missing()
        if receipt.state in (ReceiptState.COMPLETE, ReceiptState.FAILED):
            obs = await self.inspect(operation_id)
            eff = obs.effect if isinstance(obs, EffectObservation) else EffectDisposition.NONE
            return CancellationObservation(
                operation_id,
                "already_terminal",
                eff,
                obs if isinstance(obs, EffectObservation) else None,
            )
        return CancellationObservation(operation_id, "cancelled", EffectDisposition.NONE)


def configure_gridcraft(services: AppOperations, settings: AppSettings) -> ConfiguredCapability:
    def adapt(loaded: object) -> GridCraftFactory:
        if isinstance(loaded, GridCraftFactory):
            return loaded
        if callable(loaded):
            res = loaded()
            if isinstance(res, GridCraftFactory):
                return res
        raise ValueError("Unexpected gridcraft capability factory")

    return configure(
        "craftreport-gridcraft",
        "gridcraft.web_reports",
        adapt,
        services,
        settings_codec(),
        settings_codec().encode(settings),
    )
