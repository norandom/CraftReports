"""Closed report registrations and their operator-owned diagnostic policy."""

from dataclasses import dataclass
from typing import get_args

from craftreport.application.registry import (
    BoundOperation,
    Codec,
    CommandBehavior,
    OperationBinding,
    QueryBehavior,
)
from craftreport.application.service_values import DiagnosticPolicy
from craftreport.contracts import (
    EvidencePolicy,
    OperationDescriptor,
    OperationKey,
    OperationKind,
    OperationLimits,
)
from craftreport.reporting.operations import CORRECT, RETRY, ReportOperations, report_resources
from craftreport.reporting.ports import (
    DiscoveryResult,
    EmptyRequest,
    PreparationResult,
    PrepareRequest,
    ReportFailure,
    ValidateRequest,
    ValidationResult,
)
from craftreport.themes.resolve import ThemeCode


@dataclass(frozen=True, slots=True)
class ReportCodecs:
    validation_request: Codec[ValidateRequest]
    validation_result: Codec[ValidationResult | ReportFailure]
    discovery_request: Codec[EmptyRequest]
    discovery_result: Codec[DiscoveryResult]
    preparation_request: Codec[PrepareRequest]
    preparation_result: Codec[PreparationResult | ReportFailure]


def report_diagnostic_policy() -> DiagnosticPolicy:
    codes = (
        "invalid_definition",
        "invalid_parameter",
        "incomplete_binding",
        "pack_missing",
        "input_unavailable",
        *get_args(ThemeCode.__value__),
    )
    allowed = {
        (stage, code, RETRY if code == "compatibility_unavailable" else CORRECT)
        for stage in ("prepared", "quality_evaluated")
        for code in codes
    }
    allowed.update(
        {
            ("prepared", "input_unavailable", RETRY),
            ("quality_evaluated", "input_unavailable", RETRY),
            ("prepared", "service_unavailable", RETRY),
            ("quality_evaluated", "release_blocked", CORRECT),
        }
    )
    locations = frozenset(
        {
            (),
            *(
                (name,)
                for name in (
                    "definition",
                    "parameters",
                    "snapshot",
                    "selection",
                    "theme",
                    "overrides",
                    "target_support",
                )
            ),
        }
    )
    return DiagnosticPolicy(frozenset(allowed), locations)


def _descriptor[Q, R](
    name: str,
    request: Codec[Q],
    result: Codec[R],
    resources: tuple[str, ...],
    command: bool = False,
) -> OperationDescriptor:
    services = (
        ("journal", "guard", "resources", "effects", "evidence", "results", "report_packs")
        if command
        else ("resources", "report_packs")
    )
    return OperationDescriptor(
        OperationKey(name, "1"),
        OperationKind.COMMAND if command else OperationKind.QUERY,
        request.schema(),
        result.schema(),
        command,
        False,
        resources,
        (),
        services,
        OperationLimits(65536, 32, 8388608 if command else 1048576),
        EvidencePolicy(("prepared", "quality_evaluated") if command else ()),
    )


def report_descriptors(codecs: ReportCodecs) -> tuple[OperationDescriptor, ...]:
    packs = ("report_pack_source", "report_pack_artifact_scope")
    return (
        _descriptor(
            "reports.validate_definition",
            codecs.validation_request,
            codecs.validation_result,
            packs,
        ),
        _descriptor(
            "reports.discover_packs", codecs.discovery_request, codecs.discovery_result, ()
        ),
        _descriptor(
            "reports.prepare",
            codecs.preparation_request,
            codecs.preparation_result,
            (*packs, "snapshot"),
            True,
        ),
    )


def report_operations(
    handlers: ReportOperations, codecs: ReportCodecs
) -> tuple[BoundOperation, ...]:
    validate, discover, prepare = report_descriptors(codecs)
    policy = report_diagnostic_policy()
    return (
        OperationBinding(
            validate,
            codecs.validation_request,
            codecs.validation_result,
            QueryBehavior(handlers.validate),
            report_resources,
            policy,
        ).bind(),
        OperationBinding(
            discover,
            codecs.discovery_request,
            codecs.discovery_result,
            QueryBehavior(handlers.discover),
            lambda request: (),
            policy,
        ).bind(),
        OperationBinding(
            prepare,
            codecs.preparation_request,
            codecs.preparation_result,
            CommandBehavior(handlers.prepare, handlers.eligibility),
            report_resources,
            policy,
        ).bind(),
    )
