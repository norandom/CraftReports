"""Profile-bound real Open, cell navigation/copy and one formula-bar edit."""

from __future__ import annotations

import asyncio
import hashlib
import io
import time
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

from PIL import Image
from playwright.async_api import Error, Frame, Page
from playwright.async_api import TimeoutError as BrowserTimeout

from .browser import VIEWPORT, BrowserState, ReadyPage
from .config import RunConfig
from .contracts import (
    ActionReceipt,
    CellCheck,
    ObservationSpec,
    Outcome,
    Rejected,
    StageFinding,
    Succeeded,
    TargetIdentity,
    Value,
)
from .evidence import verify_loaded
from .fixture import CellExpectation, FixtureExpectation


class CellEdit(Value):
    target: TargetIdentity
    address: Literal["B3"]
    before: CellExpectation
    after: CellExpectation
    dispatch_id: UUID


class CellObservation(Value):
    reference: str
    value: str
    reference_nonce: str
    value_nonce: str
    screenshot: str
    observed_at: float


class BrowserObservation(Value):
    target: TargetIdentity
    checkpoint: str
    cells: tuple[CellObservation, ...]
    screenshot: str


class TargetMismatch(ValueError):
    """A guard rejection before workbook mutation."""


def displayed(cell: CellExpectation) -> str:
    return cell.value if isinstance(cell.value, str) else format(cell.value, "g")


def selected(pixels: bytes, address: str) -> bool:
    """Calibrated released Windows canvas selection; independent of copied text."""
    x, y = 27 + (ord(address[0]) - ord("A")) * 51, 215 + (int(address[1:]) - 1) * 16
    with Image.open(io.BytesIO(pixels)) as image:
        if image.size != (1600, 1100):
            return False
        rgb = image.convert("RGB")
        edge = [
            cast(tuple[int, int, int], rgb.getpixel((point, y))) for point in range(x + 2, x + 48)
        ]
        return sum(g > 80 and g > r * 1.5 and g > b * 1.2 for r, g, b in edge) >= 40


async def copy_text(page: Page) -> tuple[str, str]:
    nonce = "craftreport-copy-" + uuid4().hex
    await page.evaluate("nonce => navigator.clipboard.writeText(nonce)", nonce)
    await page.keyboard.press("Control+c")
    while True:
        value: str = await page.evaluate("navigator.clipboard.readText()")
        if value != nonce:
            return value.rstrip("\r\n"), nonce
        await asyncio.sleep(0.05)


async def click(page: Page, x: int, y: int) -> None:
    await page.mouse.click(x, y)
    await frame(page)


async def frame(page: Page) -> None:
    await page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )


async def key(page: Page, command: str) -> None:
    await page.keyboard.press(command)
    await frame(page)


async def title(page: Page) -> str:
    pixels = await page.screenshot(clip={"x": 650, "y": 5, "width": 300, "height": 25})
    return hashlib.sha256(pixels).hexdigest()


