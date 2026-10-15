"""Retained native command boundary for the deployment owner."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid4

from .contracts import CleanupFinding, CloseState


class Token(Protocol):
    @property
    def token_id(self) -> UUID: ...
    @property
    def acquisition_id(self) -> UUID | None: ...


class Registry(Protocol):
    @property
    def run_id(self) -> UUID: ...
    def register(self, kind: Literal["deployment", "process"], identity: str) -> Token: ...
    def mark_acquired(self, token_id: UUID) -> object: ...
    def record_close(
        self,
        token_id: UUID,
        state: CloseState,
    ) -> object: ...
    def record_finding(self, finding: CleanupFinding) -> None: ...


@dataclass
class CommandScope:
    registry: Registry
    handles: list[subprocess.Popen[str]]
    cleanup_bound: float
    cleanup_deadline: float | None = None


_scope: ContextVar[CommandScope] = ContextVar("deployment_commands")


@contextmanager
def scope(owner: CommandScope) -> Generator[None]:
    token = _scope.set(owner)
    try:
        yield
    finally:
        _scope.reset(token)


def execute(argv: list[str], deadline: float) -> str:
    owner = _scope.get()
    acquisition = uuid4()
    platform = "windows-process-group" if os.name == "nt" else "linux-session"
    token = owner.registry.register("process", platform + ":" + str(acquisition))
    assert token.acquisition_id is not None
    child: subprocess.Popen[str] | None = None
    status: CloseState = "failed"
    try:
        if deadline <= time.monotonic():
            raise subprocess.TimeoutExpired(argv, 0)
        child = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
        owner.handles.append(child)
        owner.registry.mark_acquired(token.token_id)
        stdout, stderr = child.communicate(timeout=max(0.001, deadline - time.monotonic()))
        if child.returncode:
            raise subprocess.CalledProcessError(child.returncode, argv, stdout, stderr)
        status = "graceful"
        return stdout.strip()
    except subprocess.TimeoutExpired:
        status = "timed-out"
        raise
    finally:
        finish(
            owner,
            token.token_id,
            platform + ":" + str(acquisition),
            token.acquisition_id,
            child,
            status,
        )


def settle(child: subprocess.Popen[str], deadline: float) -> bool:
    """A terminate/kill request is force even when its later exit is observed."""
    if child.poll() is not None:
        return False
    if os.name == "nt":
        child.terminate()
    else:
        os.killpg(child.pid, signal.SIGTERM)
    try:
        child.communicate(timeout=max(0.001, (deadline - time.monotonic()) / 2))
    except subprocess.TimeoutExpired:
        child.kill() if os.name == "nt" else os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=max(0.001, deadline - time.monotonic()))
    return True


def finish(
    owner: CommandScope,
    resource_id: UUID,
    identity: str,
    acquisition: UUID,
    child: subprocess.Popen[str] | None,
    status: CloseState,
) -> None:
    started = time.monotonic()
    deadline = min(started + owner.cleanup_bound, owner.cleanup_deadline or float("inf"))
    close_id = uuid4()
    force = child is not None and child.poll() is None
    if force and child is not None:
        try:
            force = settle(child, deadline)
        except (OSError, subprocess.SubprocessError, KeyboardInterrupt):
            status = "unresolved"
    code = child.poll() if child is not None else None
    if force and status not in ("unresolved", "timed-out"):
        status = "forced"
    finding = CleanupFinding(
        resource_id=resource_id,
        owner_run=owner.registry.run_id,
        identity=identity,
        status=status,
        exit_status=code,
        resource_kind="process",
        native_pid=child.pid if child else None,
        acquisition_id=acquisition,
        close_id=close_id,
        mechanism="observed-exit",
        started=started,
        deadline=deadline,
        finished=time.monotonic(),
        acquisition_state="acquired" if child else "failed",
        requested_force=force,
        observed_force=code is not None and code < 0,
        survivors=(str(child.pid),) if child is not None and code is None else (),
        final_video_state="not-required",
    )
    owner.registry.record_finding(finding)
