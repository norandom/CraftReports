"""Immutable JSON values; external handles stay with their owning adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Requirement = Annotated[str, StringConstraints(pattern=r"^[1-8]\.[1-9][0-9]*$")]
Positive = Annotated[float, Field(gt=0, allow_inf_nan=False, strict=True)]
State = Literal["pending", "passed", "failed", "blocked", "unresolved", "unexecuted"]


def absolute_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError("path must be absolute")
    return path


def browser_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.hostname in ("0.0.0.0", "::")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("origin must be a reachable HTTP(S) origin without credentials")
    _ = parsed.port
    return origin.rstrip("/")


AbsolutePath = Annotated[Path, AfterValidator(absolute_path)]
Origin = Annotated[Text, AfterValidator(browser_origin)]


class Value(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TargetIdentity(Value):
    run_id: UUID
    context_id: UUID
    page_id: UUID
    generation: Annotated[int, Field(gt=0, strict=True)]
    origin: Origin
    mode: Literal["browser-wasm"]
    build_sha256: Sha256
    fixture_id: UUID
    fixture_marker: Text
    artifact_sha256: Sha256

    @model_validator(mode="after")
    def distinct_associations(self) -> TargetIdentity:
        if len({self.run_id, self.context_id, self.page_id, self.fixture_id}) != 4:
            raise ValueError("run, context, page and fixture identities must be distinct")
        return self


class ArtifactIdentity(Value):
    artifact_id: UUID
    destination: AbsolutePath
    size: Annotated[int, Field(gt=0, strict=True)]
    sha256: Sha256
    target: TargetIdentity
    route: Literal["download"]

    @model_validator(mode="after")
    def distinct_output_association(self) -> ArtifactIdentity:
        selected = self.target
        if self.artifact_id in {
            selected.run_id,
            selected.context_id,
            selected.page_id,
            selected.fixture_id,
        }:
            raise ValueError(
                "output artifact identity must be distinct from target role identities"
            )
        return self


class StageFinding(Value):
    stage: Text
    requirements: Annotated[tuple[Requirement, ...], Field(min_length=1)]
    status: State
    expected: tuple[Text, ...] = ()
    observed: tuple[Text, ...] = ()
    evidence_refs: tuple[Text, ...] = ()


class CheckSet(Value):
    findings: tuple[StageFinding, ...] = ()

    @property
    def passed(self) -> bool:
        return bool(self.findings) and all(item.status == "passed" for item in self.findings)


class ArtifactCheckSet(CheckSet):
    """Inspector-observed identities from the exact retained bounded bytes."""

    artifact_sha256: Sha256
    artifact_size: Annotated[int, Field(gt=0, le=4_000_000, strict=True)]
    fixture_sha256: Sha256
    phase: Literal["before", "after"]


class InspectedArtifact(Value):
    """Journey-owned inspected edited bytes passed between separate adapters."""

    artifact: ArtifactIdentity
    inspection: ArtifactCheckSet
    fixture_sha256: Sha256
    phase: Literal["after"] = "after"

    @model_validator(mode="after")
    def successful_inspection(self) -> InspectedArtifact:
        if (
            not self.inspection.passed
            or self.inspection.artifact_sha256 != self.artifact.sha256
            or self.inspection.artifact_size != self.artifact.size
            or self.inspection.fixture_sha256 != self.fixture_sha256
            or self.inspection.phase != "after"
            or any(
                finding.stage != "byte-inspection" or finding.expected[-1:] != ("after",)
                for finding in self.inspection.findings
            )
        ):
            raise ValueError("reopen requires passed edited-byte inspection")
        return self


class ActionReceipt(Value):
    dispatch_id: UUID
    target: TargetIdentity
    action: Literal["open", "edit", "copy", "save", "reopen"]
    start: Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]
    deadline: Positive
    status: Literal["pending", "observed", "unresolved"] = "pending"
    observation_refs: tuple[Text, ...] = ()

    @model_validator(mode="after")
    def validate_effect(self) -> ActionReceipt:
        if self.deadline <= self.start:
            raise ValueError("deadline must follow monotonic start")
        if self.status == "observed" and not self.observation_refs:
            raise ValueError("observed receipt requires effect observation references")
        return self


class CellCheck(Value):
    address: Annotated[str, StringConstraints(pattern=r"^[A-Z]+[1-9][0-9]*$")]
    value: str


class ObservationSpec(Value):
    target: TargetIdentity
    cells: Annotated[tuple[CellCheck, ...], Field(min_length=1)]
    checkpoint: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]
    chart_identity: Text
    visual_profile: Text

    @model_validator(mode="after")
    def distinct_cells_and_marker(self) -> ObservationSpec:
        cells = {cell.address: cell.value for cell in self.cells}
        if len(cells) != len(self.cells) or cells.get("D1") != self.target.fixture_marker:
            raise ValueError("observation requires distinct cells and matching fixture marker")
        return self


class Succeeded[T: Value](Value):
    status: Literal["succeeded"] = "succeeded"
    payload: T


class Rejected(Value):
    status: Literal["rejected"] = "rejected"
    finding: StageFinding

    @model_validator(mode="after")
    def validate_rejection(self) -> Rejected:
        if self.finding.status not in ("failed", "blocked", "unresolved"):
            raise ValueError("rejection requires a non-passing finding")
        return self


type Outcome[T: Value] = Annotated[Succeeded[T] | Rejected, Field(discriminator="status")]


class ContentIdentity(Value):
    path: Text
    sha256: Sha256


ResourceKind = Literal["deployment", "process", "driver", "browser", "context", "decode-context"]
CloseState = Literal[
    "pending", "sdk-closed", "graceful", "forced", "failed", "timed-out", "unresolved", "unexecuted"
]
SDK_IDENTITY = "playwright==1.64.0"
SDK_LIMITATION = "playwright_internal_force_unobservable"


class CleanupFinding(Value):
    resource_id: UUID
    owner_run: UUID
    identity: Text
    status: CloseState
    exit_status: Annotated[int, Field(strict=True)] | None = None
    native_pid: Annotated[int, Field(strict=True, gt=0)] | None = None
    container_ids: tuple[Text, ...] = ()
    network_ids: tuple[Text, ...] = ()
    survivors: tuple[Text, ...] = ()
    final_video_state: Literal["not-required", "finalized", "unfinished"]
    resource_kind: ResourceKind | None = None
    acquisition_id: UUID | None = None
    close_id: UUID | None = None
    mechanism: str | None = None
    started: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    deadline: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    finished: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    acquisition_state: Literal["partial", "acquired", "failed", "unsettled"] = "partial"
    acquisition_task_state: Literal[
        "not-started", "pending", "succeeded", "failed", "cancelled"
    ] = "pending"
    close_task_state: Literal["not-started", "pending", "succeeded", "failed", "cancelled"] = (
        "not-started"
    )
    requested_force: bool = False
    observed_force: bool = False
    unexpected_disconnect: bool = False
    sdk_identity: Literal["playwright==1.64.0"] | None = None
    declared_limitations: tuple[Literal["playwright_internal_force_unobservable"], ...] = ()

    @property
    def accepted(self) -> bool:
        if (
            self.requested_force
            or self.observed_force
            or self.unexpected_disconnect
            or self.survivors
            or self.acquisition_state != "acquired"
            or not self.acquisition_id
            or not self.close_id
            or self.final_video_state == "unfinished"
            or self.started is None
            or self.deadline is None
            or self.finished is None
            or not self.started <= self.finished <= self.deadline
        ):
            return False
        if self.resource_kind in ("driver", "browser", "context", "decode-context"):
            return (
                self.status == "sdk-closed"
                and self.acquisition_task_state == "succeeded"
                and self.close_task_state == "succeeded"
                and self.mechanism == "public-close"
                and self.sdk_identity == SDK_IDENTITY
                and self.declared_limitations == (SDK_LIMITATION,)
            )
        return (
            self.resource_kind in ("process", "deployment")
            and self.status == "graceful"
            and self.exit_status == 0
            and self.mechanism == "observed-exit"
            and (self.resource_kind != "process" or self.native_pid is not None)
            and (self.resource_kind != "deployment" or bool(self.container_ids))
        )


MANDATORY_STAGES = frozenset(
    (
        "readiness",
        "visible-mutation",
        "persistence",
        "byte-inspection",
        "browser-reopen",
        "evidence",
        "cleanup",
    )
)


class RunResult(Value):
    schema_version: Literal[1, 2] = 2
    lifecycle_contract: Literal["historical-v1", "resource-specific-v2"] = "resource-specific-v2"
    sdk_identity: Literal["playwright==1.64.0"] | None = "playwright==1.64.0"
    declared_limitations: tuple[Literal["playwright_internal_force_unobservable"], ...] = (
        SDK_LIMITATION,
    )
    scope: Literal["synthetic-browser-reference-roundtrip"] = (
        "synthetic-browser-reference-roundtrip"
    )
    run_id: UUID
    source_revision: Text
    dirty_content: tuple[ContentIdentity, ...] = ()
    dependency_identities: Annotated[tuple[Text, ...], Field(min_length=1)]
    app_sha256: Sha256 | None
    profile_id: Literal["chromium-download-fallback"]
    findings: tuple[StageFinding, ...]
    cleanup: tuple[CleanupFinding, ...]
    verdict: Literal["VERIFIED", "FAILED", "BLOCKED", "UNRESOLVED"]
    predecessor_run: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def historical_schema(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        values = cast(dict[str, object], data)
        if values.get("schema_version") == 1:
            return values | {
                "lifecycle_contract": "historical-v1",
                "sdk_identity": None,
                "declared_limitations": (),
            }
        return values

    @model_validator(mode="after")
    def truthful_completion(self) -> RunResult:
        if self.schema_version == 2 and (
            self.lifecycle_contract != "resource-specific-v2"
            or self.sdk_identity != SDK_IDENTITY
            or self.declared_limitations != (SDK_LIMITATION,)
            or (
                self.verdict == "VERIFIED"
                and any(
                    len({getattr(c, attribute) for c in self.cleanup}) != len(self.cleanup)
                    for attribute in ("resource_id", "acquisition_id", "close_id")
                )
            )
        ):
            raise ValueError("lifecycle declaration must match schema and pinned SDK")
        if self.predecessor_run == self.run_id:
            raise ValueError("recovery requires a distinct run")
        if any(item.owner_run != self.run_id for item in self.cleanup):
            raise ValueError("cleanup must belong to this run")
        if self.verdict == "VERIFIED":
            if (
                self.app_sha256 is None
                or not CheckSet(findings=self.findings).passed
                or not MANDATORY_STAGES.issubset(item.stage for item in self.findings)
                or not self.cleanup
                or not MANDATORY_STAGES.issubset(
                    item.stage for item in self.findings if item.evidence_refs
                )
                or not any(item.final_video_state == "finalized" for item in self.cleanup)
            ):
                raise ValueError(
                    "verified requires all mandatory stages and acquired-resource cleanup"
                )
            if any(
                (not item.accepted if self.schema_version == 2 else item.status != "graceful")
                or item.survivors
                or item.exit_status not in (None, 0)
                or item.final_video_state == "unfinished"
                for item in self.cleanup
            ):
                raise ValueError("verified requires graceful cleanup with finalized evidence")
        return self
