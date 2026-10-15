"""The dispatch seam retains the original UI action ordering."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from scripts.browser_verification import interactions
from scripts.browser_verification.fixture import FixtureExpectation

from .test_contracts import target
from .test_roundtrip_runtime import FIXTURE


def test_dispatch_commits_the_real_formula_bar_once(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[object] = []

    async def click(*args: object) -> None:
        events.append(args[1:])

    async def key(*args: object) -> None:
        events.append(args[1])

    async def insert(text: str) -> None:
        events.append(text)

    monkeypatch.setattr(interactions, "click", click)
    monkeypatch.setattr(interactions, "key", key)
    monkeypatch.setattr(interactions, "frame", AsyncMock())
    driver = cast(
        interactions.BrowserDriver,
        SimpleNamespace(page=SimpleNamespace(keyboard=SimpleNamespace(insert_text=insert))),
    )
    expected = FixtureExpectation.read(FIXTURE / "expected.json")
    edit = interactions.CellEdit(
        target=target(),
        address="B3",
        before=expected.edit.before,
        after=expected.edit.after,
        dispatch_id=uuid4(),
    )
    asyncio.run(interactions.BrowserDriver.dispatch_edit(driver, edit))
    assert events == [(350, 179), "Control+a", "25", "Enter"]
