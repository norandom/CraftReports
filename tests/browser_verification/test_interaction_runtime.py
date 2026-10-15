"""Actual headless released-app effects; no hidden workbook API or fake clipboard."""

import asyncio
import json
import os
import platform
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.async_api import FloatRect
from playwright.async_api import TimeoutError as BrowserTimeout

from scripts.browser_verification import browser, deployment, interactions, journey, release
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Rejected, Succeeded, TargetIdentity
from scripts.browser_verification.fixture import FixtureExpectation

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/browser_verification"


async def workbook(
    config: RunConfig,
    lease: deployment.DeploymentLease,
    registry: journey.ResourceRegistry,
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = browser.BrowserState(registry)
    evidence: dict[str, object] = {
        "config": config.model_dump(mode="json"),
        "scenario": scenario,
        "unexecuted": ["chart-verification", "persistence", "byte-inspection", "browser-reopen"],
    }
    driver: interactions.BrowserDriver | None = None
    try:
        ready = await browser.start(config, lease, state)
        evidence["readiness"] = ready.model_dump(mode="json")
        assert isinstance(ready, Succeeded), ready
        driver = interactions.BrowserDriver(
            config, state, ready.payload, FixtureExpectation.read(FIXTURE / "expected.json")
        )
        opened = await driver.open(FIXTURE / "reference.xlsx")
        evidence["open"] = opened.model_dump(mode="json")
        assert isinstance(opened, Succeeded), opened
        await exercise(driver, opened.payload, scenario, monkeypatch, evidence)
    finally:
        if driver:
            evidence["edit_dispatched"] = driver.edit_attempted
            evidence["receipts"] = [item.model_dump(mode="json") for item in driver.receipts]
            evidence["readbacks"] = [item.model_dump(mode="json") for item in driver.readbacks]
            evidence["observations"] = [
                item.model_dump(mode="json") for item in driver.observations
            ]
        cleanup = await browser.close(config, state)
        evidence["cleanup"] = [item.model_dump(mode="json") for item in cleanup]
        evidence["video"] = state.video.model_dump(mode="json") if state.video else None
        if state.diagnostics:
            state.diagnostics.write(config.run_directory / "diagnostics.json")
        (config.run_directory / "interaction.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        assert state.video and state.video.decoded_frame
        assert all(item.accepted for item in cleanup)


async def challenge(
    driver: interactions.BrowserDriver,
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    commits: list[int],
) -> None:
    if scenario == "page":
        await driver.page.goto("about:blank")
    if scenario == "marker":
        await driver.navigate("D1")
        await interactions.click(driver.page, 350, 179)
        await interactions.key(driver.page, "Control+a")
        await driver.page.keyboard.insert_text("wrong-marker")
        await interactions.frame(driver.page)
        await interactions.key(driver.page, "Enter")
    if scenario == "timeout":
        original = driver.page.keyboard.press

        async def lost_response(command: str) -> None:
            await original(command)
            if command == "Enter" and driver.edit_attempted:
                commits[0] += 1
                await interactions.frame(driver.page)
                raise BrowserTimeout("transport timeout after real commit")

        monkeypatch.setattr(driver.page.keyboard, "press", lost_response)
    if scenario == "late-page":
        capture = driver.page.screenshot

        async def navigated_after_capture(
            *, path: str | None = None, timeout: float | None = None, clip: FloatRect | None = None
        ) -> bytes:
            pixels = await capture(path=path, timeout=timeout, clip=clip)
            if path and Path(path).name.startswith("fixture-after-"):
                await driver.page.goto("about:blank")
            return pixels

        monkeypatch.setattr(driver.page, "screenshot", navigated_after_capture)


async def exercise(
    driver: interactions.BrowserDriver,
    target: TargetIdentity,
    scenario: str,
    monkeypatch: pytest.MonkeyPatch,
    evidence: dict[str, object],
) -> None:
    commits = [0]
    await challenge(driver, scenario, monkeypatch, commits)
    edit = interactions.CellEdit(
        target=target,
        address="B3",
        before=driver.expected.edit.before,
        after=driver.expected.edit.after,
        dispatch_id=uuid4(),
    )
    edited = await driver.edit(edit)
    evidence["edit"] = edited.model_dump(mode="json")
    if scenario == "healthy":
        assert isinstance(edited, Succeeded), edited
        assert edited.payload.status == "observed"
        observed = driver.observations[-1]
        assert {cell.reference: cell.value for cell in observed.cells} == {
            address: interactions.displayed(cell) for address, cell in driver.expected.after.items()
        }
        assert all(cell.observed_at >= edited.payload.start for cell in observed.cells)
        nonces = [
            nonce for cell in driver.readbacks for nonce in (cell.reference_nonce, cell.value_nonce)
        ]
        assert len(set(nonces)) == len(nonces)
    else:
        assert isinstance(edited, Rejected), edited
        assert edited.finding.status == ("unresolved" if scenario == "timeout" else "blocked")
        assert driver.edit_attempted == (scenario in ("timeout", "late-page"))
    count = len(driver.receipts)
    replay = await driver.edit(edit)
    assert isinstance(replay, Rejected) and replay.finding.status == "blocked"
    assert len(driver.receipts) == count
    evidence["repeat_rejected"] = replay.model_dump(mode="json")
    if scenario == "timeout":
        evidence["formula_commit_count"] = commits[0]
        assert commits == [1]
    if scenario in ("marker", "timeout"):
        monkeypatch.undo()
        await independent_readback(driver, scenario, evidence)


async def independent_readback(
    driver: interactions.BrowserDriver, scenario: str, evidence: dict[str, object]
) -> None:
    pixels = await driver.navigate("B3")
    path = driver.config.run_directory / "failure-B3.png"
    path.write_bytes(pixels)
    await interactions.click(driver.page, 40, 179)
    await interactions.key(driver.page, "Control+a")
    reference, reference_nonce = await interactions.copy_text(driver.page)
    await interactions.key(driver.page, "Escape")
    value, nonce = await interactions.copy_text(driver.page)
    evidence["failure_readback"] = {
        "reference": reference,
        "reference_nonce": reference_nonce,
        "value": value,
        "nonce": nonce,
        "screenshot": str(path),
    }
    assert reference == "B3" and value == ("25" if scenario == "timeout" else "20")
    if scenario == "timeout":
        assert driver.receipts[-1].status == "unresolved"


@pytest.mark.parametrize("scenario", ["healthy", "page", "marker", "timeout", "late-page"])
def test_actual_fixture_and_single_edit(scenario: str, monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE", str(ROOT / "artifacts/browser-verification/task-3.1")
        )
    ).resolve()
    config = RunConfig(
        deployment=OwnedDeployment(
            mode="owned-wsl" if platform.system() == "Windows" else "owned-linux"
        ),
        output_root=root,
        headed=False,
        # Eleven independently copied references/values plus screenshots take ~20s here.
        # This explicit host calibration is a deadline, not a performance acceptance limit.
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
        asyncio.run(workbook(config, prepared.payload, registry, scenario, monkeypatch))
    finally:
        if state.lease:
            closed = deployment.close(state, config.bounds.cleanup)
            (config.run_directory / "deployment-cleanup.json").write_text(
                closed.model_dump_json(indent=2), encoding="utf-8"
            )
            assert closed.status == "graceful" and not closed.survivors
