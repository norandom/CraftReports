"""Sanitized startup diagnostics and actual loaded-byte/video observations."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from playwright.async_api import (
    Browser,
    BrowserContext,
    CDPSession,
    ConsoleMessage,
    Error,
    Page,
    Request,
)
from pydantic import BaseModel, ConfigDict, Field

from .contracts import ContentIdentity, Value
from .lifecycle import SDKResources, protected

WARNING_PROFILE = (
    "ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27",
    "156.0.8078.4",
)
# Exact released-app/Chromium messages; loaded hashes and WebGL readiness remain mandatory.
WARNINGS = {
    (
        "The `integrity` attribute is currently ignored for preload destinations that do not "
        "support subresource integrity. See https://crbug.com/981419 for more information"
    ): "preload-integrity-unsupported; actual-loaded-sha256-required",
    ("No available adapters."): "webgpu-unavailable; actual-webgl2-required",
    (
        "[egui_wgpu] egui-wgpu-0.36.2/src/lib.rs:461: Software rasterizer detected - loss of "
        'performance expected. backend: Gl, device_type: Cpu, name: "ANGLE (Google, Vulkan '
        '1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)", driver_info: '
        '"WebGL 2.0 (OpenGL ES 3.0 Chromium)", subgroup_size: 4..=128, transient_saves_memory: '
        "None, limit_bucket: None"
    ): "explicit-software-graphics-profile; no-performance-claim",
    (
        "[eframe::web::app_runner] eframe-0.36.2/src/web/app_runner.rs:337: Unhandled egui "
        "viewport command: SetTheme(Light) - not implemented in web backend"
    ): "native-window-theme-unsupported; canvas-profile-fixed",
    (
        "[eframe::web::app_runner] eframe-0.36.2/src/web/app_runner.rs:337: Unhandled egui "
        'viewport command: Title("Book1") - not implemented in web backend'
    ): "native-window-title-unsupported; target-identity-independent",
    (
        "[eframe::web::app_runner] eframe-0.36.2/src/web/app_runner.rs:337: Unhandled egui "
        'viewport command: Title("reference.xlsx") - not implemented in web backend'
    ): "synthetic-fixture-native-title-unsupported; fresh-marker-and-page-identity-required",
    (
        "[eframe::web::app_runner] eframe-0.36.2/src/web/app_runner.rs:337: Unhandled egui "
        'viewport command: Title("reference.xlsx \u2014 Edited") - not implemented in web backend'
    ): "synthetic-edit-native-title-unsupported; fresh-cell-effect-required",
}


class Diagnostic(Value):
    stage: Literal["readiness", "open", "edit", "persistence"] = "readiness"
    category: Literal["console", "page", "request", "asset", "evidence"]
    code: str
    asset: str | None = None
    fatal: bool = True
    allowance: str | None = None


class CDP(Protocol):
    async def send(
        self, method: str, params: dict[str, object] | None = None
    ) -> dict[str, object]: ...


class NetworkRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str


class PausedResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    requestId: str
    responseStatusCode: int | None = None
    request: NetworkRequest


class ResponseBody(Value):
    body: str
    base64Encoded: bool


class PickerState(Value):
    present: bool
    configurable: bool | None
    removed: bool
    absent: bool


class VideoEvidence(Value):
    content: ContentIdentity
    size: int = Field(gt=0)
    duration: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    decoded_frame: bool
    context_id: UUID | None = None


def native_window(process_id: int) -> int | None:
    """Windows visibility evidence bound to Chromium's directly observed process ID."""
    if sys.platform != "win32":
        return None
    windows: list[int] = []
    user32 = ctypes.windll.user32

    def inspect(handle: int, _: int) -> bool:
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == process_id and user32.IsWindowVisible(handle):
            windows.append(handle)
        return True

    callback = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(inspect)
    user32.EnumWindows(callback, 0)
    return windows[0] if windows else None


