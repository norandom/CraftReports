"""Owned Chromium startup; no workbook edit or persistence claims."""

from __future__ import annotations

import asyncio
import io
import platform
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

from PIL import Image
from playwright.async_api import (
    Browser,
    BrowserContext,
    Error,
    Page,
    Playwright,
    ViewportSize,
    async_playwright,
)
from pydantic import TypeAdapter

from .config import RunConfig
from .contracts import (
    CleanupFinding,
    ContentIdentity,
    Outcome,
    Rejected,
    StageFinding,
    Succeeded,
    Value,
)
from .deployment import DeploymentLease
from .evidence import (
    CDP,
    WARNING_PROFILE,
    Diagnostic,
    Diagnostics,
    PickerState,
    VideoEvidence,
    decode_video,
    native_window,
    verify_loaded,
)
from .visual_profile import GRAPHICS, RuntimeProfile

VIEWPORT: ViewportSize = {"width": 1600, "height": 1100}
PICKER_SCRIPT = """(() => {
  const present = 'showSaveFilePicker' in window;
  const d = Object.getOwnPropertyDescriptor(window, 'showSaveFilePicker');
  const removed = present && !!d && d.configurable && delete window.showSaveFilePicker;
  console.debug('__craftreport_picker__' + JSON.stringify({present,
    configurable: d ? d.configurable : null, removed: !!removed,
    absent: !('showSaveFilePicker' in window)}));
})()"""


class Token(Protocol):
    @property
    def token_id(self) -> UUID: ...


class Registry(Protocol):
    @property
    def run_id(self) -> UUID: ...
    def register(self, kind: Literal["driver", "browser", "context"], identity: str) -> Token: ...
    def mark_acquired(self, token_id: UUID) -> object: ...
    def record_close(self, token_id: UUID, state: Literal["graceful", "failed"]) -> object: ...


class WindowBounds(Value):
    windowState: str
    width: int
    height: int
    left: int
    top: int


class ReadyPage(Value):
    run_id: UUID
    context_id: UUID
    page_id: UUID
    generation: int = 1
    origin: str
    mode: Literal["browser-wasm"] = "browser-wasm"
    build_sha256: str
    loaded: tuple[ContentIdentity, ...]
    profile: RuntimeProfile
    picker: PickerState
    screenshot: str
    input_check: Literal["A1-B1-A1-selection"] = "A1-B1-A1-selection"
    document: Literal["startup-empty-workbook; fixture-unopened"] = (
        "startup-empty-workbook; fixture-unopened"
    )


@dataclass
class BrowserState:
    registry: Registry
    driver: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    page: Page | None = None
    diagnostics: Diagnostics | None = None
    tokens: dict[str, UUID] = field(default_factory=lambda: dict[str, UUID]())
    context_id: UUID = field(default_factory=uuid4)
    page_id: UUID = field(default_factory=uuid4)
    video: VideoEvidence | None = None
    interaction_started: bool = False
    checkpoint: Literal[
        "launch",
        "navigation",
        "build",
        "profile",
        "picker",
        "clipboard-graphics",
        "visibility",
        "grid-input",
        "diagnostics",
    ] = "launch"

    def acquired(self, kind: Literal["driver", "browser", "context"]) -> None:
        token = self.registry.register(kind, kind + "-" + str(self.context_id))
        self.tokens[kind] = token.token_id
        self.registry.mark_acquired(token.token_id)

    def next_context(self) -> None:
        if not self.context or self.context.pages or not self.video or not self.video.decoded_frame:
            raise ValueError("previous recording context is not finalized")
        del self.tokens["context"]
        self.context_id, self.page_id = uuid4(), uuid4()
        self.context, self.page, self.video = None, None, None
        self.interaction_started = False
        self.checkpoint = "launch"


async def launch(config: RunConfig, state: BrowserState) -> Page:
    if state.browser is None:
        state.driver = await async_playwright().start()
        state.acquired("driver")
        state.browser = await state.driver.chromium.launch(
            headless=not config.headed,
            args=list(GRAPHICS),
            executable_path=state.driver.chromium.executable_path,
        )
        state.acquired("browser")
    assert state.browser
    state.context = await state.browser.new_context(
        viewport=VIEWPORT,
        device_scale_factor=1,
        locale="en-US",
        service_workers="block",
        record_video_dir=str(config.run_directory / "videos"),
        record_video_size=VIEWPORT,
    )
    state.acquired("context")
    await state.context.add_init_script(PICKER_SCRIPT)
    state.page = await state.context.new_page()
    return state.page


