"""Startup evidence contracts, independently of HTTP service health."""

import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from PIL import Image, ImageDraw
from playwright.async_api import ConsoleMessage, Error, Page

from scripts.browser_verification import browser, journey
from scripts.browser_verification.config import ExternalDeployment, RunConfig
from scripts.browser_verification.contracts import ContentIdentity
from scripts.browser_verification.deployment import DeploymentLease
from scripts.browser_verification.evidence import (
    WARNING_PROFILE,
    WARNINGS,
    Diagnostics,
    verify_loaded,
)


def assets() -> tuple[ContentIdentity, ...]:
    return tuple(
        ContentIdentity(path=name, sha256="a" * 64) for name in ("index.html", "app.js", "app.wasm")
    )


def test_browser_requires_every_loaded_build_asset() -> None:
    assert verify_loaded(assets(), assets())


@pytest.mark.parametrize("fault", ["missing", "different", "empty"])
def test_http_health_cannot_replace_browser_build(fault: str) -> None:
    observed = assets()[:-1] if fault == "missing" else ()
    if fault == "different":
        observed = (*assets()[:-1], ContentIdentity(path="app.wasm", sha256="b" * 64))
    assert not verify_loaded(assets(), observed)


def test_asset_order_is_irrelevant_but_duplicate_and_missing_types_fail() -> None:
    assert verify_loaded(assets(), tuple(reversed(assets())))
    assert not verify_loaded(assets(), (*assets(), assets()[0]))
    assert not verify_loaded(assets()[:1], assets()[:1])


@pytest.mark.parametrize("kind", ["warning", "error"])
def test_arbitrary_console_content_never_leaks(tmp_path: Path, kind: str) -> None:
    diagnostics = Diagnostics("http://localhost:9000", assets())
    diagnostics.console(
        cast(ConsoleMessage, SimpleNamespace(type=kind, text="private token=secret"))
    )
    diagnostics.write(tmp_path / "diagnostics.json")
    assert diagnostics.events[0].fatal
    assert "secret" not in (tmp_path / "diagnostics.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("profile", [WARNING_PROFILE, ("b" * 64, "156.0.8078.4"), None])
def test_warning_allowances_are_exact_and_build_scoped(profile: tuple[str, str] | None) -> None:
    diagnostics = Diagnostics("http://localhost:9000", assets(), warning_profile=profile)
    for text in WARNINGS:
        diagnostics.console(cast(ConsoleMessage, SimpleNamespace(type="warning", text=text)))
    assert all(event.fatal == (profile != WARNING_PROFILE) for event in diagnostics.events)
    diagnostics.console(
        cast(ConsoleMessage, SimpleNamespace(type="warning", text="No available adapters. "))
    )
    assert diagnostics.events[-1].fatal


def test_safe_asset_identity_excludes_untrusted_paths_and_queries() -> None:
    diagnostics = Diagnostics("http://localhost:9000", assets())
    assert diagnostics.asset("http://localhost:9000/app.wasm?token=secret") == "app.wasm"
    assert diagnostics.asset("http://evil.example/app.wasm") is None
    assert diagnostics.asset("http://localhost:9000/private.xlsx") is None


class Network:
    def __init__(self, body: bytes, status: str = "body") -> None:
        self.body = body
        self.status = status
        self.calls: list[str] = []

    async def send(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        self.calls.append(method)
        if method == "Fetch.getResponseBody":
            if self.status == "error":
                raise Error("secret response error")
            return {"body": base64.b64encode(self.body).decode("ascii"), "base64Encoded": True}
        return {}


@pytest.mark.parametrize("status", [200, 404])
def test_actual_browser_response_is_hashed_then_continued_unchanged(status: int) -> None:
    diagnostics = Diagnostics("http://localhost:9000", assets())
    network = Network(b"real response bytes")
    event: dict[str, object] = {
        "requestId": "one",
        "request": {"url": "http://localhost:9000/app.wasm"},
        "responseStatusCode": status,
    }
    asyncio.run(diagnostics.inspect_response(event, network))
    assert network.calls[-1] == "Fetch.continueRequest"
    assert not any("fulfill" in call.lower() for call in network.calls)
    if status == 200:
        assert diagnostics.loaded()[0].sha256 == hashlib.sha256(network.body).hexdigest()
    else:
        assert not diagnostics.loaded()
        assert diagnostics.events[0].fatal


def test_body_capture_failure_cannot_pass_or_leak() -> None:
    diagnostics = Diagnostics("http://localhost:9000", assets())
    network = Network(b"", "error")
    asyncio.run(
        diagnostics.inspect_response(
            {
                "requestId": "one",
                "responseStatusCode": 200,
                "request": {"url": "http://localhost:9000/app.wasm"},
            },
            network,
        )
    )
    assert not diagnostics.loaded()
    assert diagnostics.events[0].fatal
    assert "secret" not in diagnostics.events[0].model_dump_json()
    assert network.calls[-1] == "Fetch.continueRequest"


@pytest.mark.parametrize("column", [0, 1])
def test_selection_oracle_checks_the_expected_cell_not_generic_pixels(column: int) -> None:
    image = Image.new("RGB", (1600, 1100), "white")
    ImageDraw.Draw(image).line((28 + column * 51, 215, 75 + column * 51, 215), fill=(0, 150, 50))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    assert browser.selected_cell(stream.getvalue(), column)
    assert not browser.selected_cell(stream.getvalue(), 1 - column)


@pytest.mark.parametrize("changed", ["none", "build", "browser", "os", "viewport"])
def test_uncalibrated_profile_cannot_reach_grid_input(changed: str) -> None:
    build, version = WARNING_PROFILE
    if changed == "build":
        build = "b" * 64
    if changed == "browser":
        version = "157.0.0"
    viewport = browser.VIEWPORT.copy()
    if changed == "viewport":
        viewport["width"] = 1280
    assert browser.profile_supported(
        build, version, "Linux" if changed == "os" else "Windows", viewport
    ) == (changed == "none")


def test_unavailable_headed_launch_stays_blocked_without_headless_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = RunConfig(
        deployment=ExternalDeployment(
            origin="http://localhost:9000", build_manifest=tmp_path / "manifest.json"
        ),
        output_root=tmp_path,
    )
    lease = DeploymentLease(
        resource_id=uuid4(),
        owner_run=config.run_id,
        mode="external",
        project=None,
        origin="http://localhost:9000",
        bind_address=None,
        port=None,
        build_sha256="a" * 64,
        assets=assets(),
    )
    calls: list[bool] = []

    async def unavailable(selected: RunConfig, state: browser.BrowserState) -> Page:
        calls.append(selected.headed)
        raise Error("Display unavailable; secret-host-detail")

    monkeypatch.setattr(browser, "launch", unavailable)
    result = asyncio.run(journey.startup(config, lease, journey.ResourceRegistry(config.run_id)))
    assert calls == [True]
    assert result.readiness.status == "rejected"
    assert not result.cleanup and result.video is None
    assert len(result.unexecuted) == 4
    data = json.loads((config.run_directory / "startup.json").read_text(encoding="utf-8"))
    assert data["headed"] and "secret" not in json.dumps(data)
