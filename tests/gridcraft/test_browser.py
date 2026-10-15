"""Prerequisites only: released bridge hosting, never reporting acceptance."""

import asyncio
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from playwright.async_api import ConsoleMessage, Page

from craftreport.composition.app import open_application
from craftreport.interfaces.principal import PrincipalBoundary
from scripts.browser_verification import browser, deployment, process, release
from scripts.browser_verification.config import OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import CloseState, ContentIdentity, Succeeded
from scripts.browser_verification.evidence import Diagnostics, verify_loaded
from scripts.browser_verification.journey import ResourceRegistry
from scripts.browser_verification.process import CommandScope, execute, scope

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy/gridcraft-report"
ARCHIVE = "ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27"
EXPECTED = {
    ".js": "cd4d0aa76dfb703870a6b5dbf63c88217221ebb7aac5c491f51c0e1b2d8fcbd9",
    ".wasm": "d1f2cfa583aea14443f0f68ee55403c18296cae237d1cfa7a2fdc3d886d4eb74",
}
PARENT = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Prerequisite probe only</title><link rel="icon" href="data:,">
<style>html,body,iframe{margin:0;width:100%;height:100%;border:0}</style>
<iframe id="app" title="Released GridCraft"></iframe><script>
window.bridgeEvents=[];
const app=document.getElementById('app');
addEventListener('message',e=>{
 if(e.origin!==location.origin || e.source!==app.contentWindow) return;
 const d=e.data;
 if(!d || typeof d!=='object') return;
 if(d.type==='gridcraft:ready' && typeof d.version==='string' && d.version.length<32)
   window.bridgeEvents.push({type:d.type,version:d.version});
 if(d.type==='gridcraft:failed') window.bridgeEvents.push({type:d.type});
});
app.src='/app/index.html?host=parent';
</script></html>"""


def test_reviewed_dependencies_are_locked_and_importable() -> None:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    selected = {"xlsxwriter": "3.2.9", "openpyxl": "3.1.5", "playwright": "1.64.0"}
    dependencies = manifest["dependency-groups"]["dev"]
    for name, version in selected.items():
        assert f"{name}=={version}" in dependencies
        assert importlib.metadata.version(name) == version
        assert importlib.import_module(name) is not None


def test_same_origin_configuration_requires_explicit_roots_and_facade() -> None:
    recipe = (DEPLOY / "compose.yaml").read_text(encoding="utf-8")
    nginx = (DEPLOY / "nginx.conf").read_text(encoding="utf-8")
    for setting in ("CRAFT_WEB_ROOT", "CRAFT_PARENT_ROOT", "CRAFT_FACADE_ORIGIN"):
        assert "${" + setting + ":?" in recipe
    assert "location /facade/" in nginx
    assert "proxy_pass ${CRAFT_FACADE_ORIGIN}/;" in nginx
    assert "proxy_set_header Host $http_host;" in nginx
    assert "read_only: true" in recipe
    assert "build:" not in recipe


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


@contextmanager
def attached_compose(
    argv: list[str], state: deployment.DeploymentState, path: Path, *, exit_timeout: float = 15
) -> Generator[subprocess.Popen[str]]:
    owner = CommandScope(state.registry, state.processes, exit_timeout)
    identity = "windows-process-group:attached-compose:" + uuid4().hex
    child: subprocess.Popen[str] | None = None
    status: CloseState = "failed"
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as logs:
        token = state.registry.register("process", identity)
        assert token.acquisition_id is not None
        try:
            child = subprocess.Popen(
                argv,
                stdout=logs,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
            state.processes.append(child)
            state.registry.mark_acquired(token.token_id)
            status = "graceful"
            yield child
        except BaseException:
            status = "failed"
            raise
        finally:
            try:
                if child is not None:
                    child.wait(timeout=exit_timeout)
                    if child.returncode:
                        status = "failed"
            except subprocess.TimeoutExpired:
                status = "timed-out"
            finally:
                process.finish(owner, token.token_id, identity, token.acquisition_id, child, status)
                logs.seek(0)
                path.write_text(logs.read(65536), encoding="utf-8")


def wait_compose(child: subprocess.Popen[str], argv: list[str], deadline: float) -> None:
    while True:
        if child.poll() is not None:
            raise subprocess.CalledProcessError(child.returncode or 1, argv)
        if execute(argv[:-1] + ["ps", "--status", "running", "-q"], deadline):
            return
        release.remaining(deadline)
        time.sleep(min(0.1, release.remaining(deadline)))


def retain_console(page: Page, directory: Path, diagnostics: Diagnostics) -> None:
    messages: list[dict[str, str]] = []

    def capture(message: ConsoleMessage) -> None:
        if message.type in ("warning", "error") and len(messages) < 32:
            messages.append(
                {"type": message.type, "text": message.text[:2048], "stage": diagnostics.stage}
            )
            write_json(directory / "synthetic-console.json", messages)

    page.on("console", capture)


def compose_start(
    config: RunConfig,
    bundle: release.BundleIdentity,
    state: deployment.DeploymentState,
    facade: str,
    attached: ExitStack,
) -> deployment.DeploymentLease:
    root, selected = deployment.assets(bundle)
    selected = tuple(ContentIdentity(path="app/" + x.path, sha256=x.sha256) for x in selected)
    project = deployment.project_name(config.run_id)
    port = deployment.available(None)
    lease = deployment.DeploymentLease(
        resource_id=uuid4(),
        owner_run=config.run_id,
        mode="owned-wsl",
        project=project,
        origin=f"http://localhost:{port}",
        bind_address="127.0.0.1",
        port=port,
        build_sha256=ARCHIVE,
        assets=selected,
    )
    deadline = time.monotonic() + 90
    assert not deployment.containers(lease, deadline)
    assert not deployment.networks(lease, deadline)
    token = state.registry.register("deployment", project)
    lease = lease.model_copy(update={"resource_id": token.token_id})
    state.lease, state.acquisition_id = lease, token.acquisition_id
    parent = config.run_directory / "parent"
    (parent / "app").mkdir(parents=True)
    (parent / "index.html").write_text(PARENT, encoding="utf-8")
    override = config.run_directory / "ownership.json"
    write_json(
        override,
        {
            "services": {"web": {"labels": {deployment.LABEL: str(config.run_id)}}},
            "networks": {"default": {"labels": {deployment.LABEL: str(config.run_id)}}},
        },
    )
    env = [
        f"CRAFT_WEB_ROOT={deployment.linux_path(root, 'owned-wsl')}",
        f"CRAFT_PARENT_ROOT={deployment.linux_path(parent, 'owned-wsl')}",
        f"CRAFT_HTTP_PORT={port}",
        f"CRAFT_FACADE_ORIGIN={facade}",
    ]
    state.startup_uncertain = True
    argv = [
        "wsl.exe",
        "-d",
        "Debian",
        "--",
        "env",
        *env,
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        deployment.linux_path(DEPLOY / "compose.yaml", "owned-wsl"),
        "-f",
        deployment.linux_path(override, "owned-wsl"),
        "up",
    ]
    child = attached.enter_context(
        attached_compose(argv, state, config.run_directory / "compose.log")
    )
    wait_compose(child, argv, deadline)
    state.startup_uncertain = False
    state.container_ids = deployment.containers(lease, deadline)
    state.network_ids = deployment.networks(lease, deadline)
    assert len(state.container_ids) == 1
    assert deployment.owned(lease, state.container_ids[0], deadline)
    state.registry.mark_acquired(lease.resource_id)
    state.acquired = True
    return lease


async def observe_bridge(
    config: RunConfig,
    lease: deployment.DeploymentLease,
    state: browser.BrowserState,
) -> dict[str, object]:
    page = await browser.launch(config, state)
    assert state.browser and state.driver and state.context
    diagnostics = Diagnostics(lease.origin, lease.assets)
    diagnostics.warning_profile = (ARCHIVE, state.browser.version)
    state.diagnostics = diagnostics
    diagnostics.attach(page)
    retain_console(page, config.run_directory, diagnostics)
    await diagnostics.capture_network(await state.context.new_cdp_session(page))
    await page.goto(lease.origin, wait_until="networkidle")
    await page.wait_for_function("window.bridgeEvents.length > 0")
    messages: list[dict[str, str]] = await page.evaluate("window.bridgeEvents")
    assert messages == [{"type": "gridcraft:ready", "version": "0.7.0"}]
    frame = page.frame(url=lease.origin + "/app/index.html?host=parent")
    assert frame is not None
    await frame.locator("#gridcraft_loading").wait_for(state="hidden")
    await frame.locator("#gridcraft_canvas").wait_for(state="visible")
    renderer: str | None = await frame.evaluate("""() => {
      const gl=document.querySelector('#gridcraft_canvas').getContext('webgl2');
      if(!gl || gl.isContextLost()) return null;
      const i=gl.getExtension('WEBGL_debug_renderer_info');
      return String(gl.getParameter(i?i.UNMASKED_RENDERER_WEBGL:gl.RENDERER));
    }""")
    assert renderer
    assert verify_loaded(lease.assets, diagnostics.loaded())
    assert browser.profile_supported(
        ARCHIVE, state.browser.version, platform.system(), page.viewport_size
    )
    assert all(not d.fatal for d in diagnostics.events)
    proxy: dict[str, object] = await page.evaluate("""async () => {
      const r=await fetch('/facade/health/ready');
      return {status:r.status,body:await r.json()};
    }""")
    denied = await page.request.get(lease.origin + "/facade/v1/catalog")
    proxy["denied"] = denied.status
    assert proxy["status"] == 200 and proxy["denied"] == 401
    assert cast(dict[str, object], proxy["body"])["ready"] is True
    assert all(not d.fatal for d in diagnostics.events)
    await page.screenshot(path=str(config.run_directory / "ready.png"))
    return {
        "bridge": messages,
        "proxy": proxy,
        "parent_url": page.url,
        "frame_url": frame.url,
        "renderer": renderer,
        "browser_version": state.browser.version,
        "executable": state.driver.chromium.executable_path,
        "context_id": str(state.context_id),
        "page_id": str(state.page_id),
    }


def source_report() -> dict[str, object]:
    return {
        "requirements": ["1.1", "1.4", "6.4", "6.5", "6.6"],
        "scope": "prerequisite-only; no report, mutation or saved artifact verification",
        "headed": "MANUAL_VERIFY_REQUIRED",
        "python": platform.python_version(),
        "provider_scope": "existing synthetic temporary kernel fixtures; default-deny",
        "sdk_source_hashes": {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "scripts/browser_verification").glob("*.py"))
        },
        "source_hashes": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in (
                "tests/gridcraft/test_browser.py",
                "deploy/gridcraft-report/compose.yaml",
                "deploy/gridcraft-report/nginx.conf",
                "pyproject.toml",
                "uv.lock",
            )
        },
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ("xlsxwriter", "openpyxl", "et-xmlfile", "playwright", "pyee", "greenlet")
        },
    }


def resolved_bundle(config: RunConfig) -> release.BundleIdentity:
    identity = release.resolve_release(config)
    assert isinstance(identity, Succeeded), identity
    assert identity.payload.sha256 == ARCHIVE
    acquired = release.acquire(identity.payload, ROOT / "artifacts/browser-verification/cache")
    assert isinstance(acquired, Succeeded), acquired
    bundle = acquired.payload
    for asset in bundle.files:
        if Path(asset.path).suffix in EXPECTED:
            assert asset.sha256 == EXPECTED[Path(asset.path).suffix]
    write_json(config.run_directory / "bundle.json", bundle.model_dump(mode="json"))
    return bundle


async def readiness(
    config: RunConfig, monkeypatch: pytest.MonkeyPatch, *, observer_timeout: float = 90
) -> None:
    monkeypatch.setattr(sys, "path", [str(ROOT / "tests/kernel"), *sys.path])
    from fixture_host import HostFixture

    registry = ResourceRegistry(config.run_id)
    deployed = deployment.DeploymentState(registry)
    browsing = browser.BrowserState(registry)
    attached = ExitStack()
    report = source_report()
    try:
        with scope(CommandScope(registry, deployed.processes, 30)):
            report["source_revision"] = execute(["git", "rev-parse", "HEAD"], time.monotonic() + 15)
            gateway = execute(
                ["wsl.exe", "-d", "Debian", "--", "ip", "route", "show", "default"],
                time.monotonic() + 15,
            ).split()[2]
            bundle = resolved_bundle(config)
            fixture = HostFixture(monkeypatch)
            with socket.socket() as listener:
                listener.bind(("0.0.0.0", 0))
                listener.listen(128)
                port = listener.getsockname()[1]
                lease = compose_start(
                    config, bundle, deployed, f"http://{gateway}:{port}", attached
                )
                settings = replace(
                    fixture.settings,
                    bind_host="0.0.0.0",
                    selections=(),
                    principal=PrincipalBoundary("task2-deny"),
                    allowed_hosts=(lease.origin.removeprefix("http://"),),
                    allowed_origins=(lease.origin,),
                )
                async with open_application(settings, fixture.providers()) as application:
                    server = application.server(listener)
                    serving = asyncio.create_task(server.serve())
                    try:
                        async with asyncio.timeout(observer_timeout):
                            report.update(await observe_bridge(config, lease, browsing))
                    finally:
                        try:
                            if browsing.page and not browsing.page.is_closed():
                                await browsing.page.screenshot(
                                    path=str(config.run_directory / "final-state.png"), timeout=3000
                                )
                        finally:
                            server.request_shutdown()
                            await asyncio.wait_for(serving, timeout=20)
                            report["facade_shutdown"] = "awaited graceful server completion"
    finally:
        try:
            await browser.close(config, browsing)
        finally:
            try:
                if deployed.lease is not None:
                    deployment.close(deployed, 30)
            finally:
                attached.close()
        if browsing.diagnostics:
            browsing.diagnostics.write(config.run_directory / "diagnostics.json")
        report["cleanup"] = [x.model_dump(mode="json") for x in registry.findings]
        report["video"] = browsing.video.model_dump(mode="json") if browsing.video else None
        write_json(config.run_directory / "readiness.json", report)
    assert registry.findings and all(x.accepted for x in registry.findings)
    assert browsing.video and browsing.video.decoded_frame


@pytest.mark.integration
@pytest.mark.skipif(platform.system() != "Windows", reason="approved Windows headless profile")
def test_released_same_origin_bridge_prerequisites(monkeypatch: pytest.MonkeyPatch) -> None:
    config = RunConfig(
        deployment=OwnedDeployment(mode="owned-wsl"),
        headed=False,
        output_root=ROOT / "artifacts/gridcraft/task-2",
        trusted_release_sha256=ARCHIVE,
        trust_source="approved v0.7.0 Design",
    )
    config.run_directory.mkdir(parents=True)
    asyncio.run(readiness(config, monkeypatch))
