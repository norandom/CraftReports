"""Interaction contract rejection and external-failure sensitivity."""

import asyncio
import io
from types import SimpleNamespace
from typing import cast

import pytest
from PIL import Image, ImageDraw
from playwright.async_api import Page
from pydantic import ValidationError

from scripts.browser_verification import interactions
from scripts.browser_verification.browser import VIEWPORT
from scripts.browser_verification.contracts import CellCheck, ObservationSpec

from .test_browser import assets
from .test_contracts import target


@pytest.mark.parametrize("fault", ["duplicate", "wrong-marker", "missing-marker", "path"])
def test_observation_rejects_ambiguous_or_unidentified_checks(fault: str) -> None:
    selected = target()
    cells = [CellCheck(address="D1", value=selected.fixture_marker)]
    if fault == "duplicate":
        cells *= 2
    if fault == "wrong-marker":
        cells = [CellCheck(address="D1", value="another document")]
    if fault == "missing-marker":
        cells = [CellCheck(address="B3", value="20")]
    with pytest.raises(ValidationError):
        ObservationSpec(
            target=selected,
            cells=tuple(cells),
            checkpoint="../overwrite" if fault == "path" else "before",
            chart_identity="Reference series",
            visual_profile="chromium-download-fallback",
        )


def test_reference_text_cannot_replace_matching_visible_selection() -> None:
    image = Image.new("RGB", (1600, 1100), "white")
    ImageDraw.Draw(image).line((78, 247, 129, 247), fill=(0, 150, 50), width=2)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    assert interactions.selected(stream.getvalue(), "B3")
    for wrong in ("A3", "B2", "B4", "D1"):
        assert not interactions.selected(stream.getvalue(), wrong)


class StaleClipboard:
    def __init__(self) -> None:
        self.value = "25"
        self.copies = 0

    async def evaluate(self, expression: str, nonce: str | None = None) -> str:
        if nonce:
            self.value = nonce
        return self.value

    async def press(self, command: str) -> None:
        assert command == "Control+c"
        self.copies += 1


def test_stale_clipboard_cannot_pass_and_copy_is_not_replayed() -> None:
    boundary = StaleClipboard()
    page = cast(Page, SimpleNamespace(evaluate=boundary.evaluate, keyboard=boundary))

    async def attempt() -> None:
        async with asyncio.timeout(0.12):
            await interactions.copy_text(page)

    with pytest.raises(TimeoutError):
        asyncio.run(attempt())
    assert boundary.value.startswith("craftreport-copy-") and boundary.copies == 1


@pytest.mark.parametrize("fault", ["page", "build", "generation", "context", "origin", "assets"])
def test_changed_external_target_blocks_before_any_input(fault: str) -> None:
    selected = target()
    page = SimpleNamespace(url=selected.origin, viewport_size=VIEWPORT, is_closed=lambda: False)
    context = SimpleNamespace(pages=[page])
    state = SimpleNamespace(
        page=page,
        context=context,
        registry=SimpleNamespace(run_id=selected.run_id),
        context_id=selected.context_id,
        page_id=selected.page_id,
        diagnostics=SimpleNamespace(loaded=assets, events=[]),
    )
    ready = SimpleNamespace(build_sha256=selected.build_sha256, loaded=assets())
    driver = cast(
        interactions.BrowserDriver,
        SimpleNamespace(
            stopped=False,
            target=selected,
            generation=selected.generation,
            state=state,
            page=page,
            context=context,
            ready=ready,
        ),
    )
    if fault == "page":
        state.page = object()
    if fault == "build":
        ready.build_sha256 = "c" * 64
    if fault == "generation":
        driver.generation += 1
    if fault == "context":
        context.pages.append(object())
    if fault == "origin":
        page.url = "http://another.example"
    if fault == "assets":
        state.diagnostics.loaded = lambda: assets()[:-1]
    with pytest.raises(interactions.TargetMismatch):
        interactions.BrowserDriver.guard(driver, selected)