@dataclass
class Diagnostics:
    origin: str
    expected: tuple[ContentIdentity, ...]
    events: list[Diagnostic] = field(default_factory=lambda: list[Diagnostic]())
    responses: list[ContentIdentity] = field(default_factory=lambda: list[ContentIdentity]())
    picker: PickerState | None = None
    warning_profile: tuple[str, str] | None = None
    stage: Literal["readiness", "open", "edit", "persistence"] = "readiness"

    def asset(self, url: str) -> str | None:
        parsed = urlsplit(url)
        if parsed.scheme + "://" + parsed.netloc != self.origin:
            return None
        path = parsed.path.lstrip("/") or "index.html"
        return path if path in {item.path for item in self.expected} else None

    def console(self, message: ConsoleMessage) -> None:
        prefix = "__craftreport_picker__"
        if message.type == "debug" and message.text.startswith(prefix):
            try:
                self.picker = PickerState.model_validate_json(message.text[len(prefix) :])
            except ValueError:
                self.events.append(
                    Diagnostic(stage=self.stage, category="page", code="invalid-picker-proof")
                )
        elif message.type in ("error", "warning"):
            allowance = (
                WARNINGS.get(message.text)
                if (message.type == "warning" and self.warning_profile == WARNING_PROFILE)
                else None
            )
            self.events.append(
                Diagnostic(
                    stage=self.stage,
                    category="console",
                    code=message.type,
                    fatal=allowance is None,
                    allowance=" / ".join(WARNING_PROFILE) + ": " + allowance if allowance else None,
                )
            )

    def failed_request(self, request: Request) -> None:
        asset = self.asset(request.url)
        critical = asset is not None or request.resource_type in ("document", "script", "fetch")
        self.events.append(
            Diagnostic(
                stage=self.stage,
                category="request",
                code="request-failed",
                asset=asset,
                fatal=critical,
            )
        )

    def attach(self, page: Page) -> None:
        page.on("console", self.console)
        page.on(
            "pageerror",
            lambda _: self.events.append(
                Diagnostic(stage=self.stage, category="page", code="uncaught-exception")
            ),
        )
        page.on("requestfailed", self.failed_request)

    async def inspect_response(self, event: dict[str, object], session: CDP) -> None:
        response = PausedResponse.model_validate(event)
        asset = self.asset(response.request.url)
        try:
            if asset:
                if response.responseStatusCode != 200:
                    raise ValueError("asset status rejected")
                body = ResponseBody.model_validate(
                    await session.send("Fetch.getResponseBody", {"requestId": response.requestId})
                )
                data = (
                    base64.b64decode(body.body, validate=True)
                    if body.base64Encoded
                    else body.body.encode("utf-8")
                )
                if len(data) > 64 * 1024 * 1024:
                    raise ValueError("asset bound exceeded")
                self.responses.append(
                    ContentIdentity(path=asset, sha256=hashlib.sha256(data).hexdigest())
                )
        except (Error, ValueError):
            self.events.append(
                Diagnostic(
                    stage=self.stage, category="asset", code="asset-response-rejected", asset=asset
                )
            )
        finally:
            await session.send("Fetch.continueRequest", {"requestId": response.requestId})

    async def capture_network(self, session: CDPSession) -> None:
        async def inspect(event: dict[str, object]) -> None:
            await self.inspect_response(event, cast(CDP, session))

        session.on("Fetch.requestPaused", inspect)
        await cast(CDP, session).send("Network.enable")
        await cast(CDP, session).send("Network.setCacheDisabled", {"cacheDisabled": True})
        await cast(CDP, session).send(
            "Fetch.enable",
            {"patterns": [{"urlPattern": self.origin + "/*", "requestStage": "Response"}]},
        )

    def loaded(self) -> tuple[ContentIdentity, ...]:
        return tuple(sorted(set(self.responses), key=lambda item: item.path))

    def write(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "events": [item.model_dump(mode="json") for item in self.events],
                    "picker": self.picker.model_dump(mode="json") if self.picker else None,
                    "loaded": [item.model_dump(mode="json") for item in self.loaded()],
                    "warning_profile": self.warning_profile,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def verify_loaded(
    expected: tuple[ContentIdentity, ...], observed: tuple[ContentIdentity, ...]
) -> bool:
    return (
        {Path(item.path).suffix for item in expected} == {".html", ".js", ".wasm"}
        and len({item.path for item in observed}) == len(observed)
        and set((item.path, item.sha256) for item in expected)
        == set((item.path, item.sha256) for item in observed)
    )


def complete_webm(body: bytes) -> None:
    """Pinned Playwright recordings finalize a finite WebM Segment length."""
    marker = bytes.fromhex("18538067")
    offset = body.find(marker, 0, 4096) + 4
    if offset < 4 or offset >= len(body) or body[offset] == 0:
        raise ValueError("invalid-webm-segment")
    width = 9 - body[offset].bit_length()
    size = int.from_bytes(body[offset : offset + width], "big") & ((1 << (7 * width)) - 1)
    if size == (1 << (7 * width)) - 1 or offset + width + size != len(body):
        raise ValueError("unfinished-or-truncated-webm")


async def decode_video(
    browser: Browser, path: Path, registry: SDKResources, deadline: float | None = None
) -> VideoEvidence:
    """Decode a frame with the same Chromium, never infer video health from size."""
    body = path.read_bytes()
    complete_webm(body)
    owner = registry
    deadline = deadline if deadline is not None else time.monotonic() + 30
    context = cast(
        BrowserContext,
        await owner.acquire("decode-context", "video-check-" + uuid4().hex, browser.new_context()),
    )
    entry = owner.entries[-1]
    try:
        page = await context.new_page()
        await page.set_content("<video muted></video>")
        data: dict[str, object] = await page.evaluate(
            """src => new Promise((resolve, reject) => {
              const v = document.querySelector('video');
              v.onerror = () => reject(new Error('video-decode-failed'));
              v.onloadeddata = () => {v.currentTime = Math.min(0.05, v.duration / 2);};
              v.onseeked = () => {
                const c = document.createElement('canvas'); c.width=v.videoWidth;
                c.height=v.videoHeight; const g=c.getContext('2d'); g.drawImage(v,0,0);
                const pixels=g.getImageData(0,0,c.width,c.height).data;
                resolve({duration:v.duration,width:v.videoWidth,height:v.videoHeight,
                         decoded_frame:pixels.some(value => value !== 0)});
              }; v.src=src;
            })""",
            "data:video/webm;base64," + base64.b64encode(body).decode("ascii"),
        )
        return VideoEvidence.model_validate(
            data
            | {
                "content": {"path": str(path), "sha256": hashlib.sha256(body).hexdigest()},
                "size": len(body),
            }
        )
    finally:
        closed = await protected(owner.close_one(entry, deadline))
        if not closed.accepted:
            raise ValueError("video-context-close-failed")
