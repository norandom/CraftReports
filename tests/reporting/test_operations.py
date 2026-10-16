"""Report orchestration with explicit external port fixtures; no target effects."""

import asyncio
from dataclasses import replace
from typing import cast

import pytest
from test_prepare import definition as definition
from test_prepare import pack as pack
from test_prepare import snapshot as snapshot
from test_themes import support as support

from craftreport.adapters import report_codecs as c
from craftreport.application.ports import (
    CapabilityResolver,
    CommandContext,
    CommandServices,
    EvidenceReader,
    ReadContext,
    ReadServices,
    ResourceEffects,
)
from craftreport.application.service_values import (
    GuardCurrent,
    Missing,
    ResourceSnapshot,
    ServiceUnavailable,
)
from craftreport.composition.reporting import is_compatible
from craftreport.contracts import EvidenceRef, ExpectedVersion, Principal, ResourceRef, StageState
from craftreport.data.values import Snapshot, SnapshotRef
from craftreport.policies.values import CheckId, CheckStatus
from craftreport.reporting.definitions import ParameterValue
from craftreport.reporting.operations import ReportOperations, report_resources
from craftreport.reporting.ports import (
    EmptyRequest,
    PackFailure,
    PackSelection,
    PackSummary,
    PreparationFact,
    PreparationResult,
    PrepareRequest,
    ReportFailure,
    ValidateRequest,
    ValidationResult,
)
from craftreport.reporting.prepared import ResolvedPack
from craftreport.themes.resolve import CapabilityStatus

PRINCIPAL = Principal("test", "reader", frozenset({"source", "artifact"}))
SELECTION = PackSelection("public", "pack", "1")


class Boundary:
    def __init__(self, pack: ResolvedPack, snapshot: Snapshot) -> None:
        pin = replace(pack.template, content_digest=c.definition_identifier(pack.definition))
        self.pack = replace(pack, template=pin, definition_pin=pin)
        self.snapshot: Snapshot | Missing | ServiceUnavailable = snapshot
        self.facts: list[PreparationFact] = []
        self.fail_fact = 0
        self.denied = False
        self.observations = {
            resource: ExpectedVersion(
                resource, snapshot.content_digest if resource.kind == "snapshot" else "e" * 64
            )
            for resource in report_resources(self.request(snapshot))
        }

    def request(self, snapshot: Snapshot) -> PrepareRequest:
        return PrepareRequest(
            pack=SELECTION,
            snapshot=SnapshotRef(
                snapshot.feed_id, snapshot.producer_version, snapshot.content_digest
            ),
        )

    def discover(self, principal: Principal) -> tuple[PackSummary, ...]:
        return () if self.denied else (PackSummary(SELECTION.identity, "1", "Public", "artifact"),)

    def read(self, selection: PackSelection, principal: Principal) -> ResolvedPack | PackFailure:
        return PackFailure() if self.denied else self.pack

    async def record(self, fact: PreparationFact) -> EvidenceRef | ServiceUnavailable:
        self.facts.append(fact)
        if len(self.facts) == self.fail_fact:
            return ServiceUnavailable("facts")
        return EvidenceRef(
            f"fact-{len(self.facts)}",
            fact.stage,
            fact.operation_id,
            fact.operation,
            fact.resource_versions,
            "f" * 64,
        )


class Reads:
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def read(self, ref: SnapshotRef) -> Snapshot | Missing | ServiceUnavailable:
        return self.boundary.snapshot


class Resources:
    def __init__(self, boundary: Boundary) -> None:
        self.boundary = boundary

    async def read(self, resource: ResourceRef) -> ResourceSnapshot | Missing:
        version = self.boundary.observations.get(resource)
        return Missing() if version is None else ResourceSnapshot(version, {})


class Guard:
    authoritative_versions: tuple[ExpectedVersion, ...] = ()

    async def assert_current(self) -> GuardCurrent:
        return GuardCurrent()


def setup(boundary: Boundary) -> tuple[ReportOperations, CommandContext, ReadContext]:
    handlers = ReportOperations(
        boundary,
        lambda principal: Reads(boundary),
        boundary,
        c.definition_identifier,
        c.prepared_identifier,
        c.validation_scope_identifier,
        is_compatible,
    )
    reads = ReadServices(
        cast(EvidenceReader, None), cast(CapabilityResolver, None), Resources(boundary)
    )
    return (
        handlers,
        CommandContext(
            "op", PRINCIPAL, Guard(), CommandServices(reads, cast(ResourceEffects, None))
        ),
        ReadContext("query", PRINCIPAL, reads),
    )


