"""App operations: discover, open_report, apply, verify, and inspect."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, cast

from craftreport.application.ports import CommandContext, Facade, ReadContext
from craftreport.application.registry import (
    BoundOperation,
    Codec,
    CommandBehavior,
    OperationBinding,
    QueryBehavior,
)
from craftreport.application.service_values import DiagnosticPolicy, ResourceSnapshot
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    EvidencePolicy,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OperationLimits,
    OutcomeProposal,
    ReceiptState,
    RecoveryDisposition,
    ResourceRef,
    ResultReadback,
    StageResult,
    StageState,
)
from craftreport.contracts.values import freeze_object
from craftreport.policies.values import CheckId, CheckScope, QualityEvaluation
from craftreport.reporting.ports import PreparationResult, ReportFailure
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins
from craftreport_gridcraft.artifacts import verify_scratch_artifact
from craftreport_gridcraft.browser import BrowserDriver
from craftreport_gridcraft.codecs import (
    apply_codec,
    discover_request_codec,
    inspect_request_codec,
    issue_codec,
    mapping_pins_match,
    observation_fact_codec,
    open_report_codec,
    prepared_content_matches,
    recovery_codec,
    support_descriptor,
    verify_codec,
)
from craftreport_gridcraft.facts import AppFacts
from craftreport_gridcraft.values import (
    PROFILE,
    AppInspectRequest,
    AppIntentFact,
    AppIssue,
    ApplyRequest,
    AppObservationFact,
    AppSettings,
    BrowserTarget,
    CurrentObservationPointer,
    DiscoverRequest,
    MappingPlan,
    OpenReportRequest,
    OwnedLayout,
    SavedCandidate,
    TargetObservation,
    TargetRecovery,
    VerifyRequest,
)
from craftreport_gridcraft.workbook import validate_mapping

_LIMITS = OperationLimits(max_input_bytes=65536, max_output_bytes=262144)


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class AppResultCodec[T]:
    success: Codec[T]
    issue: Codec[AppIssue]

    def decode(self, value: JsonObject) -> T | AppIssue:
        return (
            self.issue.decode(value)
            if "code" in value and "stage" in value
            else self.success.decode(value)
        )

    def encode(self, value: T | AppIssue) -> JsonObject:
        return (
            self.issue.encode(value) if isinstance(value, AppIssue) else self.success.encode(value)
        )

    def schema(self) -> JsonObject:
        return self.success.schema()


class SimpleJsonCodec:
    limits = _LIMITS

    def decode(self, value: JsonObject) -> JsonObject:
        return value

    encode = decode

    def schema(self) -> JsonObject:
        return {}


def app_codecs() -> tuple[Any, ...]:
    obs_res = AppResultCodec(observation_fact_codec(), issue_codec())
    return (
        discover_request_codec(),
        SimpleJsonCodec(),
        open_report_codec(),
        obs_res,
        apply_codec(),
        obs_res,
        verify_codec(),
        obs_res,
        inspect_request_codec(),
        AppResultCodec(recovery_codec(), issue_codec()),
    )


def app_diagnostic_policy() -> DiagnosticPolicy:
    retries = {
        ("bootstrap", "unavailable"),
        ("observe", "unavailable"),
        ("mutate", "unavailable"),
        ("verify", "unavailable"),
        ("admit", "unavailable"),
    }
    corrects = {
        ("bootstrap", "conflict"),
        ("bootstrap", "untested"),
        ("observe", "conflict"),
        ("mutate", "conflict"),
        ("verify", "conflict"),
        ("admit", "conflict"),
        ("admit", "untested"),
        ("admit", "unsupported"),
        ("admit", "limit"),
    }
    return DiagnosticPolicy(
        frozenset(
            {(s, c, RecoveryDisposition.RETRY) for s, c in retries}
            | {(s, c, RecoveryDisposition.CORRECT_REQUEST) for s, c in corrects}
        ),
        frozenset(
            {
                (),
                ("run",),
                ("target",),
                ("document_marker",),
                ("cells",),
                ("outside",),
                ("save_lane",),
                ("preparation",),
            }
        ),
    )


def _prep_matches(prep: PreparedReport, qual: QualityEvaluation, run: RunPins) -> bool:
    return (
        prepared_content_matches(prep)
        and mapping_pins_match(prep, qual, run)
        and (
            prep.snapshot,
            prep.definition,
            prep.template,
            prep.theme,
            prep.pack.version_pin,
            prep.content_digest,
        )
        == (run.snapshot, run.definition, run.template, run.theme, run.pack, run.prepared_digest)
    )


async def _verify_prep_receipt(facade: Facade, principal: Any, run: RunPins) -> Any | AppIssue:
    r = await facade.inspect(principal, run.prepared_operation_id)
    if (
        not r
        or getattr(r, "state", None) is not ReceiptState.COMPLETE
        or getattr(r, "operation", None) != OperationKey("reports.prepare", "1")
        or getattr(r, "result_ref", None) != run.prepared_result_ref
        or getattr(r, "result_availability", None) is not Availability.AVAILABLE
    ):
        return AppIssue("conflict", ("preparation", "receipt"), stage="admit")
    return r


async def verify_preparation_scope(
    context: CommandContext,
    run: RunPins,
    facade: Facade,
    decode_result: Callable[[JsonObject], PreparationResult | ReportFailure],
) -> tuple[PreparedReport, QualityEvaluation, CheckScope] | AppIssue:
    if isinstance(receipt := await _verify_prep_receipt(facade, context.principal, run), AppIssue):
        return receipt
    if not isinstance(
        res := await facade.read_result(context.principal, run.prepared_operation_id),
        ResultReadback,
    ):
        return AppIssue("unavailable", ("preparation", "result"), stage="admit")
    decoded = decode_result(res.value)
    if not isinstance(decoded, PreparationResult) or not _prep_matches(
        decoded.prepared, decoded.quality, run
    ):
        return AppIssue("conflict", ("preparation", "pins"), stage="admit")
    prep, qual = decoded.prepared, decoded.quality
    p = f"{run.pack.identity}@{run.pack.version}"
    expected = (
        ResourceRef("report_pack_source", p),
        ResourceRef("report_pack_artifact_scope", p),
        ResourceRef("snapshot", f"{run.snapshot.feed_id}:{run.snapshot.producer_version}"),
    )
    if set(receipt.resources) != set(expected) or len(receipt.resources) != 3:
        return AppIssue("conflict", ("preparation", "resources"), stage="admit")
    if not (
        stage := next(
            (
                s
                for s in receipt.stages
                if s.stage == "prepared" and s.state is StageState.PASSED and s.evidence
            ),
            None,
        )
    ):
        return AppIssue("conflict", ("preparation", "stage"), stage="admit")
    orig = stage.evidence[0].resource_versions
    snap = next((v for v in orig if v.resource.kind == "snapshot"), None)
    if (
        any(e.resource_versions != orig for e in stage.evidence)
        or len(orig) != 3
        or {v.resource for v in orig} != set(expected)
        or not snap
        or snap.version != run.snapshot.content_digest
    ):
        return AppIssue("conflict", ("preparation", "source_pins"), stage="admit")
    statuses = await context.services.reads.evidence.inspect(receipt.evidence)
    if any(
        s.availability is not Availability.AVAILABLE or s.verification is not StageState.PASSED
        for s in statuses
    ):
        return AppIssue("unavailable", ("preparation", "evidence"), stage="admit")
    scope = CheckScope(prep.content_digest, orig, None, None, run.validation_scope)
    tgt = {CheckId.DEFINITION, CheckId.BINDINGS, CheckId.SEMANTIC_RESOLUTION}
    if any(f.check_id in tgt and f.scope != scope for f in qual.findings):
        return AppIssue("conflict", ("preparation", "finding_scope"), stage="admit")
    return prep, qual, scope


async def _completion_versions(
    context: CommandContext, doc_ref: ResourceRef
) -> tuple[ExpectedVersion, ...]:
    s = await context.services.reads.resources.read(doc_ref)
    ver = s.version if isinstance(s, ResourceSnapshot) else ExpectedVersion(doc_ref, "1")
    return tuple(
        ver if p.resource.kind == "gridcraft_document" else p
        for p in context.guard.authoritative_versions
    )


class AppOperations:
    def __init__(
        self,
        settings: AppSettings,
        driver: BrowserDriver,
        facts: AppFacts,
        facade: Facade,
        decode_preparation: Callable[[JsonObject], PreparationResult | ReportFailure],
        page: Any | None = None,
    ) -> None:
        self._settings = settings
        self._driver = driver
        self._facts = facts
        self._facade = facade
        self._decode_prep = decode_preparation
        self._page = page

    def set_page(self, page: Any | None) -> None:
        self._page = page

    async def discover(self, request: DiscoverRequest, context: ReadContext) -> JsonObject:
        return freeze_object(
            {
                "schema_version": "1",
                "deployment_id": self._settings.deployment_id,
                "context_id": self._settings.context_id,
                "origin": self._settings.origin,
                "profile_pin": cast(JsonObject, asdict(PROFILE.pin)),
                "support": support_descriptor(),
                "operations": {
                    "gridcraft.discover": "supported",
                    "gridcraft.open_report": "supported",
                    "gridcraft.apply": "supported",
                    "gridcraft.verify": "supported",
                    "gridcraft.inspect": "supported",
                    "gridcraft.export": "unavailable",
                },
            }
        )

    async def inspect(self, request: AppInspectRequest, context: ReadContext) -> TargetRecovery:
        return self._facts.inspect_target_recovery(request.document_id)

    async def _record_success(
        self,
        ctx: CommandContext,
        op: str,
        stage: str,
        detail: str,
        target: BrowserTarget,
        run: RunPins,
        rev: int,
        obs: TargetObservation | None = None,
        cand: SavedCandidate | None = None,
    ) -> OutcomeProposal[AppObservationFact | AppIssue]:
        now_ts = _now()
        fact = self._facts.record_observation(
            AppObservationFact(
                ctx.operation_id,
                op,
                self._settings.deployment_id,
                target,
                run,
                rev,
                "complete",
                obs,
                cand,
                created_at=now_ts,
            )
        )
        self._facts.update_current_index(
            CurrentObservationPointer(
                target.identity.document_id,
                ctx.operation_id,
                target,
                run,
                rev,
                "complete",
                fact.content_digest,
                now_ts,
            )
        )
        ver = await _completion_versions(
            ctx, ResourceRef("gridcraft_document", target.identity.document_id)
        )
        ev = EvidenceRef(
            f"evidence-{ctx.operation_id}",
            "app_observation",
            ctx.operation_id,
            OperationKey(op, "1"),
            ver,
            fact.content_digest,
        )
        return OutcomeProposal(
            fact,
            EffectDisposition.APPLIED,
            (StageResult(stage, StageState.PASSED, detail, (ev,)),),
            (ev,),
        )

    async def _prep_and_plan(
        self, ctx: CommandContext, run: RunPins, target: BrowserTarget
    ) -> tuple[MappingPlan, OwnedLayout] | AppIssue:
        if isinstance(
            chk := await verify_preparation_scope(ctx, run, self._facade, self._decode_prep),
            AppIssue,
        ):
            return chk
        layout = OwnedLayout(target, run)
        return (
            plan
            if isinstance(plan := validate_mapping(chk[0], chk[1], layout), AppIssue)
            else (plan, layout)
        )

    async def open_report(
        self, request: OpenReportRequest, context: CommandContext
    ) -> OutcomeProposal[AppObservationFact | AppIssue]:
        if self._facts.read_current_index(request.target.identity.document_id) is not None:
            return OutcomeProposal(
                AppIssue("conflict", ("document",), "bootstrap"), EffectDisposition.NONE, (), ()
            )
        if isinstance(
            res := await self._prep_and_plan(context, request.run, request.target), AppIssue
        ):
            return OutcomeProposal(res, EffectDisposition.NONE, (), ())
        plan, _ = res
        self._facts.record_intent(
            AppIntentFact(
                context.operation_id,
                "gridcraft.open_report",
                self._settings.deployment_id,
                request.target,
                request.run,
                1,
                "apply",
                _now(),
            )
        )
        if self._page is None:
            return OutcomeProposal(
                AppIssue("unavailable", ("browser",), "bootstrap"), EffectDisposition.NONE, (), ()
            )
        if isinstance(
            target_res := await self._driver.open_report(
                plan, self._page, request.target.document_marker
            ),
            AppIssue,
        ):
            return OutcomeProposal(target_res, EffectDisposition.NONE, (), ())
        if isinstance(
            obs := await self._driver.observe(
                request.target, request.run, plan, self._page, revision=1
            ),
            AppIssue,
        ):
            return OutcomeProposal(obs, EffectDisposition.NONE, (), ())
        return await self._record_success(
            context,
            "gridcraft.open_report",
            "bootstrap",
            "bootstrapped",
            request.target,
            request.run,
            1,
            obs=obs,
        )

    def _handle_apply_issue(
        self, context: CommandContext, ptr: CurrentObservationPointer, run: RunPins, res: AppIssue
    ) -> OutcomeProposal[AppObservationFact | AppIssue]:
        if res.effect == "none":
            return OutcomeProposal(res, EffectDisposition.NONE, (), ())
        eff = EffectDisposition.PARTIAL if res.effect == "partial" else EffectDisposition.UNKNOWN
        self._facts.record_observation(
            AppObservationFact(
                context.operation_id,
                "gridcraft.apply",
                self._settings.deployment_id,
                ptr.target,
                run,
                ptr.revision,
                "partial" if res.effect == "partial" else "ambiguous",
                reason_code=res.code,
                created_at=_now(),
            )
        )
        return OutcomeProposal(
            res, eff, (StageResult("apply", StageState.FAILED, res.code, ()),), ()
        )

    async def apply(
        self, request: ApplyRequest, context: CommandContext
    ) -> OutcomeProposal[AppObservationFact | AppIssue]:
        ptr = self._facts.read_current_index(request.run.target.document_id)
        if ptr is None or ptr.revision != request.expected_version or ptr.outcome != "complete":
            return OutcomeProposal(
                AppIssue("conflict", ("revision",), "mutate"), EffectDisposition.NONE, (), ()
            )
        if isinstance(res := await self._prep_and_plan(context, request.run, ptr.target), AppIssue):
            return OutcomeProposal(res, EffectDisposition.NONE, (), ())
        plan, _ = res
        if (
            prev := self._facts.read_observation(ptr.operation_id)
        ) is None or prev.observation is None:
            return OutcomeProposal(
                AppIssue("unavailable", ("before",), "mutate"), EffectDisposition.NONE, (), ()
            )
        self._facts.record_intent(
            AppIntentFact(
                context.operation_id,
                "gridcraft.apply",
                self._settings.deployment_id,
                ptr.target,
                request.run,
                request.expected_version + 1,
                "apply",
                _now(),
            )
        )
        if self._page is None:
            return OutcomeProposal(
                AppIssue("unavailable", ("browser",), "mutate"), EffectDisposition.NONE, (), ()
            )
        if isinstance(
            applied_res := await self._driver.apply(
                plan, request.run, prev.observation, self._page
            ),
            AppIssue,
        ):
            return self._handle_apply_issue(context, ptr, request.run, applied_res)
        return await self._record_success(
            context,
            "gridcraft.apply",
            "apply",
            "applied",
            ptr.target,
            request.run,
            request.expected_version + 1,
            obs=applied_res,
        )

    async def verify(
        self, request: VerifyRequest, context: CommandContext
    ) -> OutcomeProposal[AppObservationFact | AppIssue]:
        ptr = self._facts.read_current_index(request.run.target.document_id)
        if ptr is None or ptr.revision != request.expected_version:
            return OutcomeProposal(
                AppIssue("conflict", ("revision",), "inspect"), EffectDisposition.NONE, (), ()
            )
        if isinstance(res := await self._prep_and_plan(context, request.run, ptr.target), AppIssue):
            return OutcomeProposal(res, EffectDisposition.NONE, (), ())
        plan, _ = res
        self._facts.record_intent(
            AppIntentFact(
                context.operation_id,
                "gridcraft.verify",
                self._settings.deployment_id,
                ptr.target,
                request.run,
                request.expected_version,
                "inspect",
                _now(),
            )
        )
        if self._page is None:
            return OutcomeProposal(
                AppIssue("unavailable", ("browser",), "inspect"), EffectDisposition.NONE, (), ()
            )
        if isinstance(
            obs := await self._driver.observe(
                ptr.target, request.run, plan, self._page, revision=request.expected_version
            ),
            AppIssue,
        ):
            return OutcomeProposal(obs, EffectDisposition.NONE, (), ())
        if isinstance(
            cand_res := await self._driver.capture_inspection_save(
                self._page,
                ptr.target,
                request.run,
                self._facts.tmp_dir,
                f"scratch-{context.operation_id}",
            ),
            AppIssue,
        ):
            return OutcomeProposal(cand_res, EffectDisposition.NONE, (), ())
        candidate, data = cand_res
        if isinstance(
            inspected := verify_scratch_artifact(
                data, ptr.target.document_marker, request.run.run_id
            ),
            AppIssue,
        ):
            return OutcomeProposal(inspected, EffectDisposition.NONE, (), ())
        return await self._record_success(
            context,
            "gridcraft.verify",
            "verify",
            "verified",
            ptr.target,
            request.run,
            request.expected_version,
            obs=obs,
            cand=candidate,
        )


def app_descriptors(codecs: Any = None) -> tuple[OperationDescriptor, ...]:
    d_req, d_res, o_req, o_res, a_req, a_res, v_req, v_res, i_req, i_res = codecs or app_codecs()
    packs = ("report_pack_source", "report_pack_artifact_scope")
    cmd_srv = ("journal", "guard", "resources", "effects", "evidence", "results")
    specs = (
        ("gridcraft.discover", OperationKind.QUERY, d_req, d_res, False, (), ("resources",), ()),
        (
            "gridcraft.open_report",
            OperationKind.COMMAND,
            o_req,
            o_res,
            True,
            (*packs, "snapshot", "gridcraft_document"),
            cmd_srv,
            ("bootstrap",),
        ),
        (
            "gridcraft.apply",
            OperationKind.COMMAND,
            a_req,
            a_res,
            True,
            ("run", *packs, "snapshot", "gridcraft_document"),
            cmd_srv,
            ("apply",),
        ),
        (
            "gridcraft.verify",
            OperationKind.COMMAND,
            v_req,
            v_res,
            True,
            (*packs, "snapshot", "gridcraft_document"),
            cmd_srv,
            ("verify",),
        ),
        (
            "gridcraft.inspect",
            OperationKind.QUERY,
            i_req,
            i_res,
            False,
            ("gridcraft_document",),
            ("resources",),
            (),
        ),
    )
    return tuple(
        OperationDescriptor(
            OperationKey(k, "1"),
            kind,
            req.schema(),
            res.schema(),
            mut,
            False,
            r,
            (),
            srv,
            _LIMITS,
            EvidencePolicy(ev),
        )
        for k, kind, req, res, mut, r, srv, ev in specs
    )


def _pack_res(run: RunPins, doc_id: str, *extra: ResourceRef) -> tuple[ResourceRef, ...]:
    p = f"{run.pack.identity}@{run.pack.version}"
    return (
        *extra,
        ResourceRef("report_pack_source", p),
        ResourceRef("report_pack_artifact_scope", p),
        ResourceRef("snapshot", f"{run.snapshot.feed_id}:{run.snapshot.producer_version}"),
        ResourceRef("gridcraft_document", doc_id),
    )


def app_operations(handlers: AppOperations, codecs: Any = None) -> tuple[BoundOperation, ...]:
    c = codecs or app_codecs()
    discover_d, open_d, apply_d, verify_d, inspect_d = app_descriptors(c)
    d_req, d_res, o_req, o_res, a_req, a_res, v_req, v_res, i_req, i_res = c
    policy = app_diagnostic_policy()
    return (
        OperationBinding(
            discover_d, d_req, d_res, QueryBehavior(handlers.discover), lambda _r: (), policy
        ).bind(),
        OperationBinding(
            open_d,
            o_req,
            o_res,
            CommandBehavior(handlers.open_report),
            lambda r: _pack_res(r.run, r.target.identity.document_id),
            policy,
        ).bind(),
        OperationBinding(
            apply_d,
            a_req,
            a_res,
            CommandBehavior(handlers.apply),
            lambda r: _pack_res(r.run, r.run.target.document_id, ResourceRef("run", r.run.run_id)),
            policy,
        ).bind(),
        OperationBinding(
            verify_d,
            v_req,
            v_res,
            CommandBehavior(handlers.verify),
            lambda r: _pack_res(r.run, r.run.target.document_id),
            policy,
        ).bind(),
        OperationBinding(
            inspect_d,
            i_req,
            i_res,
            QueryBehavior(handlers.inspect),
            lambda r: (ResourceRef("gridcraft_document", r.document_id),),
            policy,
        ).bind(),
    )