async def prerequisites(page: Page, context: BrowserContext, origin: str) -> str:
    await context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
    nonce = "craftreport-capability-" + uuid4().hex
    clipboard: bool = await page.evaluate(
        """async nonce => {
      if (!isSecureContext || !navigator.clipboard) return false;
      await navigator.clipboard.writeText(nonce);
      return await navigator.clipboard.readText() === nonce;
    }""",
        nonce,
    )
    if not clipboard:
        raise ValueError("clipboard capability unavailable")
    renderer: str | None = await page.evaluate("""() => {
      const c = document.querySelector('#gridcraft_canvas');
      const gl=c.getContext('webgl2'); if (!gl || gl.isContextLost()) return null;
      const info=gl.getExtension('WEBGL_debug_renderer_info');
      return String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
    }""")
    if not renderer:
        raise ValueError("graphics capability unavailable")
    return renderer


async def visible(page: Page, context: BrowserContext, headed: bool) -> int | None:
    if not headed:
        return None
    session = await context.new_cdp_session(page)
    try:
        window = await cast(CDP, session).send("Browser.getWindowForTarget")
        shown: bool = await page.evaluate("document.visibilityState === 'visible'")
        bounds = WindowBounds.model_validate(window["bounds"])
        if not shown or bounds.windowState == "minimized" or bounds.width <= 0:
            return None
        if platform.system() == "Windows":
            assert context.browser
            info = await context.browser.new_browser_cdp_session()
            try:
                processes = await cast(CDP, info).send("SystemInfo.getProcessInfo")
                records = TypeAdapter(list[ProcessInfo]).validate_python(processes["processInfo"])
                return native_window(next(item.id for item in records if item.type == "browser"))
            finally:
                await info.detach()
        return int(str(window["windowId"]))
    finally:
        await session.detach()


class ProcessInfo(Value):
    type: str
    id: int
    cpuTime: float


def profile_supported(build: str, version: str, system: str, viewport: ViewportSize | None) -> bool:
    """Only the observed Windows geometry is calibrated at this startup milestone."""
    return (build, version) == WARNING_PROFILE and system == "Windows" and viewport == VIEWPORT


def selected_cell(pixels: bytes, column: int) -> bool:
    """Observed v0.7.0 1600x1100 grid header geometry; only selection, no cell values."""
    with Image.open(io.BytesIO(pixels)) as image:
        if image.size != (1600, 1100):
            return False
        rgb = image.convert("RGB")
        x = 28 + column * 51
        top = [cast(tuple[int, int, int], rgb.getpixel((point, 215))) for point in range(x, x + 45)]
        return sum(g > 80 and g > r * 1.5 and g > b * 1.2 for r, g, b in top) >= 40


async def usable_grid(page: Page, config: RunConfig) -> None:
    canvas = page.locator("#gridcraft_canvas")
    await wait_selected(page, 0)
    await canvas.focus()
    await page.keyboard.press("ArrowRight")
    await wait_selected(page, 1)
    await canvas.screenshot(path=str(config.run_directory / "selection-B1.png"))
    await page.keyboard.press("ArrowLeft")
    await wait_selected(page, 0)


async def wait_selected(page: Page, column: int) -> None:
    # The released selection outline animates; observe the effect without replaying input.
    while not selected_cell(await page.locator("#gridcraft_canvas").screenshot(), column):
        await asyncio.sleep(0.05)


