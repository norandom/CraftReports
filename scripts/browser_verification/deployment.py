"""Released static deployment lifecycle and independently observed served bytes."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Literal, Protocol
from uuid import UUID, uuid4

import httpx

from .config import RunConfig
from .contracts import (
    CleanupFinding,
    ContentIdentity,
    Origin,
    Outcome,
    Rejected,
    StageFinding,
    Succeeded,
    Value,
)
from .release import BundleIdentity, remaining

RECIPE = Path(__file__).resolve().parents[2] / "docs/deployment/gridcraft/compose.yaml"
LABEL = "io.craftreport.browser-verification.run"
Mode = Literal["owned-wsl", "owned-linux", "external"]


class DeploymentError(ValueError):
    """Fixed public diagnostic without external response or manifest content."""


class Token(Protocol):
    @property
    def token_id(self) -> UUID: ...


class Registry(Protocol):
    @property
    def run_id(self) -> UUID: ...
    def register(self, kind: Literal["deployment"], identity: str) -> Token: ...
    def mark_acquired(self, token_id: UUID) -> object: ...
    def record_close(
        self, token_id: UUID, state: Literal["graceful", "forced", "failed"]
    ) -> object: ...


class DeploymentLease(Value):
    resource_id: UUID
    owner_run: UUID
    mode: Mode
    project: str | None
    origin: Origin
    bind_address: str | None
    port: int | None
    build_sha256: str
    assets: tuple[ContentIdentity, ...]


@dataclass
class DeploymentState:
    registry: Registry
    lease: DeploymentLease | None = None
    container_ids: tuple[str, ...] = ()
    network_ids: tuple[str, ...] = ()
    startup_uncertain: bool = False


def project_name(run_id: UUID) -> str:
    return "craftreport-browser-" + run_id.hex


def command(mode: Mode) -> list[str]:
    return ["wsl.exe", "-d", "Debian", "--", "docker"] if mode == "owned-wsl" else ["docker"]


def linux_path(path: PurePath, mode: Mode) -> str:
    if not path.is_absolute():
        raise DeploymentError("absolute deployment path required")
    if mode == "owned-wsl":
        if not path.drive or len(path.drive) != 2:
            raise DeploymentError("WSL requires a local drive path")
        return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])
    if path.drive:
        raise DeploymentError("native Linux requires Linux paths")
    return path.as_posix()


def run(mode: Mode, arguments: list[str], deadline: float) -> str:
    result = subprocess.run(
        command(mode) + arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=remaining(deadline),
        check=True,
    )
    return result.stdout.strip()


def containers(lease: DeploymentLease, deadline: float) -> tuple[str, ...]:
    return tuple(
        run(
            lease.mode,
            [
                "ps",
                "-aq",
                "--no-trunc",
                "--filter",
                "label=com.docker.compose.project=" + str(lease.project),
            ],
            deadline,
        ).split()
    )


def networks(lease: DeploymentLease, deadline: float) -> tuple[str, ...]:
    return tuple(
        run(
            lease.mode,
            [
                "network",
                "ls",
                "-q",
                "--no-trunc",
                "--filter",
                "label=com.docker.compose.project=" + str(lease.project),
            ],
            deadline,
        ).split()
    )


def close_networks(
    state: DeploymentState, lease: DeploymentLease, deadline: float
) -> tuple[str, ...]:
    state.network_ids = tuple(dict.fromkeys((*state.network_ids, *networks(lease, deadline))))
    live = run(lease.mode, ["network", "ls", "-q", "--no-trunc"], deadline).split()
    for identity in state.network_ids:
        if identity not in live:
            continue
        data = json.loads(run(lease.mode, ["network", "inspect", identity], deadline))[0]
        if (
            data["Id"] != identity
            or data["Labels"].get(LABEL) != str(lease.owner_run)
            or data["Labels"].get("com.docker.compose.project") != lease.project
        ):
            raise DeploymentError("network ownership mismatch")
        run(lease.mode, ["network", "rm", identity], deadline)
    live = run(lease.mode, ["network", "ls", "-q", "--no-trunc"], deadline).split()
    return tuple(identity for identity in state.network_ids if identity in live) + networks(
        lease, deadline
    )


def owned(lease: DeploymentLease, container: str, deadline: float) -> bool:
    data = json.loads(run(lease.mode, ["inspect", container], deadline))[0]
    labels = data["Config"]["Labels"]
    return (
        data["Id"] == container
        and labels.get(LABEL) == str(lease.owner_run)
        and labels.get("com.docker.compose.project") == lease.project
    )


def assets(bundle: BundleIdentity) -> tuple[Path, tuple[ContentIdentity, ...]]:
    indexes = [item for item in bundle.files if Path(item.path).name == "index.html"]
    if len(indexes) != 1:
        raise DeploymentError("unique index.html required")
    relative = Path(indexes[0].path).parent
    root = bundle.root / relative
    selected = tuple(
        ContentIdentity(path=Path(item.path).relative_to(relative).as_posix(), sha256=item.sha256)
        for item in bundle.files
        if Path(item.path).parent == relative
        and Path(item.path).suffix in (".html", ".js", ".wasm")
    )
    if {Path(item.path).suffix for item in selected} != {".html", ".js", ".wasm"}:
        raise DeploymentError("required build assets missing")
    return root, selected


def verify(
    origin: str, selected: tuple[ContentIdentity, ...], deadline: float, client: httpx.Client
) -> None:
    for item in selected:
        digest = hashlib.sha256()
        size = 0
        with client.stream(
            "GET",
            origin + "/" + item.path,
            headers={"Cache-Control": "no-cache"},
            follow_redirects=False,
            timeout=remaining(deadline),
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes(65536):
                remaining(deadline)
                size += len(chunk)
                if size > 64 * 1024 * 1024:
                    raise DeploymentError("served asset size bound exceeded")
                digest.update(chunk)
        if digest.hexdigest() != item.sha256:
            raise DeploymentError("served application build mismatch")


def available(port: int | None) -> int:
    with socket.socket() as probe:
        probe.bind(("0.0.0.0", port or 0))
        chosen = probe.getsockname()[1]
    if chosen == 8871:
        raise DeploymentError("probe port forbidden")
    return chosen


def start(
    config: RunConfig, bundle: BundleIdentity, state: DeploymentState, deadline: float
) -> DeploymentLease:
    selection = config.deployment
    root, selected = assets(bundle)
    if state.lease is not None or state.registry.run_id != config.run_id:
        raise DeploymentError("deployment state is already acquired or belongs to another run")
    if selection.mode == "external":
        manifest = BundleIdentity.model_validate_json(
            selection.build_manifest.read_text(encoding="utf-8")
        )
        if manifest.release != bundle.release or manifest.files != bundle.files:
            raise DeploymentError("external build manifest mismatch")
        return DeploymentLease(
            resource_id=uuid4(),
            owner_run=config.run_id,
            mode="external",
            project=None,
            origin=selection.origin,
            bind_address=None,
            port=None,
            build_sha256=bundle.release.sha256,
            assets=selected,
        )
    if root != root.resolve():
        raise DeploymentError("mount follows a symlink")
    for item in selected:
        path = root / item.path
        if (
            not path.resolve().is_relative_to(bundle.root.resolve())
            or path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != item.sha256
        ):
            raise DeploymentError("mount asset mismatch")
    port = available(selection.port)
    project = project_name(config.run_id)
    lease = DeploymentLease(
        resource_id=uuid4(),
        owner_run=config.run_id,
        mode=selection.mode,
        project=project,
        origin=f"http://localhost:{port}",
        bind_address=selection.bind_address,
        port=port,
        build_sha256=bundle.release.sha256,
        assets=selected,
    )
    if containers(lease, deadline) or networks(lease, deadline):
        raise DeploymentError("existing deployment project conflict")
    # Register the unique project before up: timeout may leave late-created containers.
    token = state.registry.register("deployment", project)
    lease = lease.model_copy(update={"resource_id": token.token_id})
    state.lease = lease
    override = config.run_directory / "deployment.yaml"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text(
        json.dumps(
            {
                "services": {"web": {"labels": {LABEL: str(config.run_id)}}},
                "networks": {"default": {"labels": {LABEL: str(config.run_id)}}},
            }
        ),
        encoding="utf-8",
    )
    arguments = [
        "compose",
        "-p",
        project,
        "-f",
        linux_path(RECIPE, selection.mode),
        "-f",
        linux_path(override, selection.mode),
        "up",
        "-d",
    ]
    # Compose interpolation is supplied inside the Linux invocation, never host shell text.
    env = [
        "env",
        f"CRAFT_WEB_ROOT={linux_path(root, selection.mode)}",
        f"CRAFT_HTTP_BIND={selection.bind_address}",
        f"CRAFT_HTTP_PORT={port}",
    ]
    prefix = command(selection.mode)
    state.startup_uncertain = True
    subprocess.run(
        prefix[:-1] + env + [prefix[-1]] + arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=remaining(deadline),
        check=True,
    )
    state.startup_uncertain = False
    state.container_ids = containers(lease, deadline)
    state.network_ids = networks(lease, deadline)
    validate_service(lease, state.container_ids, root, deadline)
    state.registry.mark_acquired(lease.resource_id)
    return lease


def validate_service(
    lease: DeploymentLease, ids: tuple[str, ...], root: Path, deadline: float
) -> None:
    if len(ids) != 1 or not owned(lease, ids[0], deadline):
        raise DeploymentError("created deployment ownership mismatch")
    data = json.loads(run(lease.mode, ["inspect", ids[0]], deadline))[0]
    mounts = data["Mounts"]
    if not any(
        item["Destination"] == "/usr/share/nginx/html"
        and item["Source"] == linux_path(root, lease.mode)
        and not item["RW"]
        for item in mounts
    ):
        raise DeploymentError("deployment mount mismatch")
    ports = data["NetworkSettings"]["Ports"].get("80/tcp", [])
    if not any(
        item["HostPort"] == str(lease.port) and item["HostIp"] == lease.bind_address
        for item in ports
    ):
        raise DeploymentError("deployment port mismatch")


def prepare(
    config: RunConfig,
    bundle: BundleIdentity,
    state: DeploymentState,
    *,
    client: httpx.Client | None = None,
) -> Outcome[DeploymentLease]:
    try:
        if client is None:
            with httpx.Client(headers={"Cache-Control": "no-cache"}) as connection:
                return prepare(config, bundle, state, client=connection)
        deadline = time.monotonic() + config.bounds.readiness
        lease = start(config, bundle, state, deadline)
        state.lease = lease
        while True:
            try:
                verify(lease.origin, lease.assets, deadline, client)
                break
            except httpx.HTTPError:
                remaining(deadline)
                time.sleep(min(0.1, remaining(deadline)))
        return Succeeded(payload=lease)
    except (ValueError, OSError, httpx.HTTPError, subprocess.SubprocessError) as error:
        reason = (
            str(error)
            if isinstance(error, DeploymentError)
            else "deployment startup or reachability failed"
        )
        return Rejected(
            finding=StageFinding(
                stage="deployment",
                requirements=("1.4", "2.2", "2.3"),
                status="blocked",
                observed=(reason,),
            )
        )


def stop_container(
    lease: DeploymentLease, container: str, deadline: float
) -> tuple[Literal["graceful", "forced", "failed"], int]:
    if not owned(lease, container, deadline):
        raise DeploymentError("cleanup ownership mismatch")
    run(lease.mode, ["stop", "--time", str(max(1, int(remaining(deadline)))), container], deadline)
    stopped = json.loads(run(lease.mode, ["inspect", container], deadline))[0]["State"]
    status: Literal["graceful", "forced", "failed"] = "graceful"
    if stopped["ExitCode"] == 137 or stopped["OOMKilled"] or stopped["Running"]:
        status = "forced"
    elif stopped["ExitCode"] != 0:
        status = "failed"
    run(lease.mode, ["rm", container], deadline)
    return status, stopped["ExitCode"]


def close(state: DeploymentState, bound: float) -> CleanupFinding:
    lease = state.lease
    if lease is None:
        raise DeploymentError("no deployment acquired")
    survivors: tuple[str, ...] = ()
    status: Literal["graceful", "forced", "failed"] = "graceful"
    exit_status: int | None = None
    try:
        deadline = time.monotonic() + bound
        if lease.project is not None:
            ids = containers(lease, deadline)
            state.container_ids = tuple(dict.fromkeys((*state.container_ids, *ids)))
            live = run(lease.mode, ["ps", "-aq", "--no-trunc"], deadline).split()
            for container in state.container_ids:
                if container in live:
                    stopped_status, exit_status = stop_container(lease, container, deadline)
                    if stopped_status != "graceful":
                        status = stopped_status
            live = run(lease.mode, ["ps", "-aq", "--no-trunc"], deadline).split()
            survivors = tuple(identity for identity in state.container_ids if identity in live)
            survivors += containers(lease, deadline) + close_networks(state, lease, deadline)
            if survivors:
                status = "failed"
    except (ValueError, OSError, subprocess.SubprocessError):
        status = "failed"
        survivors = (*state.container_ids, *state.network_ids) or (str(lease.project),)
    if state.startup_uncertain:
        # A snapshot cannot prove quiescence after an ambiguous Compose request.
        status = "failed"
        survivors = tuple(dict.fromkeys((*survivors, str(lease.project))))
    if lease.project is not None:
        state.registry.record_close(lease.resource_id, status)
    return CleanupFinding(
        resource_id=lease.resource_id,
        owner_run=lease.owner_run,
        identity=lease.project or lease.origin,
        status=status,
        survivors=survivors,
        exit_status=exit_status,
        final_video_state="not-required",
    )
