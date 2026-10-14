"""Configuration, value boundaries and immediate acquisition ownership."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from scripts.browser_verification.config import (
    Bounds,
    ExternalDeployment,
    OwnedDeployment,
    RunConfig,
)
from scripts.browser_verification.contracts import (
    MANDATORY_STAGES,
    ActionReceipt,
    ArtifactIdentity,
    CheckSet,
    CleanupFinding,
    Outcome,
    Rejected,
    RunResult,
    StageFinding,
    Succeeded,
    TargetIdentity,
)
from scripts.browser_verification.journey import ResourceRegistry


def target() -> TargetIdentity:
    return TargetIdentity(
        run_id=uuid4(),
        context_id=uuid4(),
        page_id=uuid4(),
        generation=1,
        origin="http://localhost:8891",
        mode="browser-wasm",
        build_sha256="a" * 64,
        fixture_id=uuid4(),
        fixture_marker="synthetic-reference",
        artifact_sha256="b" * 64,
    )


def finding(status: str = "failed") -> StageFinding:
    return StageFinding.model_validate(
        {
            "stage": "visible-mutation",
            "requirements": ["6.2"],
            "status": status,
            "expected": ["25"],
            "observed": ["20"],
            "evidence_refs": ["after.png"],
        }
    )


def test_run_isolated_paths_and_json_roundtrip(tmp_path: Path) -> None:
    first = RunConfig(deployment=OwnedDeployment(mode="owned-wsl"), output_root=tmp_path)
    second = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    assert first.run_id != second.run_id
    assert first.run_directory != second.run_directory
    assert first.destination == tmp_path / str(first.run_id) / "output" / "result.xlsx"
    assert first.headed is True
    assert (first.bounds.readiness, first.bounds.action, first.bounds.cleanup) == (90, 20, 30)
    assert RunConfig.model_validate_json(first.model_dump_json()) == first


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf"), True])
@pytest.mark.parametrize("field", ["readiness", "action", "cleanup"])
def test_deadlines_reject_nonpositive_nonfinite_and_boolean(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Bounds.model_validate({field: value})


def test_deployment_selection_and_origin_validation(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"output_root": str(tmp_path), "deployment": {"mode": "external"}})
    external = ExternalDeployment(
        origin="https://example.test", build_manifest=tmp_path / "build.json"
    )
    assert external.mode == "external"
    for origin in (
        "http://0.0.0.0:8891",
        "https://u:p@example.test",
        "https://example.test?q=x",
        "https://example.test/path",
        "file:///app",
        "http://example.test#fragment",
    ):
        with pytest.raises(ValidationError):
            ExternalDeployment(origin=origin, build_manifest=tmp_path / "build.json")
    with pytest.raises(ValidationError):
        OwnedDeployment(mode="owned-linux", port=8871)
    with pytest.raises(ValidationError):
        OwnedDeployment.model_validate({"mode": "owned-linux", "origin": "http://localhost"})
    with pytest.raises(ValidationError):
        RunConfig.model_validate({"deployment": {"mode": "owned-linux"}, "output_root": "relative"})


def test_target_artifact_binding_and_frozen_json(tmp_path: Path) -> None:
    selected = target()
    output = ArtifactIdentity(
        artifact_id=uuid4(),
        destination=tmp_path / "result.xlsx",
        size=20,
        sha256="c" * 64,
        target=selected,
        route="download",
    )
    assert ArtifactIdentity.model_validate_json(output.model_dump_json()) == output
    assert selected.context_id != selected.page_id != selected.fixture_id
    with pytest.raises(ValidationError):
        selected.generation = 2
    for changes in ({"generation": 0}, {"build_sha256": "bad"}, {"fixture_marker": " "}):
        with pytest.raises(ValidationError):
            TargetIdentity.model_validate(selected.model_dump() | changes)


@pytest.mark.parametrize("role", ["run_id", "context_id", "page_id", "fixture_id"])
def test_output_identity_rejects_target_role_aliases(tmp_path: Path, role: str) -> None:
    selected = target()
    data = {
        "artifact_id": selected.model_dump()[role],
        "destination": tmp_path / "result.xlsx",
        "size": 20,
        "sha256": "c" * 64,
        "target": selected,
        "route": "download",
    }
    with pytest.raises(ValidationError, match="output artifact identity must be distinct"):
        ArtifactIdentity.model_validate(data)
    data["target"] = selected.model_dump(mode="json")
    data["destination"] = str(tmp_path / "result.xlsx")
    data["artifact_id"] = str(data["artifact_id"])
    with pytest.raises(ValidationError, match="output artifact identity must be distinct"):
        ArtifactIdentity.model_validate_json(json.dumps(data))


def test_nonpassing_outcomes_never_carry_success_payload() -> None:
    codec = TypeAdapter(Outcome[TargetIdentity])
    result = codec.validate_json(Succeeded(payload=target()).model_dump_json())
    assert isinstance(result, Succeeded)
    for state in ("failed", "blocked", "unresolved"):
        result = codec.validate_json(Rejected(finding=finding(state)).model_dump_json())
        assert isinstance(result, Rejected)
        assert "payload" not in json.loads(result.model_dump_json())
    for state in ("pending", "passed", "unexecuted"):
        with pytest.raises(ValidationError):
            Rejected(finding=finding(state))
    with pytest.raises(ValidationError):
        codec.validate_python(
            {"status": "rejected", "finding": finding().model_dump(), "payload": {}}
        )


def test_check_states_and_receipt_deadline_preserve_uncertainty() -> None:
    for state in ("pending", "unresolved", "unexecuted", "failed", "blocked"):
        assert not CheckSet(findings=(finding(state),)).passed
    assert not CheckSet().passed
    assert CheckSet(findings=(finding("passed"),)).passed
    receipt = ActionReceipt(
        dispatch_id=uuid4(), target=target(), action="edit", start=10, deadline=30
    )
    assert receipt.status == "pending"
    assert (
        ActionReceipt.model_validate(receipt.model_dump() | {"status": "unresolved"}).status
        == "unresolved"
    )
    with pytest.raises(ValidationError):
        ActionReceipt.model_validate(receipt.model_dump() | {"deadline": 10})
    with pytest.raises(ValidationError):
        ActionReceipt.model_validate(receipt.model_dump() | {"status": "observed"})
    with pytest.raises(ValidationError):
        StageFinding.model_validate(finding().model_dump() | {"requirements": ["REQ-6.2"]})


def test_partial_acquisition_survives_rejection_and_cancel() -> None:
    registry = ResourceRegistry(uuid4())
    token = registry.register("context", "exact-context-123")
    rejected = Rejected(finding=finding("blocked"))
    assert rejected.status == "rejected"
    assert registry.tokens == (token,)
    assert token.acquisition == "partial"
    registry.request_cancel()
    assert registry.cancel_requested
    assert registry.pending_cleanup == (token,)
    assert registry.mark_acquired(token.token_id).acquisition == "acquired"
    closed = registry.record_close(token.token_id, "graceful")
    assert closed.owner_run == registry.run_id
    assert not registry.pending_cleanup
    assert registry.tokens[0].close_state == "graceful"


def test_registry_reverse_order_and_exact_ownership() -> None:
    registry = ResourceRegistry(uuid4())
    browser = registry.register("browser", "exact-browser-1")
    context = registry.register("context", "exact-context-2")
    assert registry.pending_cleanup == (context, browser)
    with pytest.raises(ValueError):
        registry.register("browser", "exact-browser-1")
    with pytest.raises(KeyError):
        registry.record_close(uuid4(), "graceful")
    assert registry.record_close(context.token_id, "failed").close_state == "failed"
    assert registry.pending_cleanup == (registry.tokens[1], browser)
    registry.record_close(context.token_id, "forced")
    with pytest.raises(ValueError):
        registry.mark_acquired(context.token_id)
    assert registry.tokens[1].close_state == "forced"


def test_cancellation_before_acquisition_still_retains_late_resource() -> None:
    registry = ResourceRegistry(uuid4())
    registry.request_cancel()
    token = registry.register("process", "owned-process-group-7")
    assert registry.cancel_requested
    assert registry.pending_cleanup == (token,)


def test_verified_result_requires_every_stage_and_successful_owned_cleanup() -> None:
    run_id = uuid4()
    stages = tuple(
        StageFinding(stage=stage, requirements=("7.4",), status="passed")
        for stage in sorted(MANDATORY_STAGES)
    )
    cleanup = CleanupFinding(
        resource_id=uuid4(),
        owner_run=run_id,
        identity="owned-context",
        status="graceful",
        final_video_state="finalized",
    )
    result = RunResult(
        run_id=run_id,
        source_revision="synthetic-test-revision",
        dependency_identities=("playwright-test",),
        app_sha256="d" * 64,
        profile_id="chromium-download-fallback",
        findings=stages,
        cleanup=(cleanup,),
        verdict="VERIFIED",
    )
    assert RunResult.model_validate_json(result.model_dump_json()) == result
    for changes in (
        {"findings": stages[:-1]},
        {"cleanup": ()},
        {"app_sha256": None},
        {"findings": (*stages, finding("unexecuted"))},
    ):
        with pytest.raises(ValidationError):
            RunResult.model_validate(result.model_dump() | changes)
    for changes in (
        {"status": "forced"},
        {"status": "failed"},
        {"exit_status": 1},
        {"survivors": ["context"]},
        {"final_video_state": "unfinished"},
        {"owner_run": uuid4()},
    ):
        with pytest.raises(ValidationError):
            RunResult.model_validate(
                result.model_dump() | {"cleanup": [cleanup.model_dump() | changes]}
            )


def test_configuration_trust_and_recovery_identity(tmp_path: Path) -> None:
    config = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    for changes in (
        {"trusted_release_sha256": "f" * 64},
        {"trust_source": "operator"},
        {"predecessor_run": config.run_id},
        {"headed": "false"},
    ):
        with pytest.raises(ValidationError):
            RunConfig.model_validate(config.model_dump() | changes)
