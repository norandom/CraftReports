"""Evidence reduction and atomic publication; no application interaction."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, field_serializer

from .config import RunConfig
from .contracts import (
    MANDATORY_STAGES,
    ActionReceipt,
    CleanupFinding,
    ContentIdentity,
    InspectedArtifact,
    Rejected,
    RunResult,
    StageFinding,
    State,
    Succeeded,
    Text,
    Value,
)
from .deployment import DeploymentLease
from .evidence import Diagnostic, complete_webm, verify_loaded
from .fixture import FixtureExpectation
from .interactions import BrowserObservation
from .packet_provenance import verify_provenance

if TYPE_CHECKING:
    from .journey import ResourceToken, RoundTripResult


class PacketInputs(Value):
    config: RunConfig
    deployment: DeploymentLease
    fixture: FixtureExpectation
    source_revision: Text
    source_content: tuple[ContentIdentity, ...]
    dependencies: tuple[Text, ...]
    scope: Literal["synthetic-browser-reference-roundtrip"] = (
        "synthetic-browser-reference-roundtrip"
    )

    @field_serializer("fixture")
    def serialize_fixture(self, fixture: FixtureExpectation) -> dict[str, object]:
        serialized: dict[str, object] = fixture.model_dump(mode="json", exclude={"before", "after"})
        serialized.update(
            {
                phase: {key: cell.model_dump(mode="json") for key, cell in cells.items()}
                for phase, cells in (("before", fixture.before), ("after", fixture.after))
            }
        )
        return serialized


class RecordedDiagnostics(BaseModel):
    model_config = ConfigDict(extra="ignore")
    events: tuple[Diagnostic, ...]


class RecordedInteractions(Value):
    receipts: tuple[ActionReceipt, ...]
    observations: tuple[BrowserObservation, ...]


def interaction_records(result: RoundTripResult) -> tuple[RecordedInteractions, ...]:
    return tuple(
        RecordedInteractions.model_validate_json(
            (Path(r.payload.screenshot).parent / "interactions.json").read_bytes()
        )
        for r in result.readiness
        if isinstance(r, Succeeded)
    )


def finding(stage: str, status: State, *refs: str) -> StageFinding:
    return StageFinding(
        stage=stage, requirements=("5.1", "5.6", "7.4", "7.5"), status=status, evidence_refs=refs
    )


def reduce_stages(result: RoundTripResult) -> tuple[StageFinding, ...]:
    """Derive stage truth from retained adapter observations, never dispatch alone."""
    stages: list[StageFinding] = []
    for ready in result.readiness:
        stages.append(
            ready.finding
            if isinstance(ready, Rejected)
            else finding("readiness", "passed", ready.payload.screenshot)
        )
    edits = tuple(r for r in result.receipts if r.action == "edit")
    if edits:
        stages.append(
            finding(
                "visible-mutation",
                result.primary.finding.status
                if result.primary and result.primary.finding.stage == "edit"
                else "passed"
                if all(r.status == "observed" for r in edits)
                and len(result.checks) >= 2
                and all(c.passed for c in result.checks[:2])
                else "failed",
                *(ref for r in edits for ref in r.observation_refs),
            )
        )
    for name, outcome in (
        ("persistence", result.artifact),
        ("byte-inspection", result.inspection),
        ("browser-reopen", result.reopened),
    ):
        if isinstance(outcome, Rejected):
            stages.append(outcome.finding)
        elif outcome:
            stages.append(finding(name, "passed", "roundtrip.json"))
    if isinstance(result.inspection, Succeeded):
        stages.extend(result.inspection.payload.findings)
    for checks in result.checks:
        stages.extend(checks.findings)
    if result.primary:
        stages.append(result.primary.finding)
    stages.extend(
        StageFinding(
            stage=event.stage,
            requirements=("5.4", "5.5"),
            status="failed" if event.fatal else "passed",
            observed=(event.category, event.code, event.allowance or "none"),
        )
        for event in result.diagnostics
    )
    return tuple(stages)


def validate_associations(inputs: PacketInputs, result: RoundTripResult) -> None:
    config, lease = inputs.config, inputs.deployment
    if lease.owner_run != config.run_id or not inputs.source_content or not inputs.dependencies:
        raise ValueError("missing-or-mismatched-provenance")
    if inputs.fixture.fixture.sha256 not in {s.sha256 for s in inputs.source_content}:
        raise ValueError("missing-frozen-fixture")
    validate_targets(inputs, result)
    validate_roundtrip(inputs, result)


def validate_targets(inputs: PacketInputs, result: RoundTripResult) -> None:
    config, lease = inputs.config, inputs.deployment
    targets = [r.target for r in result.receipts] + [c.target for c in result.charts]
    if isinstance(result.artifact, Succeeded):
        targets.append(result.artifact.payload.target)
    if isinstance(result.reopened, Succeeded):
        targets.append(result.reopened.payload)
    for ready in result.readiness:
        if isinstance(ready, Succeeded):
            page = ready.payload
            if (page.run_id, page.origin, page.build_sha256, page.profile.headed) != (
                config.run_id,
                lease.origin,
                lease.build_sha256,
                config.headed,
            ):
                raise ValueError("readiness-identity-mismatch")
            if not verify_loaded(lease.assets, page.loaded):
                raise ValueError("loaded-build-identity-mismatch")
    for target in targets:
        if (target.run_id, target.origin, target.build_sha256, target.fixture_marker) != (
            config.run_id,
            lease.origin,
            lease.build_sha256,
            inputs.fixture.marker.value,
        ):
            raise ValueError("target-identity-mismatch")
    ready_targets = {
        (r.payload.context_id, r.payload.page_id)
        for r in result.readiness
        if isinstance(r, Succeeded)
    }
    if any((t.context_id, t.page_id) not in ready_targets for t in targets):
        raise ValueError("target-not-bound-to-readiness")


def validate_roundtrip(inputs: PacketInputs, result: RoundTripResult) -> None:
    if isinstance(result.artifact, Succeeded) and isinstance(result.inspection, Succeeded):
        artifact = result.artifact.payload
        for action in ("edit", "save"):
            receipts = tuple(r for r in result.receipts if r.action == action)
            if (
                len(receipts) != 1
                or receipts[0].target != artifact.target
                or receipts[0].status != "observed"
            ):
                raise ValueError("effect-receipt-association-mismatch")
        if artifact.target.artifact_sha256 != inputs.fixture.fixture.sha256:
            raise ValueError("initial-fixture-hash-mismatch")
        InspectedArtifact(
            artifact=artifact,
            inspection=result.inspection.payload,
            fixture_sha256=inputs.fixture.fixture.sha256,
        )
        if isinstance(result.reopened, Succeeded):
            reopened = result.reopened.payload
            if (
                reopened.artifact_sha256 != artifact.sha256
                or reopened.context_id == artifact.target.context_id
                or reopened.page_id == artifact.target.page_id
                or reopened.generation <= artifact.target.generation
                or len(result.checks) != 3
                or len(result.charts) != 3
                or len(result.readiness) != 2
                or not all(c.passed for c in result.checks)
                or tuple(c.phase for c in result.charts) != ("before", "after", "after")
                or tuple(c.target for c in result.charts)
                != (artifact.target, artifact.target, reopened)
            ):
                raise ValueError("reopen-association-incomplete")


def references(result: RoundTripResult) -> set[str]:
    refs = {ref for stage in reduce_stages(result) for ref in stage.evidence_refs}
    refs.update(ref for receipt in result.receipts for ref in receipt.observation_refs)
    refs.update(v.content.path for v in result.videos)
    refs.add("resources.json")
    refs.update(
        str(Path(r.payload.screenshot).parent / name)
        for r in result.readiness
        if isinstance(r, Succeeded)
        for name in ("diagnostics.json", "interactions.json")
    )
    for record in interaction_records(result):
        if any(
            o.target not in tuple(r.target for r in record.receipts) for o in record.observations
        ):
            raise ValueError("observation-target-disagrees")
        refs.update(ref for receipt in record.receipts for ref in receipt.observation_refs)
        refs.update(o.screenshot for o in record.observations)
        refs.update(c.screenshot for o in record.observations for c in o.cells)
    for chart in result.charts:
        refs.update(chart.copy_receipt.observation_refs)
        refs.update(p for c in chart.captures for p in (c.screenshot, c.cropped))
    if isinstance(result.artifact, Succeeded):
        refs.add(str(result.artifact.payload.destination))
        refs.add(str(result.artifact.payload.destination.parent.parent / "persisted.png"))
    if isinstance(result.reopened, Succeeded):
        refs.update(
            str(Path(r.payload.screenshot).parent / "reopened.png")
            for r in result.readiness[1:]
            if isinstance(r, Succeeded)
        )
    return refs


def hash_content(path: Path) -> ContentIdentity:
    return ContentIdentity(
        path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )


def verify_files(
    inputs: PacketInputs, result: RoundTripResult, resources: tuple[ResourceToken, ...]
) -> tuple[ContentIdentity, ...]:
    directory = inputs.config.run_directory
    for source in inputs.source_content:
        if hash_content(Path(source.path)) != source:
            raise ValueError("source-content-changed")
    for ref in references(result):
        path = Path(ref) if Path(ref).is_absolute() else directory / ref
        if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError("missing-or-foreign-evidence")
    verify_provenance(inputs)
    verify_videos(result, resources)
    verify_records(directory, result, resources)
    if isinstance(result.artifact, Succeeded):
        artifact = result.artifact.payload
        if (
            hash_content(artifact.destination).sha256 != artifact.sha256
            or artifact.destination.stat().st_size != artifact.size
        ):
            raise ValueError("persisted-artifact-changed")
    return hash_directory(directory)


def verify_records(
    directory: Path, result: RoundTripResult, resources: tuple[ResourceToken, ...]
) -> None:
    recorded = type(result).model_validate_json(
        (directory / "roundtrip.json").read_text(encoding="utf-8")
    )
    if recorded.model_dump(exclude={"cleanup"}) != result.model_dump(exclude={"cleanup"}):
        raise ValueError("roundtrip-record-disagrees")
    if json.loads((directory / "resources.json").read_text(encoding="utf-8")) != [
        r.model_dump(mode="json") for r in resources
    ]:
        raise ValueError("resource-record-disagrees")
    events = tuple(
        event
        for ready in result.readiness
        if isinstance(ready, Succeeded)
        for event in RecordedDiagnostics.model_validate_json(
            (Path(ready.payload.screenshot).parent / "diagnostics.json").read_text(encoding="utf-8")
        ).events
    )
    if (
        tuple(r for record in interaction_records(result) for r in record.receipts)
        != result.receipts
    ):
        raise ValueError("interaction-record-disagrees")
    if events != result.diagnostics:
        raise ValueError("diagnostics-record-disagrees")


def verify_videos(result: RoundTripResult, resources: tuple[ResourceToken, ...]) -> None:
    contexts = sum(
        r.kind == "context" and not r.identity.startswith("video-check-") for r in resources
    )
    if len(result.videos) != contexts or len({v.content.path for v in result.videos}) != contexts:
        raise ValueError("missing-required-video")
    for video in result.videos:
        path = Path(video.content.path)
        if (
            not video.decoded_frame
            or hash_content(path) != video.content
            or path.stat().st_size != video.size
        ):
            raise ValueError("invalid-finalized-video")
        complete_webm(path.read_bytes())
    if {"context-" + str(v.context_id) for v in result.videos} != {
        r.identity
        for r in resources
        if r.kind == "context" and not r.identity.startswith("video-check-")
    }:
        raise ValueError("video-context-mismatch")


def reconcile_cleanup(
    inputs: PacketInputs, result: RoundTripResult, resources: tuple[ResourceToken, ...]
) -> None:
    tokens = {r.token_id: r for r in resources}
    if len(tokens) != len(resources) or any(r.owner_run != inputs.config.run_id for r in resources):
        raise ValueError("resource-identity-mismatch")
    if len({c.resource_id for c in result.cleanup}) != len(result.cleanup):
        raise ValueError("duplicate-cleanup-finding")
    for cleanup in result.cleanup:
        token = tokens.get(cleanup.resource_id)
        if (
            token is None
            or token.close_state != cleanup.status
            or token.owner_run != cleanup.owner_run
            or cleanup.identity not in (token.kind, token.identity)
        ):
            raise ValueError("cleanup-token-disagrees")


def hash_directory(directory: Path) -> tuple[ContentIdentity, ...]:
    paths = sorted(p for p in directory.rglob("*") if p.is_file())
    for path in paths:
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
        if path.suffix == ".png":
            with Image.open(path) as image:
                image.verify()
    return tuple(hash_content(path) for path in paths)


def finalize(
    inputs: PacketInputs, result: RoundTripResult, resources: tuple[ResourceToken, ...]
) -> RunResult:
    directory = inputs.config.run_directory
    if (directory / "manifest.json").exists() or any(r.close_state == "pending" for r in resources):
        raise ValueError("finalization-requires-closed-resources-and-new-packet")
    stages = list(reduce_stages(result))
    files = tuple(hash_content(p) for p in sorted(directory.rglob("*")) if p.is_file())
    try:
        reconcile_cleanup(inputs, result, resources)
        validate_associations(inputs, result)
        files = verify_files(inputs, result, resources)
        stages.append(finding("evidence", "passed", *(f.path for f in files)))
    except (OSError, ValueError, IndexError):
        stages.append(
            StageFinding(
                stage="evidence",
                requirements=("5.3", "5.5"),
                status="failed",
                observed=("evidence-incomplete-or-inconsistent",),
            )
        )
    cleanup = result.cleanup + tuple(
        CleanupFinding(
            resource_id=r.token_id,
            owner_run=r.owner_run,
            identity=r.identity,
            status=r.close_state,
            final_video_state="not-required",
        )
        for r in resources
        if r.token_id not in {c.resource_id for c in result.cleanup} and r.close_state != "pending"
    )
    good_cleanup = (
        bool(cleanup)
        and all(r.close_state == "graceful" for r in resources)
        and all(
            c.status == "graceful"
            and not c.survivors
            and c.exit_status in (None, 0)
            and c.final_video_state != "unfinished"
            for c in cleanup
        )
    )
    stages.append(finding("cleanup", "passed" if good_cleanup else "failed", "resources.json"))
    stages.extend(
        finding(s, "unexecuted") for s in sorted(MANDATORY_STAGES - {f.stage for f in stages})
    )
    statuses = {s.status for s in stages}
    verdict = (
        "FAILED"
        if "failed" in statuses
        else "UNRESOLVED"
        if "unresolved" in statuses
        else "BLOCKED"
        if statuses != {"passed"}
        else "VERIFIED"
    )
    final = RunResult(
        run_id=inputs.config.run_id,
        source_revision=inputs.source_revision,
        dirty_content=inputs.source_content,
        dependency_identities=inputs.dependencies,
        app_sha256=inputs.deployment.build_sha256,
        profile_id=inputs.config.profile_id,
        findings=tuple(stages),
        cleanup=cleanup,
        verdict=verdict,
        predecessor_run=inputs.config.predecessor_run,
    )
    publish(inputs, result, final, files)
    return final


def publish(
    inputs: PacketInputs,
    result: RoundTripResult,
    final: RunResult,
    files: tuple[ContentIdentity, ...],
) -> None:
    directory = inputs.config.run_directory
    findings = directory / "findings.json"
    with findings.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps([f.model_dump(mode="json") for f in final.findings], indent=2))
    files = (*files, hash_content(findings))
    payload = {
        "inputs": inputs.model_dump(mode="json"),
        "result": final.model_dump(mode="json"),
        "observations": result.model_dump(mode="json"),
        "files": [f.model_dump(mode="json") for f in files],
    }
    temporary = directory / "manifest.partial"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2))
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, directory / "manifest.json")
    temporary.unlink()
