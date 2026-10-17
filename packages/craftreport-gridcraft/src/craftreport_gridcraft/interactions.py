"""Narrow Playwright interactions for released GridCraft canvas and formula bar."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from playwright.async_api import Page


async def frame(page: Page) -> None:
    """Await two animation frames to ensure layout and rendering settle."""
    await page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )


async def click(page: Page, x: int, y: int) -> None:
    """Coordinate click followed by frame synchronization."""
    await page.mouse.click(x, y)
    await frame(page)


async def key(page: Page, chord: str) -> None:
    """Key press followed by frame synchronization."""
    await page.keyboard.press(chord)
    await frame(page)


async def copy_text(page: Page, timeout: float = 5.0) -> tuple[str, str]:
    """Copy text using fresh clipboard nonce readback to ensure authentic copy."""
    nonce = f"craftreport-copy-{uuid4().hex}"
    await page.evaluate("nonce => navigator.clipboard.writeText(nonce)", nonce)
    await page.keyboard.press("Control+c")
    async with asyncio.timeout(timeout):
        while True:
            value: str = await page.evaluate("navigator.clipboard.readText()")
            if value != nonce:
                return value.rstrip("\r\n"), nonce
            await asyncio.sleep(0.05)


async def read_cell(page: Page, address: str, timeout: float = 5.0) -> tuple[str, str]:
    """Select address via name box, verify selected reference, and read canvas value."""
    # 1. Name box navigation at (40, 179)
    await click(page, 40, 179)
    await page.keyboard.press("Control+a")
    await page.keyboard.insert_text(address)
    await frame(page)
    await page.keyboard.press("Enter")
    await frame(page)

    # 2. Verify selected reference from name box
    await click(page, 40, 179)
    await page.keyboard.press("Control+a")
    async with asyncio.timeout(timeout):
        reference, _ = await copy_text(page, timeout=timeout)
    if reference != address:
        raise ValueError(f"Selection mismatch: expected {address}, got {reference}")
    await page.keyboard.press("Escape")
    await frame(page)

    # 3. Focus child canvas and copy cell value
    child = page.frames[1] if len(page.frames) > 1 else page
    canvas = child.locator("#gridcraft_canvas")
    await canvas.focus()
    async with asyncio.timeout(timeout):
        value, _ = await copy_text(page, timeout=timeout)
    return reference, value


async def type_cell(page: Page, address: str, value: str) -> None:
    """Navigate to cell and type value into formula bar at (300, 179)."""
    await click(page, 40, 179)
    await page.keyboard.press("Control+a")
    await page.keyboard.insert_text(address)
    await frame(page)
    await page.keyboard.press("Enter")
    await frame(page)

    await click(page, 300, 179)
    await page.keyboard.press("Control+a")
    await page.keyboard.insert_text(value)
    await frame(page)
    await page.keyboard.press("Enter")
    await frame(page)
