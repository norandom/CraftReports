"""Import must leave backstage before any canvas Name Box interaction."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import Page

from scripts.browser_verification import interactions


def test_visible_title_transition_precedes_namebox_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    title = AsyncMock(side_effect=["Book1", "Book1", "reference.xlsx"])
    frame = AsyncMock()
    screenshot = AsyncMock()
    monkeypatch.setattr(interactions, "title", title)
    monkeypatch.setattr(interactions, "frame", frame)
    asyncio.run(
        interactions.wait_imported(
            cast(Page, SimpleNamespace(screenshot=screenshot)), "Book1", tmp_path / "imported.png"
        )
    )
    assert title.await_count == 3 and frame.await_count == 2
    screenshot.assert_awaited_once()


def test_missing_title_transition_is_bounded_without_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def yield_frame(page: Page) -> None:
        await asyncio.sleep(0)

    monkeypatch.setattr(interactions, "title", AsyncMock(return_value="Book1"))
    monkeypatch.setattr(interactions, "frame", yield_frame)
    screenshot = AsyncMock()

    async def attempt() -> None:
        async with asyncio.timeout(0.01):
            await interactions.wait_imported(
                cast(Page, SimpleNamespace(screenshot=screenshot)),
                "Book1",
                tmp_path / "imported.png",
            )

    with pytest.raises(TimeoutError):
        asyncio.run(attempt())
    screenshot.assert_not_awaited()
