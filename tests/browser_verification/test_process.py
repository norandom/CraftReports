"""Real native handles exercise the same subprocess boundary as Deployment."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest

from scripts.browser_verification import process
from scripts.browser_verification.contracts import CleanupFinding
from scripts.browser_verification.journey import ResourceRegistry

PYTHON = str(getattr(sys, "_base_executable", sys.executable))


@pytest.fixture(autouse=True)
def retain_native_evidence(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Generator[None]:
    findings: list[CleanupFinding] = []
    original = ResourceRegistry.record_finding

    def capture(registry: ResourceRegistry, finding: CleanupFinding) -> None:
        original(registry, finding)
        findings.append(finding)

    monkeypatch.setattr(ResourceRegistry, "record_finding", capture)
    yield
    if root := os.environ.get("CRAFT_NATIVE_EVIDENCE"):
        directory = Path(root)
        directory.mkdir(parents=True, exist_ok=True)
        node = cast(pytest.Item, getattr(request, "node"))
        (directory / (node.name + ".json")).write_text(
            json.dumps(
                {
                    "platform": platform.platform(),
                    "python": sys.version,
                    "executable": PYTHON,
                    "findings": [item.model_dump(mode="json") for item in findings],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


@pytest.mark.parametrize("exit_code", [0, 7])
def test_observed_native_exit(tmp_path: Path, exit_code: int) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    command = [PYTHON, "-c", f"import sys; print('observed'); sys.exit({exit_code})"]
    with process.scope(process.CommandScope(registry, handles, 2)):
        if exit_code:
            with pytest.raises(subprocess.CalledProcessError):
                process.execute(command, time.monotonic() + 15)
        else:
            assert process.execute(command, time.monotonic() + 15) == "observed"
    assert len(handles) == 1 and handles[0].returncode == exit_code
    finding = registry.findings[0]
    assert finding.resource_kind == "process" and finding.exit_status == exit_code
    assert finding.status == ("failed" if exit_code else "graceful")
    assert finding.acquisition_state == "acquired"
    assert finding.acquisition_id and finding.close_id
    assert finding.acquisition_id == registry.tokens[0].acquisition_id
    assert finding.close_id == registry.tokens[0].close_id
    assert (
        finding.started is not None
        and finding.finished is not None
        and finding.deadline is not None
    )
    assert finding.started <= finding.finished <= finding.deadline
    assert finding.native_pid == handles[0].pid
    assert not finding.requested_force and not finding.observed_force
    assert not finding.survivors
    assert finding.accepted == (exit_code == 0)


def test_real_native_group_or_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    code = (
        "import ctypes; print(int(bool(ctypes.windll.kernel32.GetConsoleWindow())))"
        if os.name == "nt"
        else "import os; print(f'{os.getpid()}:{os.getsid(0)}:{os.getpgrp()}')"
    )
    original = subprocess.Popen
    launched: list[dict[str, object]] = []

    def launch(
        argv: list[str],
        *,
        stdout: int,
        stderr: int,
        text: bool,
        encoding: str,
        creationflags: int,
        start_new_session: bool,
    ) -> subprocess.Popen[str]:
        launched.append({"creationflags": creationflags})
        return original(
            argv,
            stdout=stdout,
            stderr=stderr,
            text=text,
            encoding=encoding,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )

    monkeypatch.setattr(process.subprocess, "Popen", launch)
    with process.scope(process.CommandScope(registry, handles, 2)):
        output = process.execute([PYTHON, "-c", code], time.monotonic() + 15)
    record_property("actual_native_observation", output)
    assert handles, "the actual production Popen must remain retained"
    if os.name == "nt":
        assert output == "0", "native helper must not create a console window"
        assert launched[0]["creationflags"] == (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        assert output == ":".join([str(handles[0].pid)] * 3)
    assert registry.findings[0].identity.startswith(
        "windows-process-group:" if os.name == "nt" else "linux-session:"
    )
    assert registry.findings[0].mechanism == "observed-exit"


def test_timeout_retains_handle_force_and_unrelated_process(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    unrelated = subprocess.Popen([PYTHON, "-c", "import time; time.sleep(20)"], creationflags=flags)
    try:
        with process.scope(process.CommandScope(registry, handles, 2)):
            with pytest.raises(subprocess.TimeoutExpired):
                process.execute(
                    [PYTHON, "-c", "import time; time.sleep(20)"], time.monotonic() + 0.1
                )
        assert len(handles) == 1 and handles[0].poll() is not None
        finding = registry.findings[0]
        assert finding.requested_force and finding.status != "graceful"
        assert finding.exit_status == handles[0].returncode and not finding.survivors
        assert unrelated.poll() is None
    finally:
        unrelated.kill()
        unrelated.wait(timeout=5)


def test_native_startup_failure_is_retained(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    with process.scope(process.CommandScope(registry, handles, 2)):
        with pytest.raises(OSError):
            process.execute([str(tmp_path / "missing-command")], time.monotonic() + 2)
    assert len(registry.tokens) == 1 and not handles
    finding = registry.findings[0]
    assert finding.status == "failed" and finding.acquisition_state == "failed"
    assert finding.exit_status is None and finding.resource_kind == "process"


@pytest.mark.parametrize("repeated", [False, True])
def test_cancellation_retains_actual_handle_and_primary_failure(
    monkeypatch: pytest.MonkeyPatch,
    repeated: bool,
) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    original = subprocess.Popen[str].communicate
    calls = 0

    def cancelled(
        child: subprocess.Popen[str], input: str | None = None, timeout: float | None = None
    ) -> tuple[str, str]:
        nonlocal calls
        calls += 1
        assert handles[0] is child and registry.tokens[0].acquisition == "acquired"
        if calls == 1 or repeated:
            raise KeyboardInterrupt("primary" if calls == 1 else "cleanup")
        return original(child, input=input, timeout=timeout)

    monkeypatch.setattr(subprocess.Popen, "communicate", cancelled)
    try:
        with process.scope(process.CommandScope(registry, handles, 2)):
            with pytest.raises(KeyboardInterrupt, match="primary"):
                process.execute(
                    [PYTHON, "-c", "import time; time.sleep(20)"], time.monotonic() + 15
                )
        finding = registry.findings[0]
        assert finding.requested_force and finding.status == (
            "unresolved" if repeated else "forced"
        )
        assert finding.native_pid == handles[0].pid
        assert not finding.accepted
        if not repeated:
            assert handles[0].poll() is not None
    finally:
        for child in handles:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)


def test_timeout_race_cannot_become_graceful(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    original = subprocess.Popen[str].communicate

    def late_exit(
        child: subprocess.Popen[str], input: str | None = None, timeout: float | None = None
    ) -> tuple[str, str]:
        original(child, input=input, timeout=timeout)
        raise subprocess.TimeoutExpired(child.args, timeout or 0)

    monkeypatch.setattr(subprocess.Popen, "communicate", late_exit)
    with process.scope(process.CommandScope(registry, handles, 2)):
        with pytest.raises(subprocess.TimeoutExpired):
            process.execute([PYTHON, "-c", "pass"], time.monotonic() + 15)
    assert handles[0].returncode == 0
    assert registry.findings[0].status == "timed-out"
    assert not registry.findings[0].accepted


@pytest.mark.skipif(os.name == "nt", reason="Linux native signal exit")
def test_linux_signal_exit_is_observed_force() -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    with process.scope(process.CommandScope(registry, handles, 2)):
        with pytest.raises(subprocess.CalledProcessError):
            process.execute(
                [PYTHON, "-c", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)"],
                time.monotonic() + 15,
            )
    assert registry.findings[0].observed_force and not registry.findings[0].accepted


@pytest.mark.skipif(os.name == "nt", reason="Linux SIGTERM escalation")
def test_linux_ignored_sigterm_is_bounded_and_retained() -> None:
    registry = ResourceRegistry(uuid4())
    handles: list[subprocess.Popen[str]] = []
    started = time.monotonic()
    with process.scope(process.CommandScope(registry, handles, 1)):
        with pytest.raises(subprocess.TimeoutExpired):
            process.execute(
                [
                    PYTHON,
                    "-c",
                    "import signal,time;"
                    "signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)",
                ],
                started + 1,
            )
    assert time.monotonic() - started < 3
    assert handles[0].poll() is not None
    assert registry.findings[0].requested_force and registry.findings[0].observed_force
    assert not registry.findings[0].survivors
