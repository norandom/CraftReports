"""Real headless chart observations on an independently frozen profile."""

import asyncio
import json
import os
import platform
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.browser_verification import (
    browser,
    deployment,
    interactions,
    journey,
    persistence,
    release,
    visual_profile,
)
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Rejected, Succeeded
from scripts.browser_verification.fixture import FixtureExpectation

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/browser_verification"


async def workbook(
    config: RunConfig, lease: deployment.DeploymentLease, registry: journey.ResourceRegistry
) -> None:
    result = await journey.roundtrip(
        config,
        lease,
        registry,
        FIXTURE / "reference.xlsx",
        FixtureExpectation.read(FIXTURE / "expected.json"),
        visual_profile.VisualProfile.read(FIXTURE / "visual/manifest.json"),
    )
    assert result.primary is None, result.primary
    assert isinstance(result.artifact, Succeeded), result.artifact
    assert isinstance(result.inspection, Succeeded) and result.inspection.payload.passed
    assert isinstance(result.reopened, Succeeded), result.reopened
    assert result.reopened.payload.generation > result.artifact.payload.target.generation
    assert result.reopened.payload.artifact_sha256 == result.artifact.payload.sha256
    assert len(result.charts) == len(result.checks) == 3
    assert all(i.passed for i in result.checks)
    assert len(result.videos) == 2 and all(i.decoded_frame for i in result.videos)
    assert all(i.accepted for i in result.cleanup)


async def file_fault(
    config: RunConfig,
    lease: deployment.DeploymentLease,
    registry: journey.ResourceRegistry,
    fault: str,
) -> None:
    state = browser.BrowserState(registry)
    evidence: dict[str, object] = {}
    driver: interactions.BrowserDriver | None = None
    try:
        ready = await browser.start(config, lease, state)
        assert isinstance(ready, Succeeded), ready
        driver = interactions.BrowserDriver(
            config, state, ready.payload, FixtureExpectation.read(FIXTURE / "expected.json")
        )
        opened = await driver.open(FIXTURE / "reference.xlsx")
        assert isinstance(opened, Succeeded), opened
        edited = await driver.edit(
            interactions.CellEdit(
                target=opened.payload,
                address="B3",
                before=driver.expected.edit.before,
                after=driver.expected.edit.after,
                dispatch_id=uuid4(),
            )
        )
        assert isinstance(edited, Succeeded), edited
        if fault == "conflict":
            config.destination.parent.mkdir(parents=True)
            config.destination.write_bytes(b"operator-existing-content")
        saved = await persistence.save(driver, opened.payload)
        evidence["save"] = saved.model_dump(mode="json")
        assert isinstance(saved, Rejected), saved
        if fault == "conflict":
            assert config.destination.read_bytes() == b"operator-existing-content"
            assert saved.finding.observed[0] == "destination-conflict"
            assert not driver.save_attempted
        else:
            assert saved.finding.status == "unresolved"
            assert not config.destination.exists()
            assert sum(i.action == "save" for i in driver.receipts) == 1
    finally:
        cleanup = await browser.close(config, state)
        evidence["cleanup"] = [i.model_dump(mode="json") for i in cleanup]
        evidence["video"] = state.video.model_dump(mode="json") if state.video else None
        if driver:
            evidence["receipts"] = [i.model_dump(mode="json") for i in driver.receipts]
        if state.diagnostics:
            state.diagnostics.write(config.run_directory / "diagnostics.json")
        (config.run_directory / "file-fault.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        assert all(i.accepted for i in cleanup)
        assert state.video and state.video.decoded_frame


@pytest.mark.parametrize("fault", ["healthy", "conflict", "no-file"])
def test_actual_save_inspect_and_fresh_reopen(fault: str, monkeypatch: pytest.MonkeyPatch) -> None:
    save_dispatches: list[str] = []
    if fault == "no-file":

        async def suppress_save(*args: object) -> None:
            save_dispatches.append("suppressed-save")

        monkeypatch.setattr(persistence, "key", suppress_save)
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE",
            str(ROOT / "artifacts/browser-verification/task-3.3/acceptance"),
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
    selected = release.resolve_release(config)
    assert isinstance(selected, Succeeded), selected
    (config.run_directory / "release.json").write_text(
        selected.model_dump_json(indent=2), encoding="utf-8"
    )
    bundle = release.acquire(selected.payload, ROOT / "artifacts/browser-verification/cache")
    assert isinstance(bundle, Succeeded), bundle
    registry = journey.ResourceRegistry(config.run_id)
    state = deployment.DeploymentState(registry)
    try:
        prepared = deployment.prepare(config, bundle.payload, state)
        assert isinstance(prepared, Succeeded), prepared
        if fault == "healthy":
            asyncio.run(workbook(config, prepared.payload, registry))
        else:
            asyncio.run(file_fault(config, prepared.payload, registry, fault))
        if fault == "no-file":
            assert save_dispatches == ["suppressed-save"]
    finally:
        if state.lease:
            closed = deployment.close(state, config.bounds.cleanup)
            (config.run_directory / "deployment-cleanup.json").write_text(
                closed.model_dump_json(indent=2), encoding="utf-8"
            )
            assert closed.status == "graceful" and not closed.survivors
