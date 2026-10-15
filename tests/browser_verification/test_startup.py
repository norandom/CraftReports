"""Real official-release startup only; workbook round trips remain separate tasks."""

import asyncio
import os
import platform
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.async_api import Page

from scripts.browser_verification import browser, deployment, journey, release
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Succeeded

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def official() -> Iterator[release.BundleIdentity]:
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE", str(ROOT / "artifacts/browser-verification/task-2.4")
        )
    )
    mode = "owned-wsl" if platform.system() == "Windows" else "owned-linux"
    config = RunConfig(deployment=OwnedDeployment(mode=mode), output_root=root.resolve())
    selected = release.resolve_release(config)
    assert isinstance(selected, Succeeded), selected
    root.mkdir(parents=True, exist_ok=True)
    (root / "latest-release.json").write_text(selected.model_dump_json(indent=2), encoding="utf-8")
    cache = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_CACHE", str(ROOT / "artifacts/browser-verification/cache")
        )
    )
    acquired = release.acquire(selected.payload, cache.resolve())
    assert isinstance(acquired, Succeeded), acquired
    yield acquired.payload


@pytest.mark.parametrize("scenario", ["headed", "headless", "missing-wasm", "clipboard-denied"])
def test_official_startup_and_failure_cleanup(
    official: release.BundleIdentity, scenario: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE", str(ROOT / "artifacts/browser-verification/task-2.4")
        )
    )
    mode = "owned-wsl" if platform.system() == "Windows" else "owned-linux"
    config = RunConfig(
        deployment=OwnedDeployment(mode=mode),
        output_root=root.resolve(),
        headed=scenario == "headed",
        bounds=Bounds(action=10, cleanup=60),
    )
    registry = journey.ResourceRegistry(config.run_id)
    state = deployment.DeploymentState(registry)
    original = browser.launch

    async def challenged(selected: RunConfig, owned: browser.BrowserState) -> Page:
        page = await original(selected, owned)
        if scenario == "missing-wasm":
            await page.route("**/*.wasm", lambda route: route.abort())
        if scenario == "clipboard-denied":
            assert owned.context
            # Explicitly deny clipboard through real Chromium permissions, not a fake clipboard.
            await owned.context.grant_permissions([])

            async def deny(permissions: list[str], *, origin: str | None = None) -> None:
                return None

            monkeypatch.setattr(owned.context, "grant_permissions", deny)
        return page

    monkeypatch.setattr(browser, "launch", challenged)
    try:
        prepared = deployment.prepare(config, official, state)
        assert isinstance(prepared, Succeeded), prepared
        result = asyncio.run(journey.startup(config, prepared.payload, registry))
        assert result.video and result.video.decoded_frame
        assert all(item.status == "graceful" for item in result.cleanup)
        assert all(
            item.close_state == "graceful" for item in registry.tokens if item.kind != "deployment"
        )
        if scenario in ("headed", "headless"):
            assert isinstance(result.readiness, Succeeded), result
            ready = result.readiness.payload
            assert ready.profile.headed == (scenario == "headed")
            assert ready.profile.visible == (scenario == "headed")
            assert ready.picker.absent and ready.input_check == "A1-B1-A1-selection"
            assert len(ready.loaded) == 3
        else:
            assert result.readiness.status == "rejected"
            assert (config.run_directory / "startup-failed.png").is_file()
    finally:
        if state.lease:
            closed = deployment.close(state, config.bounds.cleanup)
            (config.run_directory / "deployment-cleanup.json").write_text(
                closed.model_dump_json(indent=2), encoding="utf-8"
            )
            assert closed.status == "graceful" and not closed.survivors
