"""Identity/ownership faults are separate from retained real deployment smoke evidence."""

import hashlib
import json
import socket
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

import httpx
import pytest

from scripts.browser_verification import deployment as d
from scripts.browser_verification.config import ExternalDeployment, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import ContentIdentity, Rejected, Succeeded
from scripts.browser_verification.journey import ResourceRegistry
from scripts.browser_verification.release import BundleIdentity
from tests.browser_verification.test_release import selected


@pytest.fixture
def bundle(tmp_path: Path) -> BundleIdentity:
    root = tmp_path / "bundle"
    (root / "nested").mkdir(parents=True)
    files: list[ContentIdentity] = []
    for name in ("index.html", "app.js", "app.wasm"):
        data = ("synthetic " + name).encode()
        (root / "nested" / name).write_bytes(data)
        files.append(
            ContentIdentity(path="nested/" + name, sha256=hashlib.sha256(data).hexdigest())
        )
    return BundleIdentity(
        release=selected(tmp_path, b"synthetic archive"),
        archive=tmp_path / "archive.zip",
        root=root,
        files=tuple(files),
    )


def client(bundle: BundleIdentity, wrong: bool = False) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"wrong"
                if wrong
                else (bundle.root / "nested" / request.url.path.lstrip("/")).read_bytes(),
            )
        )
    )