async def observe(config: RunConfig, lease: DeploymentLease, state: BrowserState) -> ReadyPage:
    page, context, diagnostics = state.page, state.context, state.diagnostics
    assert page and context and diagnostics and state.browser and state.driver
    state.checkpoint = "navigation"
    await page.goto(lease.origin, wait_until="networkidle")
    await page.locator("#gridcraft_canvas").wait_for(state="visible")
    await page.locator("#gridcraft_loading").wait_for(state="hidden")
    await page.evaluate(
        "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"
    )
    state.checkpoint = "build"
    loaded = diagnostics.loaded()
    if not verify_loaded(lease.assets, loaded) or page.url.rstrip("/") != lease.origin:
        raise ValueError("browser loaded build mismatch")
    state.checkpoint = "profile"
    if not profile_supported(
        lease.build_sha256, state.browser.version, platform.system(), page.viewport_size
    ):
        raise ValueError("startup geometry profile unverified")
    state.checkpoint = "picker"
    absent: bool = await page.evaluate("!('showSaveFilePicker' in window)")
    if not diagnostics.picker or not diagnostics.picker.absent or not absent:
        raise ValueError("picker capability removal unavailable")
    state.checkpoint = "clipboard-graphics"
    renderer = await prerequisites(page, context, lease.origin)
    state.checkpoint = "visibility"
    shown = await visible(page, context, config.headed)
    if config.headed and not shown:
        raise ValueError("headed display unavailable")
    state.checkpoint = "grid-input"
    await usable_grid(page, config)
    path = config.run_directory / "ready.png"
    pixels = await page.locator("#gridcraft_canvas").screenshot(path=str(path))
    with Image.open(io.BytesIO(pixels)) as image:
        if (
            image.width != 1600
            or image.height != 1100
            or len(image.convert("RGB").getcolors(32) or []) == 1
        ):
            raise ValueError("canvas frame unavailable")
    state.checkpoint = "diagnostics"
    if any(event.fatal for event in diagnostics.events):
        raise ValueError("critical browser diagnostic")
    return ReadyPage(
        run_id=config.run_id,
        context_id=state.context_id,
        page_id=state.page_id,
        origin=lease.origin,
        build_sha256=lease.build_sha256,
        loaded=loaded,
        profile=RuntimeProfile(
            browser_version=state.browser.version,
            executable=state.driver.chromium.executable_path,
            os=platform.platform(),
            headed=config.headed,
            visible=shown is not None,
            window_handle=shown,
            graphics_renderer=renderer,
        ),
        picker=diagnostics.picker,
        screenshot=str(path),
    )


async def start(
    config: RunConfig, lease: DeploymentLease, state: BrowserState
) -> Outcome[ReadyPage]:
    if (
        "context" in state.tokens
        or state.registry.run_id != config.run_id
        or lease.owner_run != config.run_id
    ):
        raise ValueError("browser ownership mismatch or already started")
    state.diagnostics = Diagnostics(lease.origin, lease.assets)
    try:
        async with asyncio.timeout(config.bounds.readiness):
            page = await launch(config, state)
            assert state.browser
            state.diagnostics.warning_profile = (lease.build_sha256, state.browser.version)
            state.diagnostics.attach(page)
            assert state.context
            session = await state.context.new_cdp_session(page)
            await state.diagnostics.capture_network(session)
            return Succeeded[ReadyPage](payload=await observe(config, lease, state))
    except (Error, OSError, ValueError, TimeoutError):
        code = state.checkpoint + "-unavailable"
        state.diagnostics.events.append(Diagnostic(category="page", code=code))
        if state.page and not state.page.is_closed():
            try:
                await state.page.screenshot(
                    path=str(config.run_directory / "startup-failed.png"), timeout=2000
                )
            except (Error, OSError):
                state.diagnostics.events.append(
                    Diagnostic(category="evidence", code="screenshot-unavailable")
                )
        return Rejected(
            finding=StageFinding(
                stage="readiness",
                requirements=("1.5", "1.6", "6.6"),
                status="blocked",
                observed=(code,),
            )
        )


async def close(
    config: RunConfig, state: BrowserState, retain_browser: bool = False
) -> tuple[CleanupFinding, ...]:
    findings: list[CleanupFinding] = []
    for kind in ("context",) if retain_browser else ("context", "browser", "driver"):
        if kind not in state.tokens:
            continue
        status: Literal["graceful", "failed"] = "graceful"
        video_state: Literal["not-required", "finalized", "unfinished"] = "not-required"
        try:
            async with asyncio.timeout(config.bounds.cleanup):
                if kind == "context" and state.context:
                    video_state = "unfinished"
                    video = state.page.video if state.page else None
                    await state.context.close()
                    if not video or not state.browser:
                        raise ValueError("required video unavailable")
                    state.video = await decode_video(
                        state.browser, await video.path(), state.registry
                    )
                    state.video = state.video.model_copy(update={"context_id": state.context_id})
                    if not state.video.decoded_frame:
                        raise ValueError("video frame unavailable")
                    video_state = "finalized"
                elif kind == "browser" and state.browser:
                    await state.browser.close()
                    if state.browser.is_connected():
                        raise ValueError("browser still connected")
                elif kind == "driver" and state.driver:
                    await state.driver.stop()
        except (Error, OSError, ValueError, TimeoutError):
            status = "failed"
        token = state.tokens[kind]
        state.registry.record_close(token, status)
        findings.append(
            CleanupFinding(
                resource_id=token,
                owner_run=config.run_id,
                identity=kind,
                status=status,
                final_video_state=video_state,
                survivors=(kind,) if status == "failed" else (),
            )
        )
    return tuple(findings)
