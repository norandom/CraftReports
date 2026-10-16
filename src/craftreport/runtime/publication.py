"""Publication results and exact decision observations through the shared facade."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from craftreport.application import ports
from craftreport.application.registry import Codec
from craftreport.contracts import (
    Availability,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    OutcomeProposal,
    Principal,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.data.ports import SnapshotFinalizer
from craftreport.data.requirements import BindingIssue, InputRequirements
from craftreport.data.values import Snapshot, SnapshotRef
from craftreport.runtime.ports import PublicationDecisionReader, SnapshotQueries

type PublicationStatus = Literal["accepted", "existing", "stale_version", "version_conflict"]


@dataclass(frozen=True, slots=True)
class PublicationFinding:
    check_id: Literal["schema_and_values", "provenance_shape"]
    status: Literal["passed"] = "passed"
    scope: Literal["supplied_publication"] = "supplied_publication"


FINDINGS = (PublicationFinding("schema_and_values"), PublicationFinding("provenance_shape"))


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    reference: SnapshotRef
    datasets: int
    fields: int
    rows: int
    cells: int
    metrics: int
    metric_points: int
    received_at: datetime
    accepted_at: datetime


def summarize(snapshot: Snapshot) -> SnapshotSummary:
    return SnapshotSummary(
        SnapshotRef(snapshot.feed_id, snapshot.producer_version, snapshot.content_digest),
        len(snapshot.datasets),
        sum(len(d.fields) for d in snapshot.datasets),
        sum(len(d.rows) for d in snapshot.datasets),
        sum(len(r) for d in snapshot.datasets for r in d.rows),
        len(snapshot.metrics),
        sum(len(m.values) for m in snapshot.metrics),
        snapshot.received_at,
        snapshot.accepted_at,
    )


@dataclass(frozen=True, slots=True)
class PublicationResult:
    status: PublicationStatus
    requested: SnapshotRef
    retained: SnapshotRef | None
    latest_accepted: SnapshotRef
    content_availability: Availability | None
    summary: SnapshotSummary | None
    validation_findings: tuple[PublicationFinding, ...] = FINDINGS

    def __post_init__(self) -> None:
        if (
            self.validation_findings != FINDINGS
            or self.latest_accepted.feed_id != self.requested.feed_id
        ):
            raise ValueError("Invalid publication findings/feed")
        if self.status == "stale_version":
            if (
                self.retained is not None
                or self.content_availability is not None
                or self.summary is not None
                or self.requested.producer_version >= self.latest_accepted.producer_version
            ):
                raise ValueError("Invalid stale result")
            return
        if (
            self.retained is None
            or self.retained.feed_id != self.requested.feed_id
            or self.retained.producer_version > self.latest_accepted.producer_version
        ):
            raise ValueError("Invalid retained result")
        if self.content_availability not in (Availability.AVAILABLE, Availability.MISSING):
            raise ValueError("Invalid content availability")
        if self.status == "version_conflict":
            if (
                self.retained.producer_version != self.requested.producer_version
                or self.retained == self.requested
                or self.summary is not None
            ):
                raise ValueError("Invalid conflict result")
            return
        if self.status not in ("accepted", "existing") or self.retained != self.requested:
            raise ValueError("Invalid publication status/identity")
        self._acceptance()

    def _acceptance(self) -> None:
        if (self.content_availability is Availability.AVAILABLE) != (self.summary is not None):
            raise ValueError("Availability and summary differ")
        if self.summary is not None and self.summary.reference != self.retained:
            raise ValueError("Summary identity differs")
        if self.status == "accepted" and (
            self.retained != self.latest_accepted or self.summary is None
        ):
            raise ValueError("Accepted result requires available latest content")


@dataclass(frozen=True, slots=True)
class LatestRequest:
    feed_id: str
    requirements: InputRequirements | None = None

    def __post_init__(self) -> None:
        if not self.feed_id.strip():
            raise ValueError("Feed identity required")


@dataclass(frozen=True, slots=True)
class LatestSelection:
    latest_accepted: SnapshotRef
    content_availability: Availability
    selection_status: Literal["not_requested", "selected", "none"]
    highest_complete: SnapshotRef | None
    latest_issues: tuple[BindingIssue, ...]


@dataclass(frozen=True, slots=True)
class PublicationDecision:
    result: PublicationResult
    effect: EffectDisposition
    completion_pins: tuple[ExpectedVersion, ...]
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        accepted = self.result.status == "accepted"
        scopes = (
            {"publication_decided", "snapshot_persisted"} if accepted else {"publication_decided"}
        )
        if (
            len(self.completion_pins) != 1
            or self.completion_pins[0].resource
            != ResourceRef("feed", self.result.requested.feed_id)
            or self.effect
            is not (EffectDisposition.APPLIED if accepted else EffectDisposition.NONE)
            or len(self.evidence) != len(scopes)
            or {ref.scope for ref in self.evidence} != scopes
            or len({ref.operation_id for ref in self.evidence}) != 1
            or any(
                ref.operation != OperationKey("snapshot.publish", "1")
                or ref.resource_versions != self.completion_pins
                for ref in self.evidence
            )
        ):
            raise ValueError("Publication decision evidence differs")


@dataclass(frozen=True, slots=True)
class PublicationOperations:
    decisions: PublicationDecisionReader
    queries: Callable[[Principal], SnapshotQueries]
    finalize: SnapshotFinalizer
    snapshot_codec: Codec[Snapshot]
    clock: Callable[[], datetime]

    async def publish(
        self, request: JsonObject, context: ports.CommandContext
    ) -> OutcomeProposal[PublicationResult]:
        current = await context.guard.assert_current()
        if not isinstance(current, ports.GuardCurrent):
            return OutcomeProposal(None, EffectDisposition.NONE, (), ())
        snapshot, _ = self.finalize(request, self.clock(), self.clock())
        change: JsonObject = {
            "operation_id": context.operation_id,
            "snapshot": self.snapshot_codec.encode(snapshot),
        }
        observed = await context.services.effects.apply(
            ResourceRef("feed", snapshot.feed_id), change, context.guard
        )
        if isinstance(observed, (ports.GuardLost, ports.VersionConflict)):
            return OutcomeProposal(None, EffectDisposition.NONE, (), ())
        decision = await self.decisions.read_decision(context.operation_id)
        if not isinstance(decision, PublicationDecision):
            return OutcomeProposal(None, EffectDisposition.UNKNOWN, (), ())
        if decision.result.requested != SnapshotRef(
            snapshot.feed_id, snapshot.producer_version, snapshot.content_digest
        ):
            return OutcomeProposal(None, EffectDisposition.UNKNOWN, (), ())
        if any(ref.operation_id != context.operation_id for ref in decision.evidence):
            return OutcomeProposal(None, EffectDisposition.UNKNOWN, (), ())
        if isinstance(observed, ports.ResourceEffect) and (
            observed.effect,
            observed.versions,
            observed.evidence,
        ) != (decision.effect, decision.completion_pins, decision.evidence):
            return OutcomeProposal(None, EffectDisposition.UNKNOWN, (), ())
        return OutcomeProposal(
            decision.result,
            decision.effect,
            (
                StageResult(
                    "publication_decided",
                    StageState.PASSED,
                    "publication_decided",
                    decision.evidence,
                ),
            ),
            decision.evidence,
        )

    async def read(
        self, request: SnapshotRef, context: ports.ReadContext
    ) -> Snapshot | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        return await self.queries(context.principal).read(request)

    async def latest(
        self, request: LatestRequest, context: ports.ReadContext
    ) -> LatestSelection | ports.Missing | ports.ServiceUnavailable:
        return await self.queries(context.principal).latest(request)