class BrowserDriver:
    def __init__(
        self, config: RunConfig, state: BrowserState, ready: ReadyPage, expected: FixtureExpectation
    ) -> None:
        assert state.page and state.context
        if state.interaction_started or (ready.run_id, ready.context_id, ready.page_id) != (
            config.run_id,
            state.context_id,
            state.page_id,
        ):
            raise ValueError("interaction driver ownership mismatch or already acquired")
        state.interaction_started = True
        self.config, self.state, self.ready, self.expected = config, state, ready, expected
        self.page, self.context = state.page, state.context
        self.generation = ready.generation
        self.target: TargetIdentity | None = None
        self.stopped = False
        self.edit_attempted = False
        self.receipts: list[ActionReceipt] = []
        self.observations: list[BrowserObservation] = []
        self.readbacks: list[CellObservation] = []
        self.document_title: str | None = None
        self.page.on("framenavigated", self.navigated)
        self.page.on("popup", lambda _: setattr(self, "stopped", True))
        self.opening = False
        self.page.on("filechooser", lambda _: setattr(self, "stopped", not self.opening))

    def navigated(self, frame: Frame) -> None:
        if frame == self.page.main_frame:
            self.generation += 1

    def guard(self, target: TargetIdentity) -> None:
        state = self.state
        if (
            self.stopped
            or target != self.target
            or target.generation != self.generation
            or state.page is not self.page
            or state.context is not self.context
            or (target.run_id, target.context_id, target.page_id)
            != (state.registry.run_id, state.context_id, state.page_id)
            or self.page.is_closed()
            or self.context.pages != [self.page]
            or self.page.url.rstrip("/") != target.origin
            or self.page.viewport_size != VIEWPORT
            or target.build_sha256 != self.ready.build_sha256
        ):
            raise TargetMismatch("target-identity-mismatch")
        if (
            not state.diagnostics
            or not verify_loaded(self.ready.loaded, state.diagnostics.loaded())
            or any(item.fatal for item in state.diagnostics.events)
        ):
            raise TargetMismatch("loaded-build-or-diagnostics-mismatch")

    async def navigate(self, address: str) -> bytes:
        await click(self.page, 40, 179)
        await key(self.page, "Control+a")
        await self.page.keyboard.insert_text(address)
        await frame(self.page)
        await key(self.page, "Enter")
        while True:
            pixels = await self.page.screenshot()
            if selected(pixels, address):
                return pixels
            await asyncio.sleep(0.05)

    async def cell(self, target: TargetIdentity, address: str) -> CellObservation:
        self.guard(target)
        pixels = await self.navigate(address)
        screenshot = self.config.run_directory / (
            "selected-" + address + "-" + uuid4().hex + ".png"
        )
        screenshot.write_bytes(pixels)
        await click(self.page, 40, 179)
        await key(self.page, "Control+a")
        reference, reference_nonce = await copy_text(self.page)
        if reference != address:
            raise TargetMismatch("selected-reference-mismatch")
        await key(self.page, "Escape")
        await self.page.locator("#gridcraft_canvas").focus()
        value, value_nonce = await copy_text(self.page)
        self.guard(target)
        observation = CellObservation(
            reference=reference,
            value=value,
            reference_nonce=reference_nonce,
            value_nonce=value_nonce,
            screenshot=str(screenshot),
            observed_at=time.monotonic(),
        )
        self.readbacks.append(observation)
        return observation

    def checks(self, target: TargetIdentity, phase: Literal["before", "after"]) -> ObservationSpec:
        cells = self.expected.before if phase == "before" else self.expected.after
        return ObservationSpec(
            target=target,
            checkpoint="fixture-" + phase,
            cells=tuple(
                CellCheck(address=key, value=displayed(value)) for key, value in cells.items()
            ),
            chart_identity=self.expected.chart.title,
            visual_profile=self.config.profile_id,
        )

    async def observe(self, checks: ObservationSpec) -> BrowserObservation:
        async with asyncio.timeout(self.config.bounds.action):
            cells: list[CellObservation] = []
            for check in checks.cells:
                cell = await self.cell(checks.target, check.address)
                cells.append(cell)
            path = self.config.run_directory / (checks.checkpoint + "-" + uuid4().hex + ".png")
            await self.page.screenshot(path=str(path))
            self.guard(checks.target)
            result = BrowserObservation(
                target=checks.target,
                checkpoint=checks.checkpoint,
                cells=tuple(cells),
                screenshot=str(path),
            )
            self.observations.append(result)
            if any(
                cell.value != check.value for cell, check in zip(cells, checks.cells, strict=True)
            ):
                raise ValueError("observed-cell-value-mismatch")
            return result

    def receipt(
        self, target: TargetIdentity, action: Literal["open", "edit"], dispatch: UUID
    ) -> ActionReceipt:
        start = time.monotonic()
        receipt = ActionReceipt(
            target=target,
            action=action,
            dispatch_id=dispatch,
            start=start,
            deadline=start + self.config.bounds.action,
        )
        self.receipts.append(receipt)
        return receipt

    async def rejected(self, stage: str, error: Exception) -> Rejected:
        self.stopped = True
        status = "unresolved" if isinstance(error, (TimeoutError, BrowserTimeout)) else "failed"
        if isinstance(error, TargetMismatch):
            status = "blocked"
        if self.receipts and status == "unresolved":
            self.receipts[-1] = self.receipts[-1].model_copy(update={"status": "unresolved"})
        path = self.config.run_directory / (stage + "-failed-" + uuid4().hex + ".png")
        refs: tuple[str, ...] = ()
        try:
            await self.page.screenshot(path=str(path), timeout=2000)
            refs = (str(path),)
        except (Error, OSError):
            pass
        return Rejected(
            finding=StageFinding(
                stage=stage,
                requirements=("2.5", "3.3", "6.2"),
                status=status,
                observed=(
                    str(error) if isinstance(error, ValueError) else "interaction-unavailable",
                    self.target.model_dump_json() if self.target else "fixture-unopened",
                ),
                evidence_refs=refs,
            )
        )

    async def open(self, fixture: Path) -> Outcome[TargetIdentity]:
        try:
            if self.target:
                raise TargetMismatch("open-already-attempted")
            data = fixture.read_bytes()
            if hashlib.sha256(data).hexdigest() != self.expected.fixture.sha256:
                raise TargetMismatch("fixture-hash-mismatch")
            self.generation += 1
            target = TargetIdentity(
                run_id=self.config.run_id,
                context_id=self.state.context_id,
                page_id=self.state.page_id,
                generation=self.generation,
                origin=self.ready.origin,
                mode="browser-wasm",
                build_sha256=self.ready.build_sha256,
                fixture_id=uuid4(),
                fixture_marker=self.expected.marker.value,
                artifact_sha256=self.expected.fixture.sha256,
            )
            self.target = target
            self.guard(target)
            assert self.state.diagnostics
            self.state.diagnostics.stage = "open"
            self.receipt(target, "open", uuid4())
            async with asyncio.timeout(self.config.bounds.action):
                self.opening = True
                await click(self.page, 40, 53)
                await click(self.page, 65, 192)
                async with self.page.expect_file_chooser() as choice:
                    await click(self.page, 285, 162)
                await (await choice.value).set_files(
                    {
                        "name": "reference.xlsx",
                        "mimeType": "application/octet-stream",
                        "buffer": data,
                    }
                )
                self.opening = False
                while not selected(await self.page.screenshot(), "A1"):
                    await asyncio.sleep(0.05)
                observed = await self.observe(self.checks(target, "before"))
                self.document_title = await title(self.page)
                self.guard(target)
            self.receipts[-1] = self.receipts[-1].model_copy(
                update={"status": "observed", "observation_refs": (observed.screenshot,)}
            )
            return Succeeded(payload=target)
        except (Error, OSError, ValueError, TimeoutError) as error:
            return await self.rejected("open", error)

    async def edit(self, edit: CellEdit) -> Outcome[ActionReceipt]:
        try:
            self.guard(edit.target)
            assert self.state.diagnostics
            self.state.diagnostics.stage = "edit"
            if (
                self.edit_attempted
                or edit.before != self.expected.edit.before
                or edit.after != self.expected.edit.after
            ):
                raise TargetMismatch("edit-precondition-mismatch")
            self.receipt(edit.target, "edit", edit.dispatch_id)
            async with asyncio.timeout(self.config.bounds.action):
                marker = await self.cell(edit.target, "D1")
                if marker.value != edit.target.fixture_marker:
                    raise TargetMismatch("fixture-marker-mismatch")
                before = await self.cell(edit.target, edit.address)
                if before.value != displayed(edit.before):
                    raise TargetMismatch("edit-before-mismatch")
                if self.document_title != await title(self.page):
                    raise TargetMismatch("document-title-mismatch")
                self.guard(edit.target)
                self.edit_attempted = True
                await click(self.page, 350, 179)
                await key(self.page, "Control+a")
                await self.page.keyboard.insert_text(displayed(edit.after))
                await frame(self.page)
                await key(self.page, "Enter")
                observed = await self.observe(self.checks(edit.target, "after"))
            self.receipts[-1] = self.receipts[-1].model_copy(
                update={"status": "observed", "observation_refs": (observed.screenshot,)}
            )
            return Succeeded(payload=self.receipts[-1])
        except (Error, OSError, ValueError, TimeoutError) as error:
            return await self.rejected("edit", error)