def test_real_compiler_and_two_facts(pack: ResolvedPack, snapshot: Snapshot) -> None:
    boundary = Boundary(pack, snapshot)
    handlers, context, query = setup(boundary)
    validated = asyncio.run(handlers.validate(ValidateRequest(pack=SELECTION), query))
    assert isinstance(validated, ValidationResult)
    result = asyncio.run(handlers.prepare(boundary.request(snapshot), context))
    assert isinstance(result.result, PreparationResult)
    assert result.result.prepared.tables[0].rows[0][0] == "=SUM(A1)"
    assert result.result.quality.draft_eligible
    assert [fact.stage for fact in boundary.facts] == ["prepared", "quality_evaluated"]
    assert all(len(fact.resource_versions) == 3 for fact in boundary.facts)
    assert all(stage.state is StageState.PASSED for stage in result.stages)
    assert len(result.evidence) == 2
    assert all(
        f.scope.resource_versions == boundary.facts[0].resource_versions
        for f in result.result.quality.findings
    )


def test_validated_blocked_preserves_content(pack: ResolvedPack, snapshot: Snapshot) -> None:
    policy = replace(pack.definition.release_policy, required_checks=(CheckId.LAYOUT_FIT,))
    boundary = Boundary(
        replace(pack, definition=replace(pack.definition, release_policy=policy)), snapshot
    )
    handlers, context, _ = setup(boundary)
    result = asyncio.run(
        handlers.prepare(
            replace(boundary.request(snapshot), requested_designation="validated"), context
        )
    )
    assert isinstance(result.result, PreparationResult)
    assert (
        result.result.quality.draft_eligible
        and not result.result.quality.validated_release_eligible
    )
    assert result.stages[1].state is StageState.FAILED
    assert result.diagnostics[0].code == "release_blocked"
    assert result.result.quality.findings[3].status is CheckStatus.UNEVALUATED


@pytest.mark.parametrize("unavailable", [False, True])
def test_snapshot_absence_is_not_empty_success(
    pack: ResolvedPack, snapshot: Snapshot, unavailable: bool
) -> None:
    boundary = Boundary(pack, snapshot)
    boundary.snapshot = ServiceUnavailable("snapshot") if unavailable else Missing()
    handlers, context, _ = setup(boundary)
    result = asyncio.run(handlers.prepare(boundary.request(snapshot), context))
    assert isinstance(result.result, ReportFailure)
    assert result.result.code == "input_unavailable"
    assert result.result.recovery == ("retry" if unavailable else "correct_request")
    assert result.stages[0].state is StageState.FAILED
    assert not boundary.facts


def test_scoped_reader_denial(pack: ResolvedPack, snapshot: Snapshot) -> None:
    boundary = Boundary(pack, snapshot)
    boundary.denied = True
    handlers, _, query = setup(boundary)
    assert asyncio.run(handlers.discover(EmptyRequest(), query)).packs == ()
    invalid = asyncio.run(handlers.validate(ValidateRequest(pack=SELECTION), query))
    assert isinstance(invalid, ReportFailure) and invalid.code == "pack_missing"
    rejected = asyncio.run(handlers.eligibility(boundary.request(snapshot), PRINCIPAL))
    assert rejected is not None and rejected.code == "pack_missing"
    assert not boundary.facts


@pytest.mark.parametrize("failure_index", [1, 2])
def test_fact_unavailability_withholds_completion(
    pack: ResolvedPack, snapshot: Snapshot, failure_index: int
) -> None:
    boundary = Boundary(pack, snapshot)
    boundary.fail_fact = failure_index
    handlers, context, _ = setup(boundary)
    result = asyncio.run(handlers.prepare(boundary.request(snapshot), context))
    assert not all(stage.state is StageState.PASSED for stage in result.stages)
    assert len(result.evidence) == failure_index - 1
    assert result.diagnostics[0].code == "service_unavailable"


def test_exact_registration(pack: ResolvedPack, snapshot: Snapshot) -> None:
    from craftreport.reporting.registration import (
        ReportCodecs,
        report_descriptors,
        report_operations,
    )

    codecs = ReportCodecs(
        c.validation_request_codec(),
        c.validation_result_codec(),
        c.discovery_request_codec(),
        c.discovery_result_codec(),
        c.preparation_request_codec(),
        c.preparation_result_codec(),
    )
    handlers, _, _ = setup(Boundary(pack, snapshot))
    operations = report_operations(handlers, codecs)
    assert tuple(op.descriptor for op in operations) == report_descriptors(codecs)
    assert [op.descriptor.key.name for op in operations] == [
        "reports.validate_definition",
        "reports.discover_packs",
        "reports.prepare",
    ]
    assert [len(op.descriptor.resources) for op in operations] == [2, 0, 3]
    assert operations[2].descriptor.limits.max_output_bytes == 8388608
    assert operations[2].descriptor.starts_business_work
    assert not operations[2].descriptor.changes_business_state
    assert operations[2].descriptor.completion_evidence.required_stages == (
        "prepared",
        "quality_evaluated",
    )


