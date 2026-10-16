"""Guarded report orchestration; target effects remain outside preparation."""

from collections.abc import Callable
from dataclasses import dataclass

from craftreport.application.ports import CommandContext, ReadContext
from craftreport.application.service_values import (
    GuardCurrent,
    Missing,
    ResourceSnapshot,
    ServiceUnavailable,
    VersionConflict,
)
from craftreport.contracts import (
    Diagnostic,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    OperationKey,
    OutcomeProposal,
    Principal,
    RecoveryDisposition,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.data.ports import SnapshotReader
from craftreport.data.values import SnapshotRef
from craftreport.policies.evaluate import evaluate
from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
    ReleasePolicy,
)
from craftreport.reporting.definitions import DefinitionError, ReportDefinition
from craftreport.reporting.ports import (
    DiscoveryResult,
    EmptyRequest,
    PackFailure,
    PackReader,
    PreparationCheck,
    PreparationDecision,
    PreparationFact,
    PreparationFactWriter,
    PreparationResult,
    PrepareRequest,
    ReportCode,
    ReportFailure,
    ReportIssue,
    ValidateRequest,
    ValidationResult,
)
from craftreport.reporting.prepare import (
    prepare,
    requirements_for,
    resolve_parameters,
    validate_template,
)
from craftreport.reporting.prepared import PreparationFailure, PreparedReport, ResolvedPack
from craftreport.themes.resolve import CompatibilityCheck, ThemeFailure, resolve_theme
from craftreport.themes.values import ResolvedTheme

PREPARE = OperationKey("reports.prepare", "1")
OWNED_CHECKS = (CheckId.DEFINITION, CheckId.BINDINGS, CheckId.SEMANTIC_RESOLUTION)
CORRECT = RecoveryDisposition.CORRECT_REQUEST
RETRY = RecoveryDisposition.RETRY


def report_resources(request: ValidateRequest) -> tuple[ResourceRef, ...]:
    identity = f"{request.pack.identity}@{request.pack.version}"
    packs = tuple(
        ResourceRef(kind, identity) for kind in ("report_pack_source", "report_pack_artifact_scope")
    )
    if isinstance(request, PrepareRequest):
        return (
            *packs,
            ResourceRef(
                "snapshot", f"{request.snapshot.feed_id}:{request.snapshot.producer_version}"
            ),
        )
    return packs


def failure(
    code: ReportCode, issues: tuple[ReportIssue, ...] = (), *, retry: bool = False
) -> ReportFailure:
    return ReportFailure.from_issues("prepared", code, RETRY if retry else CORRECT, issues)


def diagnostic(value: ReportFailure) -> Diagnostic:
    location = {
        "invalid_definition": "definition",
        "invalid_parameter": "parameters",
        "incomplete_binding": "snapshot",
        "input_unavailable": "snapshot",
        "pack_missing": "selection",
    }.get(value.code, "theme")
    if value.issues and isinstance(value.issues[0], ThemeFailure):
        location = {"support": "target_support", "overrides": "overrides"}.get(
            str(value.issues[0].location[0]), "theme"
        )
    return Diagnostic(PREPARE, value.stage, value.code, value.recovery, (location,))


def _failed(value: ReportFailure) -> OutcomeProposal[PreparationResult | ReportFailure]:
    return OutcomeProposal(
        value,
        EffectDisposition.NONE,
        (
            StageResult("prepared", StageState.FAILED, value.code),
            StageResult("quality_evaluated", StageState.PENDING, "not_executed"),
        ),
        (),
        (diagnostic(value),),
    )


def _unavailable(
    evidence: tuple[EvidenceRef, ...] = (),
) -> OutcomeProposal[PreparationResult | ReportFailure]:
    stages = (
        StageResult(
            "prepared",
            StageState.PASSED if evidence else StageState.FAILED,
            "verified" if evidence else "service_unavailable",
            evidence,
        ),
        StageResult("quality_evaluated", StageState.PENDING, "not_executed"),
    )
    return OutcomeProposal(
        None,
        EffectDisposition.NONE,
        stages,
        evidence,
        (Diagnostic(PREPARE, "prepared", "service_unavailable", RETRY),),
    )


