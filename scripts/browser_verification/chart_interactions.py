"""BrowserDriver-owned chart UI acquisition; no visual acceptance verdict."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from PIL import Image
from playwright.async_api import Error

from .contracts import ActionReceipt, CellCheck, Outcome, Rejected, Succeeded, TargetIdentity
from .interactions import BrowserDriver, TargetMismatch, click, copy_text, frame, key
from .visual_profile import ChartObservation, VisualCapture, VisualProfile, compare_crop


async def capture(
    driver: BrowserDriver, profile: VisualProfile, name: str, check: str | None = None
) -> VisualCapture:
    path = driver.config.run_directory / (name + "-" + uuid4().hex + ".png")
    screenshot = driver.config.run_directory / (name + "-full-" + uuid4().hex + ".png")
    await driver.page.screenshot(path=str(screenshot))
    with Image.open(screenshot) as pixels:
        pixels.crop(profile.crops[name].box).save(path)
    return VisualCapture(
        check=check or name, crop_name=name, screenshot=str(screenshot), cropped=str(path)
    )


def matches(frame: VisualCapture, profile: VisualProfile) -> bool:
    return compare_crop(Path(frame.cropped), profile.crops[frame.crop_name], profile.root)


async def settled_dialog(driver: BrowserDriver, profile: VisualProfile) -> VisualCapture:
    """Wait for real fade animation to settle independently of baseline correctness."""
    previous = await capture(driver, profile, "dialog")
    while True:
        await frame(driver.page)
        current = await capture(driver, profile, "dialog")
        if Path(previous.cropped).read_bytes() == Path(current.cropped).read_bytes():
            return current
        previous = current


async def guarded_click(driver: BrowserDriver, target: TargetIdentity, x: int, y: int) -> None:
    driver.guard(target)
    await click(driver.page, x, y)
    driver.guard(target)


async def ensure_home(
    driver: BrowserDriver, target: TargetIdentity, profile: VisualProfile
) -> list[VisualCapture]:
    controls = await capture(driver, profile, "expanded-controls")
    if not matches(controls, profile):
        raise TargetMismatch("expanded-control-geometry-unrecognized")
    home = await capture(driver, profile, "home")
    if matches(home, profile):
        return [controls, home]
    inactive = await capture(driver, profile, "home-inactive")
    if not matches(inactive, profile):
        raise TargetMismatch("ribbon-geometry-unrecognized")
    await guarded_click(driver, target, 95, 53)
    home = await capture(driver, profile, "home")
    if not matches(home, profile):
        raise TargetMismatch("home-ribbon-unavailable")
    return [controls, inactive, home]


async def presentation(
    driver: BrowserDriver, target: TargetIdentity, profile: VisualProfile
) -> list[VisualCapture]:
    frames: list[VisualCapture] = []
    for address in ("A1", "B1"):
        await driver.cell(target, address)
        frames.append(await capture(driver, profile, "bold", "bold-" + address))
    await driver.cell(target, "B3")
    frames.append(await capture(driver, profile, "number"))
    return frames


async def acquire(
    driver: BrowserDriver,
    target: TargetIdentity,
    phase: Literal["before", "after"],
    profile: VisualProfile,
) -> ChartObservation:
    try:
        profile.require_runtime(driver.ready.build_sha256, driver.ready.profile)
    except ValueError as error:
        raise TargetMismatch("visual-profile-mismatch") from error
    if target.artifact_sha256 != profile.fixture_sha256 and (
        phase != "after"
        or driver.reopened_artifact is None
        or not driver.reopened_artifact.inspection.passed
        or driver.reopened_artifact.fixture_sha256 != profile.fixture_sha256
        or driver.reopened_artifact.artifact.sha256 != target.artifact_sha256
    ):
        raise TargetMismatch("visual-fixture-mismatch")
    driver.guard(target)
    frames = await ensure_home(driver, target, profile)
    cells = await driver.observe(driver.checks(target, phase))
    frames += await presentation(driver, target, profile)
    await driver.cell(target, "D3")  # Keep the green active-cell border outside B2:B4.
    await guarded_click(driver, target, 450, 247)
    for name in (
        "chart-" + phase,
        "middle-" + phase,
        "range-" + phase,
        "title",
        "legend",
        "background",
    ):
        frames.append(await capture(driver, profile, name))
    await guarded_click(driver, target, 725, 53)
    await guarded_click(driver, target, 192, 116)
    frames.append(await settled_dialog(driver, profile))
    frames.append(await capture(driver, profile, "series"))
    category, nonce, receipt = await category_copy(driver, target)
    await guarded_click(driver, target, 900, 602)  # Cancel without changing chart data.
    await guarded_click(driver, target, 200, 400)  # Deselect its blue cell-edge overlay.
    post = await driver.observe(driver.checks(target, phase))
    driver.guard(target)
    return ChartObservation(
        target=target,
        phase=phase,
        profile_id=profile.profile_id,
        category=category,
        category_nonce=nonce,
        captures=tuple(frames),
        cells_before=tuple(
            CellCheck(address=cell.reference, value=cell.value) for cell in cells.cells
        ),
        cells=tuple(CellCheck(address=cell.reference, value=cell.value) for cell in post.cells),
        copy_receipt=receipt,
    )


async def category_copy(
    driver: BrowserDriver, target: TargetIdentity
) -> tuple[str, str, ActionReceipt]:
    await guarded_click(driver, target, 770, 469)
    await key(driver.page, "Control+a")
    driver.guard(target)
    start = time.monotonic()
    receipt = ActionReceipt(
        target=target,
        action="copy",
        dispatch_id=uuid4(),
        start=start,
        deadline=start + driver.config.bounds.action,
    )
    driver.receipts.append(receipt)
    category, nonce = await copy_text(driver.page)
    path = driver.config.run_directory / ("category-copy-" + uuid4().hex + ".png")
    await driver.page.screenshot(path=str(path))
    driver.guard(target)
    receipt = receipt.model_copy(update={"status": "observed", "observation_refs": (str(path),)})
    driver.receipts[-1] = receipt
    return category, nonce, receipt


async def observe_chart(
    driver: BrowserDriver,
    target: TargetIdentity,
    phase: Literal["before", "after"],
    profile: VisualProfile,
) -> Outcome[ChartObservation]:
    try:
        async with asyncio.timeout(driver.config.bounds.action):
            observation = await acquire(driver, target, phase, profile)
        path = driver.config.run_directory / ("chart-" + phase + "-" + uuid4().hex + ".json")
        path.write_text(observation.model_dump_json(indent=2), encoding="utf-8")
        return Succeeded(payload=observation)
    except (Error, OSError, ValueError, TimeoutError) as error:
        rejected = await driver.rejected("chart-" + phase, error)
        return Rejected(
            finding=rejected.finding.model_copy(update={"requirements": ("3.4", "3.7", "6.6")})
        )