@pytest.mark.parametrize("problem", ["missing_pack_pin", "snapshot_pin", "snapshot_identity"])
def test_independent_readback_full_pins(
    pack: ResolvedPack, snapshot: Snapshot, problem: str
) -> None:
    boundary = Boundary(pack, snapshot)
    resources = report_resources(boundary.request(snapshot))
    if problem == "missing_pack_pin":
        del boundary.observations[resources[0]]
    elif problem == "snapshot_pin":
        boundary.observations[resources[-1]] = ExpectedVersion(resources[-1], "b" * 64)
    else:
        boundary.snapshot = replace(snapshot, producer_version=2)
    handlers, context, _ = setup(boundary)
    result = asyncio.run(handlers.prepare(boundary.request(snapshot), context))
    assert isinstance(result.result, ReportFailure) and result.result.code == "input_unavailable"
    assert not boundary.facts and not result.evidence


@pytest.mark.parametrize("problem", ["parameter", "definition", "binding"])
def test_semantic_failure_retains_detail_but_safe_diagnostic(
    pack: ResolvedPack, snapshot: Snapshot, problem: str
) -> None:
    boundary = Boundary(pack, snapshot)
    request = boundary.request(snapshot)
    if problem == "parameter":
        request = replace(request, parameters=(ParameterValue("private-name", 1),))
    elif problem == "definition":
        request = replace(request, definition=replace(pack.definition, title="Changed"))
    else:
        boundary.snapshot = replace(snapshot, datasets=())
    handlers, context, _ = setup(boundary)
    result = asyncio.run(handlers.prepare(request, context))
    assert isinstance(result.result, ReportFailure)
    assert (
        result.result.code
        == {
            "parameter": "invalid_parameter",
            "definition": "invalid_definition",
            "binding": "incomplete_binding",
        }[problem]
    )
    assert result.result.issues and not boundary.facts
    assert result.diagnostics[0].location == (
        {"parameter": "parameters", "definition": "definition", "binding": "snapshot"}[problem],
    )
    assert "private-name" not in str(result.diagnostics)


@pytest.mark.parametrize("problem", ["untested", "unsupported", "malformed", "unused_optional"])
def test_theme_eligibility_uses_real_checker(
    pack: ResolvedPack, snapshot: Snapshot, support: tuple[CapabilityStatus, ...], problem: str
) -> None:
    selected = support[0]
    if problem in ("untested", "unsupported"):
        selected = replace(selected, status="untested" if problem == "untested" else "unsupported")
    elif problem == "malformed":
        selected = replace(selected, capability=replace(selected.capability, version="invalid!"))
    else:
        support = tuple(
            replace(
                item,
                properties=tuple(
                    (name, "unsupported" if name == "format.date_pattern" else status)
                    for name, status in item.properties
                ),
            )
            for item in support
        )
        selected = support[0]
    boundary = Boundary(pack, snapshot)
    handlers, _, _ = setup(boundary)
    request = replace(boundary.request(snapshot), target_support=(selected, *support[1:]))
    result = asyncio.run(handlers.eligibility(request, PRINCIPAL))
    if problem == "unused_optional":
        assert result is None
    else:
        assert result is not None
        assert result.code == (
            "incompatible_version" if problem == "malformed" else f"{problem}_mapping"
        )
        assert result.location == ("target_support",)
    assert not boundary.facts


def test_second_snapshot_revalidates_and_changes_identity(
    pack: ResolvedPack, snapshot: Snapshot
) -> None:
    boundary = Boundary(pack, snapshot)
    handlers, context, _ = setup(boundary)
    first = asyncio.run(handlers.prepare(boundary.request(snapshot), context))
    second_snapshot = replace(
        snapshot,
        producer_version=2,
        content_digest="b" * 64,
        datasets=(replace(snapshot.datasets[0], rows=()),),
    )
    second_boundary = Boundary(pack, second_snapshot)
    handlers, context, _ = setup(second_boundary)
    second = asyncio.run(handlers.prepare(second_boundary.request(second_snapshot), context))
    assert isinstance(first.result, PreparationResult) and isinstance(
        second.result, PreparationResult
    )
    assert first.result.prepared.content_digest != second.result.prepared.content_digest
    assert not second.result.prepared.tables[0].rows
    assert first.result.prepared.definition == second.result.prepared.definition