@dataclass(frozen=True, slots=True)
class ReportOperations:
    packs: PackReader
    snapshots: Callable[[Principal], SnapshotReader]
    facts: PreparationFactWriter
    identify_definition: Callable[[ReportDefinition], str]
    identify_prepared: Callable[[PreparedReport], str]
    identify_scope: Callable[[ReleasePolicy], str]
    compatibility: CompatibilityCheck

    def _selection(
        self, request: ValidateRequest, principal: Principal
    ) -> tuple[ResolvedPack, ResolvedTheme] | ReportFailure:
        pack = self.packs.read(request.pack, principal)
        if isinstance(pack, PackFailure):
            return failure("pack_missing")
        theme = resolve_theme(
            pack.theme, request.overrides, request.target_support, is_compatible=self.compatibility
        )
        if isinstance(theme, ThemeFailure):
            return failure(theme.code, (theme,), retry=theme.code == "compatibility_unavailable")
        return pack, theme

    async def eligibility(self, request: PrepareRequest, principal: Principal) -> Diagnostic | None:
        selected = self._selection(request, principal)
        if isinstance(selected, ReportFailure):
            if selected.code == "compatibility_unavailable":
                return Diagnostic(PREPARE, "prepared", "service_unavailable", RETRY)
            return diagnostic(selected)
        return None

    def _validate(
        self, request: ValidateRequest, pack: ResolvedPack
    ) -> ValidationResult | ReportFailure:
        try:
            definition = validate_template(
                request.definition or pack.definition, pack.template, self.identify_definition
            )
        except DefinitionError as error:
            return failure("invalid_definition", (error.issue,))
        try:
            parameters = resolve_parameters(definition, request.parameters)
        except DefinitionError as error:
            return failure("invalid_parameter", (error.issue,))
        try:
            requirements = requirements_for(definition, parameters)
        except DefinitionError as error:
            return failure("invalid_definition", (error.issue,))
        return ValidationResult(
            requirements,
            parameters,
            pack.definition_pin,
            pack.template,
            pack.theme.version_pin,
            pack.pin,
            definition.required_capabilities,
        )

    async def validate(
        self, request: ValidateRequest, context: ReadContext
    ) -> ValidationResult | ReportFailure:
        selected = self._selection(request, context.principal)
        return (
            selected
            if isinstance(selected, ReportFailure)
            else self._validate(request, selected[0])
        )

    async def discover(self, request: EmptyRequest, context: ReadContext) -> DiscoveryResult:
        return DiscoveryResult(self.packs.discover(context.principal))

    async def _pins(
        self, request: PrepareRequest, context: CommandContext
    ) -> tuple[ExpectedVersion, ...] | ReportFailure:
        versions: list[ExpectedVersion] = []
        for resource in report_resources(request):
            value = await context.services.reads.resources.read(resource)
            if not isinstance(value, ResourceSnapshot):
                return failure("input_unavailable", retry=isinstance(value, ServiceUnavailable))
            if value.version.resource != resource:
                return failure("input_unavailable")
            versions.append(value.version)
        if versions[-1].version != request.snapshot.content_digest:
            return failure("input_unavailable")
        return tuple(versions)

    async def prepare(
        self, request: PrepareRequest, context: CommandContext
    ) -> OutcomeProposal[PreparationResult | ReportFailure]:
        selected = self._selection(request, context.principal)
        if isinstance(selected, ReportFailure):
            return _failed(selected)
        pack, theme = selected
        validated = self._validate(request, pack)
        if isinstance(validated, ReportFailure):
            return _failed(validated)
        snapshot = await self.snapshots(context.principal).read(request.snapshot)
        if isinstance(snapshot, (Missing, VersionConflict, ServiceUnavailable)):
            return _failed(
                failure("input_unavailable", retry=isinstance(snapshot, ServiceUnavailable))
            )
        if (
            SnapshotRef(snapshot.feed_id, snapshot.producer_version, snapshot.content_digest)
            != request.snapshot
        ):
            return _failed(failure("input_unavailable"))
        versions = await self._pins(request, context)
        if isinstance(versions, ReportFailure):
            return _failed(versions)
        prepared = prepare(
            pack.definition, request.parameters, snapshot, pack, theme, self.identify_prepared
        )
        if isinstance(prepared, PreparationFailure):
            return _failed(failure(prepared.code, prepared.issues))
        if not isinstance(await context.guard.assert_current(), GuardCurrent):
            return _unavailable()
        return await self._retain(request, context, prepared, versions)

    async def _retain(
        self,
        request: PrepareRequest,
        context: CommandContext,
        prepared: PreparedReport,
        versions: tuple[ExpectedVersion, ...],
    ) -> OutcomeProposal[PreparationResult | ReportFailure]:
        scope = CheckScope(
            prepared.content_digest,
            versions,
            None,
            None,
            self.identify_scope(prepared.release_policy),
        )
        checks = tuple(
            PreparationCheck(check, CheckStatus.PASSED, CheckOrigin.CRAFTREPORT, "verified")
            for check in OWNED_CHECKS
        )
        fact = PreparationFact(
            context.operation_id,
            PREPARE,
            versions,
            "1",
            "prepared",
            prepared.content_digest,
            scope.validation_scope_digest,
            checks,
            None,
        )
        reference = await self.facts.record(fact)
        if isinstance(reference, ServiceUnavailable):
            return _unavailable()
        _check_reference(reference, fact)
        observations = tuple(
            CheckObservation(c.check_id, scope, c.status, (reference,), c.origin, c.reason_code)
            for c in checks
        )
        quality = evaluate(
            scope,
            prepared.release_policy,
            observations + _external(prepared, scope, reference),
            preparation_scope=scope,
        )
        decision = PreparationDecision(
            request.requested_designation,
            quality.draft_eligible,
            quality.validated_release_eligible,
            quality.blocking_checks,
        )
        quality_fact = PreparationFact(
            context.operation_id,
            PREPARE,
            versions,
            "1",
            "quality_evaluated",
            prepared.content_digest,
            scope.validation_scope_digest,
            tuple(
                PreparationCheck(f.check_id, f.status, f.origin, f.reason_code)
                for f in quality.findings
            ),
            decision,
        )
        retained = await self.facts.record(quality_fact)
        if isinstance(retained, ServiceUnavailable):
            return _unavailable((reference,))
        _check_reference(retained, quality_fact)
        blocked = (
            request.requested_designation == "validated" and not quality.validated_release_eligible
        )
        stages = (
            StageResult("prepared", StageState.PASSED, "verified", (reference,)),
            StageResult(
                "quality_evaluated",
                StageState.FAILED if blocked else StageState.PASSED,
                "release_blocked" if blocked else "verified",
                (retained,),
            ),
        )
        diagnostics = (
            (Diagnostic(PREPARE, "quality_evaluated", "release_blocked", CORRECT),)
            if blocked
            else ()
        )
        return OutcomeProposal(
            PreparationResult(prepared, quality),
            EffectDisposition.NONE,
            stages,
            (reference, retained),
            diagnostics,
        )


def _check_reference(reference: EvidenceRef, fact: PreparationFact) -> None:
    if (
        reference.operation_id,
        reference.operation,
        reference.resource_versions,
        reference.scope,
    ) != (
        fact.operation_id,
        fact.operation,
        fact.resource_versions,
        fact.stage,
    ) or not reference.content_digest:
        raise ValueError("Preparation fact reference mismatch")


def _external(
    prepared: PreparedReport, scope: CheckScope, reference: EvidenceRef
) -> tuple[CheckObservation, ...]:
    observations: list[CheckObservation] = []
    if prepared.metric_provenance:
        observations.append(
            CheckObservation(
                CheckId.METRIC_METHODOLOGY,
                scope,
                CheckStatus.UNEVALUATED,
                (reference,),
                CheckOrigin.EXTERNAL,
                "externally_supplied",
            )
        )
    if prepared.compliance_statement is not None:
        observations.append(
            CheckObservation(
                CheckId.COMPLIANCE_STATEMENT,
                scope,
                CheckStatus.UNEVALUATED,
                prepared.compliance_statement.evidence,
                CheckOrigin.EXTERNAL,
                "externally_supplied",
            )
        )
    return tuple(observations)
