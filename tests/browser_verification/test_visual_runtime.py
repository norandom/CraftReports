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
    chart_interactions,
    deployment,
    interactions,
    journey,
    release,
    visual,
    visual_profile,
)
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Succeeded
from scripts.browser_verification.fixture import FixtureExpectation

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/browser_verification"


async def workbook(
    config: RunConfig, lease: deployment.DeploymentLease, registry: journey.ResourceRegistry
) -> None:
    state = browser.BrowserState(registry)
    evidence: dict[str, object] = {
        "config": config.model_dump(mode="json"),
        "unexecuted": ["persistence", "reopen"],
    }
    driver: interactions.BrowserDriver | None = None
    try:
        ready = await browser.start(config, lease, state)
        evidence["ready"] = ready.model_dump(mode="json")
        assert isinstance(ready, Succeeded), ready
        profile = visual_profile.VisualProfile.read(FIXTURE / "visual/manifest.json")
        profile.require_runtime(ready.payload.build_sha256, ready.payload.profile)
        driver = interactions.BrowserDriver(
            config, state, ready.payload, FixtureExpectation.read(FIXTURE / "expected.json")
        )
        opened = await driver.open(FIXTURE / "reference.xlsx")
        evidence["open"] = opened.model_dump(mode="json")
        assert isinstance(opened, Succeeded), opened
        for phase in ("before", "after"):
            if phase == "after":
                edited = await driver.edit(
                    interactions.CellEdit(
                        target=opened.payload,
                        address="B3",
                        before=driver.expected.edit.before,
                        after=driver.expected.edit.after,
                        dispatch_id=uuid4(),
                    )
                )
                evidence["edit"] = edited.model_dump(mode="json")
                assert isinstance(edited, Succeeded), edited
            observed = await chart_interactions.observe_chart(
                driver, opened.payload, phase, profile
            )
            evidence[phase] = observed.model_dump(mode="json")
            assert isinstance(observed, Succeeded), observed
            checks = visual.compare_visual(observed.payload, profile, driver.expected)
            evidence[phase + "-checks"] = checks.model_dump(mode="json")
            assert checks.passed, checks
    finally:
        if driver:
            evidence["receipts"] = [i.model_dump(mode="json") for i in driver.receipts]
            evidence["readbacks"] = [i.model_dump(mode="json") for i in driver.readbacks]
            evidence["observations"] = [i.model_dump(mode="json") for i in driver.observations]
        cleanup = await browser.close(config, state)
        evidence["cleanup"] = [i.model_dump(mode="json") for i in cleanup]
        evidence["video"] = state.video.model_dump(mode="json") if state.video else None
        if state.diagnostics:
            state.diagnostics.write(config.run_directory / "diagnostics.json")
        (config.run_directory / "visual.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        assert state.video and state.video.decoded_frame
        assert all(i.status == "graceful" for i in cleanup)


def test_actual_reviewed_chart_before_and_after() -> None:
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE",
            str(ROOT / "artifacts/browser-verification/task-3.2/acceptance"),
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
        asyncio.run(workbook(config, prepared.payload, registry))
    finally:
        if state.lease:
            closed = deployment.close(state, config.bounds.cleanup)
            (config.run_directory / "deployment-cleanup.json").write_text(
                closed.model_dump_json(indent=2), encoding="utf-8"
            )
            assert closed.status == "graceful" and not closed.survivors
