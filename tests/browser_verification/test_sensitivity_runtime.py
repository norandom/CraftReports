"""Disposable edit disconnection and a distinct real recovery journey."""

import asyncio
import json
import os
import platform
from pathlib import Path

import pytest

from scripts.browser_verification import deployment, interactions, journey, release, visual_profile
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Rejected, Succeeded
from scripts.browser_verification.fixture import FixtureExpectation

from .test_roundtrip_runtime import FIXTURE, ROOT

pytestmark = pytest.mark.integration


def assert_result(result: journey.RoundTripResult, disconnected: bool, config: RunConfig) -> None:
    assert all(i.accepted for i in result.cleanup), result.cleanup
    assert result.videos and all(i.decoded_frame for i in result.videos)
    if disconnected:
        assert isinstance(result.primary, Rejected), result
        assert result.primary.finding.stage == "edit"
        assert result.primary.finding.status == "failed"
        assert result.primary.finding.observed[0] == "observed-cell-value-mismatch"
        assert result.artifact is result.inspection is result.reopened is None
        evidence = json.loads((config.run_directory / "interactions.json").read_text())
        after = evidence["observations"][-1]
        assert after["checkpoint"] == "fixture-after"
        assert next(i["value"] for i in after["cells"] if i["reference"] == "B3") == "20"
        assert sum(i["action"] == "edit" for i in evidence["receipts"]) == 1
        assert not any(i["action"] == "save" for i in evidence["receipts"])
    else:
        assert result.primary is None, result.primary
        assert isinstance(result.artifact, Succeeded), result.artifact
        assert isinstance(result.inspection, Succeeded) and result.inspection.payload.passed
        assert isinstance(result.reopened, Succeeded), result.reopened
        assert result.reopened.payload.generation > result.artifact.payload.target.generation
        assert result.reopened.payload.context_id != result.artifact.payload.target.context_id
        assert result.reopened.payload.artifact_sha256 == result.artifact.payload.sha256
        assert len(result.charts) == len(result.checks) == 3
        assert all(i.passed for i in result.checks)
        assert len(result.videos) == 2


@pytest.mark.parametrize("disconnected", [True, False], ids=["challenge", "recovery"])
def test_actual_disconnected_edit_and_restored_roundtrip(
    disconnected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    suppressed: list[str] = []

    async def suppress_dispatch(
        driver: interactions.BrowserDriver, edit: interactions.CellEdit
    ) -> None:
        suppressed.append(str(edit.dispatch_id))

    if disconnected:
        monkeypatch.setattr(interactions.BrowserDriver, "dispatch_edit", suppress_dispatch)
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE",
            str(ROOT / "artifacts/browser-verification/task-3.4/acceptance"),
        )
    )
    config = RunConfig(
        deployment=OwnedDeployment(
            mode="owned-wsl" if platform.system() == "Windows" else "owned-linux"
        ),
        output_root=root.resolve(),
        headed=False,
        bounds=Bounds(action=60, cleanup=60),
    )
    config.run_directory.mkdir(parents=True)
    (config.run_directory / "variant.json").write_text(
        json.dumps(
            {
                "run_id": str(config.run_id),
                "disconnected": disconnected,
                "suppressed_boundary": "BrowserDriver.dispatch_edit" if disconnected else None,
                "requirements": ["3.7", "6.3", "6.4", "6.5", "6.6", "7.3", "7.5"],
                "config": config.model_dump(mode="json"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    selected = release.resolve_release(config)
    assert isinstance(selected, Succeeded), selected
    (config.run_directory / "release.json").write_text(
        selected.model_dump_json(indent=2), encoding="utf-8"
    )
    bundle = release.acquire(selected.payload, ROOT / "artifacts/browser-verification/cache")
    assert isinstance(bundle, Succeeded), bundle
    registry = journey.ResourceRegistry(config.run_id)
    state = deployment.DeploymentState(registry)
    result: journey.RoundTripResult | None = None
    closed = None
    try:
        prepared = deployment.prepare(config, bundle.payload, state)
        assert isinstance(prepared, Succeeded), prepared
        result = asyncio.run(
            journey.roundtrip(
                config,
                prepared.payload,
                registry,
                FIXTURE / "reference.xlsx",
                FixtureExpectation.read(FIXTURE / "expected.json"),
                visual_profile.VisualProfile.read(FIXTURE / "visual/manifest.json"),
            )
        )
    finally:
        if state.lease:
            closed = deployment.close(state, config.bounds.cleanup)
            (config.run_directory / "deployment-cleanup.json").write_text(
                closed.model_dump_json(indent=2), encoding="utf-8"
            )
    assert result is not None
    assert_result(result, disconnected, config)
    assert len(suppressed) == int(disconnected)
    assert closed and closed.status == "graceful" and not closed.survivors