def test_external_observation(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "build.json"
    manifest.write_text(bundle.model_dump_json(), encoding="utf-8")
    config = RunConfig(
        deployment=ExternalDeployment(origin="http://localhost:8871", build_manifest=manifest),
        output_root=tmp_path,
    )
    state = d.DeploymentState(ResourceRegistry(config.run_id))

    def forbidden(*args: object, **kwargs: object) -> str:
        pytest.fail("external deployment must never invoke docker")

    monkeypatch.setattr(d, "run", forbidden)
    with client(bundle) as connection:
        result = d.prepare(config, bundle, state, client=connection)
    assert isinstance(result, Succeeded)
    assert result.payload.project is None
    assert isinstance(state.registry, ResourceRegistry)
    assert not state.registry.tokens
    assert d.close(state, 3).status == "graceful"


@pytest.mark.parametrize("fault", ["manifest", "build", "unreachable"])
def test_external_rejection(tmp_path: Path, bundle: BundleIdentity, fault: str) -> None:
    manifest = tmp_path / "build.json"
    value = bundle.model_dump(mode="json")
    if fault == "manifest":
        value["release"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(value), encoding="utf-8")
    config = RunConfig(
        deployment=ExternalDeployment(origin="http://localhost:9000", build_manifest=manifest),
        output_root=tmp_path,
    )
    state = d.DeploymentState(ResourceRegistry(config.run_id))
    with client(bundle, wrong=fault == "build") as connection:
        if fault == "unreachable":
            config = config.model_copy(
                update={"bounds": config.bounds.model_copy(update={"readiness": 0.01})}
            )
            connection.close()
            connection = httpx.Client(
                transport=httpx.MockTransport(lambda request: httpx.Response(503))
            )
        result = d.prepare(config, bundle, state, client=connection)
        connection.close()
    assert isinstance(result, Rejected)
    assert isinstance(state.registry, ResourceRegistry)
    assert not state.registry.tokens


class Runtime:
    def __init__(self, config: RunConfig, bundle: BundleIdentity) -> None:
        self.config = config
        self.root = bundle.root / "nested"
        self.present = False
        self.network = False
        self.foreign = False
        self.port = "9000"
        self.calls: list[list[str]] = []
        self.id = "a" * 64
        self.network_id = "b" * 64

    def up(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        self.present = True
        self.network = True
        return subprocess.CompletedProcess(argv, 0, "")

    def run(self, mode: d.Mode, argv: list[str], deadline: float) -> str:
        self.calls.append(argv)
        labels = {
            d.LABEL: "foreign" if self.foreign else str(self.config.run_id),
            "com.docker.compose.project": d.project_name(self.config.run_id),
        }
        if argv[0] == "ps":
            return self.id if self.present else ""
        if argv[:2] == ["network", "ls"]:
            return self.network_id if self.network else ""
        if argv[:2] == ["network", "inspect"]:
            return json.dumps([{"Id": self.network_id, "Labels": labels}])
        if argv[:2] == ["network", "rm"]:
            self.network = False
        if argv[0] == "inspect":
            return json.dumps(
                [
                    {
                        "Id": self.id,
                        "Config": {"Labels": labels},
                        "Mounts": [
                            {
                                "Destination": "/usr/share/nginx/html",
                                "Source": d.linux_path(self.root, mode),
                                "RW": False,
                            }
                        ],
                        "State": {"ExitCode": 0, "OOMKilled": False, "Running": False},
                        "NetworkSettings": {
                            "Ports": {"80/tcp": [{"HostPort": self.port, "HostIp": "127.0.0.1"}]}
                        },
                    }
                ]
            )
        if argv[0] == "rm":
            self.present = False
        return ""


def setup(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> tuple[RunConfig, d.DeploymentState, Runtime]:
    config = RunConfig(
        deployment=OwnedDeployment(
            mode="owned-wsl" if tmp_path.drive else "owned-linux", port=9000
        ),
        output_root=tmp_path,
    )
    state = d.DeploymentState(ResourceRegistry(config.run_id))
    runtime = Runtime(config, bundle)

    def port_available(port: int | None) -> int:
        return 9000

    monkeypatch.setattr(d, "available", port_available)
    monkeypatch.setattr(d, "run", runtime.run)
    monkeypatch.setattr(d.subprocess, "run", runtime.up)
    return config, state, runtime


def test_owned_and_exact_cleanup(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)
    with client(bundle) as connection:
        result = d.prepare(config, bundle, state, client=connection)
    assert isinstance(result, Succeeded)
    assert result.payload.bind_address == "127.0.0.1"
    assert result.payload.origin == "http://localhost:9000"
    assert isinstance(state.registry, ResourceRegistry)
    assert state.registry.tokens[0].acquisition == "acquired"
    prefix = (
        ["wsl.exe", "-d", "Debian", "--", "env"]
        if config.deployment.mode == "owned-wsl"
        else ["env"]
    )
    startup = next(argv for argv in runtime.calls if "compose" in argv)
    assert startup[: len(prefix)] == prefix
    assert startup[len(prefix) + 3] == "docker"
    assert d.close(state, 5).status == "graceful"
    assert not runtime.present and not runtime.network
    assert ["rm", runtime.id] in runtime.calls
    assert not any("down" in argv or "8871" in argv for argv in runtime.calls)


@pytest.mark.parametrize("fault", ["project", "port", "build", "labels", "up-timeout", "mount"])
def test_owned_rejections_retain_partial_ownership(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)
    if fault == "project":
        runtime.present = True
    if fault == "port":
        runtime.port = "9001"
    if fault == "labels":
        runtime.foreign = True
    if fault == "mount":
        (bundle.root / "nested/index.html").write_bytes(b"corrupt")
    if fault == "up-timeout":

        def timeout(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            runtime.up(argv)
            raise subprocess.TimeoutExpired(argv, 1)

        monkeypatch.setattr(d.subprocess, "run", timeout)
    with client(bundle, wrong=fault == "build") as connection:
        result = d.prepare(config, bundle, state, client=connection)
    assert isinstance(result, Rejected)
    assert isinstance(state.registry, ResourceRegistry)
    if fault in ("project", "mount"):
        assert state.lease is None and not state.registry.tokens
    else:
        assert state.lease is not None and state.registry.tokens
        assert d.close(state, 5).status == (
            "failed" if fault in ("labels", "up-timeout") else "graceful"
        )
        if fault == "labels":
            assert runtime.present
            assert not any(argv[0] in ("rm", "stop") for argv in runtime.calls)


def test_cleanup_survivor_is_failure(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)
    with client(bundle) as connection:
        assert isinstance(d.prepare(config, bundle, state, client=connection), Succeeded)
    original = runtime.run

    def survivor(mode: d.Mode, argv: list[str], deadline: float) -> str:
        return "" if argv[0] == "rm" else original(mode, argv, deadline)

    monkeypatch.setattr(d, "run", survivor)
    result = d.close(state, 5)
    assert result.status == "failed" and runtime.id in result.survivors


def test_available_port_conflict() -> None:
    with socket.socket() as listener:
        listener.bind(("0.0.0.0", 0))
        with pytest.raises(OSError):
            d.available(listener.getsockname()[1])


def test_linux_path_and_probe_preserved() -> None:
    assert (
        d.linux_path(PureWindowsPath("D:/Source/GridDash"), "owned-wsl") == "/mnt/d/Source/GridDash"
    )
    assert d.command("owned-wsl") == ["wsl.exe", "-d", "Debian", "--", "docker"]
    assert d.command("owned-linux") == ["docker"]
    assert d.linux_path(PurePosixPath("/opt/gridcraft"), "owned-linux") == "/opt/gridcraft"
    assert d.project_name(uuid4()) != d.project_name(uuid4())
    with pytest.raises(ValueError):
        OwnedDeployment(mode="owned-wsl", port=8871)


def test_recorded_container_label_change_is_not_lost(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)
    with client(bundle) as connection:
        assert isinstance(d.prepare(config, bundle, state, client=connection), Succeeded)
    runtime.foreign = True
    original = runtime.run

    def changed(mode: d.Mode, argv: list[str], deadline: float) -> str:
        return "" if argv[0] == "ps" and "--filter" in argv else original(mode, argv, deadline)

    monkeypatch.setattr(d, "run", changed)
    result = d.close(state, 5)
    assert result.status == "failed" and runtime.id in result.survivors
    assert runtime.present


def test_forced_stop_cannot_pass(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)
    with client(bundle) as connection:
        assert isinstance(d.prepare(config, bundle, state, client=connection), Succeeded)
    original = runtime.run

    def forced(mode: d.Mode, argv: list[str], deadline: float) -> str:
        value = original(mode, argv, deadline)
        if argv[0] == "inspect":
            data = json.loads(value)
            data[0]["State"]["ExitCode"] = 137
            return json.dumps(data)
        return value

    monkeypatch.setattr(d, "run", forced)
    assert d.close(state, 5).status == "forced"
    assert isinstance(state.registry, ResourceRegistry)
    assert state.registry.tokens[0].close_state == "forced"


def test_delayed_creation_after_startup_timeout_keeps_cleanup_unresolved(
    tmp_path: Path, bundle: BundleIdentity, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, runtime = setup(tmp_path, bundle, monkeypatch)

    def delayed(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        # Model the daemon completing its request after the CLI timed out.
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(d.subprocess, "run", delayed)
    with client(bundle) as connection:
        assert isinstance(d.prepare(config, bundle, state, client=connection), Rejected)
    assert not runtime.present and not runtime.network
    cleanup = d.close(state, 5)
    # The empty snapshot is not proof that the daemon cannot create resources later.
    runtime.present = True
    runtime.network = True
    assert cleanup.status == "failed"
    assert d.project_name(config.run_id) in cleanup.survivors
    assert isinstance(state.registry, ResourceRegistry)
    assert state.registry.pending_cleanup[0].identity == d.project_name(config.run_id)
    assert state.registry.pending_cleanup[0].acquisition == "partial"
    assert runtime.present and runtime.network
