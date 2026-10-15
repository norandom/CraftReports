"""Real headless public SDK handles, finalized video and lifecycle faults."""

import asyncio
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from playwright.async_api import BrowserContext

from scripts.browser_verification import browser, evidence, journey, packet
from scripts.browser_verification.config import Bounds, ExternalDeployment, RunConfig
from scripts.browser_verification.contracts import CleanupFinding

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "fault", ["healthy", "close-failure", "cancel", "late", "decode-failure", "disconnect"]
)
def test_real_headless_sdk_lifecycle(fault: str, monkeypatch: pytest.MonkeyPatch) -> None:
    root = Path(
        os.environ.get(
            "CRAFTREPORT_LIFECYCLE_EVIDENCE", "artifacts/browser-verification/task-4.2/sdk-runtime"
        )
    ).resolve()
    config = RunConfig(
        deployment=ExternalDeployment(
            origin="http://localhost:9000", build_manifest=root / "unused-external-manifest.json"
        ),
        output_root=root / fault,
        headed=False,
        bounds=Bounds(cleanup=20),
    )
    config.run_directory.mkdir(parents=True)
    frozen = tuple(
        packet.hash_content(p)
        for p in sorted(
            [*Path("scripts/browser_verification").glob("*.py"), Path(__file__), Path("uv.lock")]
        )
    )
    (config.run_directory / "source-freeze.json").write_text(
        json.dumps([v.model_dump(mode="json") for v in frozen], indent=2), encoding="utf-8"
    )

    async def exercise() -> None:
        registry = journey.ResourceRegistry(config.run_id)
        state = browser.BrowserState(registry)
        page = await browser.launch(config, state)
        await page.set_content("<h1>Synthetic owned lifecycle</h1>")
        await page.wait_for_timeout(250)
        assert state.context and state.browser
        await inject_fault(fault, state, monkeypatch)
        cleanup = await cancelled_close(fault, config, state, monkeypatch)
        assert all(e.task.done() for e in state.resources.entries)
        assert all(e.close_task is None or e.close_task.done() for e in state.resources.entries)
        assert state.browser.is_connected() is False
        assert all(t.close_state != "pending" for t in registry.tokens)
        healthy = fault in ("healthy", "cancel", "late")
        assert all(f.accepted for f in cleanup) == healthy
        if healthy:
            assert state.video and state.video.decoded_frame
        (config.run_directory / "lifecycle.json").write_text(
            json.dumps(
                {
                    "fault": fault,
                    "cancel_requested": registry.cancel_requested,
                    "resources": [t.model_dump(mode="json") for t in registry.tokens],
                    "cleanup": [f.model_dump(mode="json") for f in cleanup],
                    "video": state.video.model_dump(mode="json") if state.video else None,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        assert all(packet.hash_content(Path(f.path)) == f for f in frozen)

    asyncio.run(exercise())


async def inject_fault(
    fault: str, state: browser.BrowserState, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert state.browser and state.context
    if fault == "late":
        release = asyncio.Event()
        original_context = state.browser.new_context

        async def delayed() -> BrowserContext:
            exact = await original_context()
            await release.wait()
            return exact

        acquired = asyncio.create_task(
            state.resources.acquire("decode-context", "video-check-late-" + uuid4().hex, delayed())
        )
        await asyncio.sleep(0)
        acquired.cancel()
        with pytest.raises(asyncio.CancelledError):
            await acquired
        release.set()
    if fault == "close-failure":

        async def fail() -> None:
            raise ValueError("public-close-failed")

        monkeypatch.setattr(state.context, "close", fail)
    if fault == "decode-failure":

        def fail_decode(_: bytes) -> None:
            raise ValueError("required-video-decode-failed")

        monkeypatch.setattr(evidence, "complete_webm", fail_decode)
    if fault == "disconnect":
        await state.browser.close()


async def cancelled_close(
    fault: str, config: RunConfig, state: browser.BrowserState, monkeypatch: pytest.MonkeyPatch
) -> tuple[CleanupFinding, ...]:
    assert state.context
    if fault == "cancel":
        original = state.context.close
        entered, release = asyncio.Event(), asyncio.Event()

        async def delayed_close() -> None:
            entered.set()
            await release.wait()
            await original()

        monkeypatch.setattr(state.context, "close", delayed_close)
        closing = asyncio.create_task(browser.close(config, state))
        await entered.wait()
        for _ in range(3):
            closing.cancel()
            await asyncio.sleep(0)
        release.set()
        cleanup = await closing
        assert state.registry.cancel_requested
    else:
        cleanup = await browser.close(config, state)
    return cleanup
