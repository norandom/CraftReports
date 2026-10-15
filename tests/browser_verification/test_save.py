"""Save dispatch order and honest file failures at the external browser boundary."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.browser_verification import interactions, persistence
from scripts.browser_verification.config import Bounds
from scripts.browser_verification.contracts import Rejected, StageFinding, Succeeded

from .test_contracts import target


@pytest.mark.parametrize("fault", ["none", "conflict", "no-file", "cancel", "native"])
def test_single_armed_save_and_nonpassing_missing_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    events: list[str] = []
    source = tmp_path / "actual-download"
    source.write_bytes(b"actual browser bytes")
    destination = tmp_path / "result.xlsx"
    if fault == "conflict":
        destination.write_bytes(b"preserve")
    download = SimpleNamespace(
        path=AsyncMock(return_value=source),
        failure=AsyncMock(return_value="cancelled" if fault == "cancel" else None),
    )

    async def value() -> object:
        if fault == "no-file":
            await asyncio.sleep(1)
        return download

    class Pending:
        async def __aenter__(self) -> SimpleNamespace:
            events.append("armed")
            return SimpleNamespace(value=value())

        async def __aexit__(self, *args: object) -> None:
            return None

    async def dispatch(*args: object) -> None:
        events.append("save")

    async def reject(stage: str, error: Exception) -> Rejected:
        return Rejected(
            finding=StageFinding(
                stage=stage,
                requirements=("4.3",),
                status="unresolved" if isinstance(error, TimeoutError) else "failed",
                observed=(str(error) or "timeout",),
            )
        )

    driver = SimpleNamespace(
        guard=MagicMock(),
        config=SimpleNamespace(
            destination=destination, run_directory=tmp_path, bounds=Bounds(action=0.1)
        ),
        save_attempted=False,
        ready=SimpleNamespace(picker=SimpleNamespace(absent=fault != "native")),
        state=SimpleNamespace(diagnostics=SimpleNamespace(stage="edit")),
        observe=AsyncMock(),
        checks=MagicMock(),
        document_title="same",
        receipts=[],
        page=SimpleNamespace(expect_download=Pending, screenshot=AsyncMock()),
        rejected=reject,
    )

    def receipt(*args: object) -> None:
        from uuid import uuid4

        from scripts.browser_verification.contracts import ActionReceipt

        driver.receipts.append(
            ActionReceipt(
                target=target(), action="save", dispatch_id=uuid4(), start=1.0, deadline=2.0
            )
        )

    driver.receipt = receipt
    monkeypatch.setattr(persistence, "key", dispatch)
    monkeypatch.setattr(persistence, "title", AsyncMock(return_value="same"))
    result = asyncio.run(persistence.save(cast(interactions.BrowserDriver, driver), target()))
    if fault == "none":
        assert isinstance(result, Succeeded)
        assert destination.read_bytes() == source.read_bytes()
        assert events == ["armed", "save"]
        repeat = asyncio.run(persistence.save(cast(interactions.BrowserDriver, driver), target()))
        assert isinstance(repeat, Rejected) and events == ["armed", "save"]
    else:
        assert isinstance(result, Rejected)
        assert events == ([] if fault in ("conflict", "native") else ["armed", "save"])
        assert (
            destination.read_bytes() == b"preserve"
            if fault == "conflict"
            else not destination.exists()
        )
