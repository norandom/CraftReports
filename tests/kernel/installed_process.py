"""Portable ownership of one isolated runtime process and its private control pipes."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import IO
from uuid import uuid4

from fixture_packaging import ROOT, InstalledFixture
from pydantic import BaseModel, ConfigDict, Field


class Control(BaseModel):
    model_config = ConfigDict(strict=True)
    port: int = Field(ge=1, le=65535)
    credentials: dict[str, str] = Field(repr=False)
    imports: dict[str, str]
    pid: int
    parent_pid: int
    epoch: str
    fixture: dict[str, str]


class TargetObservation(BaseModel):
    request_id: str
    epoch: str
    resource: str
    value: str
    version: str
    effect_count: int
    result: dict[str, str] | None = None


class StartupFailure(RuntimeError):
    """The owned child failed before delivering its private startup record."""


class CleanupFailure(RuntimeError):
    """The owned child did not complete graceful cleanup successfully."""


class ChildCleanup(BaseModel):
    providers_closed: bool
    plugin_events: list[str]
    effect_count: int
    status: str
    code: int


def write_json(path: Path, value: object, *, secrets: tuple[str, ...] = ()) -> None:
    content = json.dumps(value, indent=2, sort_keys=True)
    for secret in secrets:
        content = content.replace(json.dumps(secret)[1:-1], "[REDACTED]")
    path.write_text(content, encoding="utf-8")


@dataclass
class InstalledProcess:
    installed: InstalledFixture
    name: str
    failure: str = "none"
    boundary_probe: bool = False
    timeout: float = 20
    process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    control: Control | None = field(default=None, init=False, repr=False)
    cleanup: dict[str, object] = field(default_factory=dict[str, object], init=False)
    _messages: queue.Queue[str] = field(default_factory=queue.Queue[str], init=False, repr=False)
    _diagnostics: list[str] = field(default_factory=list[str], init=False, repr=False)
    _readers: list[threading.Thread] = field(
        default_factory=list[threading.Thread], init=False, repr=False
    )

    @property
    def directory(self) -> Path:
        return self.installed.directory / self.name

    @property
    def secrets(self) -> tuple[str, ...]:
        return tuple(self.control.credentials.values()) if self.control else ()

    @property
    def endpoint(self) -> str:
        assert self.control is not None
        return f"http://127.0.0.1:{self.control.port}"

    def __enter__(self) -> InstalledProcess:
        self.directory.mkdir()
        command = [
            str(self.installed.python),
            "-I",
            str(ROOT / "tests/fixtures/kernel_server.py"),
            str(self.directory),
        ]
        if self.boundary_probe:
            command.append("--boundary-probe")
        if self.failure != "none":
            command.extend(("--failure", self.failure))
        environment = {
            key: os.environ[key]
            for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
            if key in os.environ
        }
        self.process = subprocess.Popen(
            command,
            cwd=self.directory,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        assert self.process.stdout is not None and self.process.stderr is not None
        self._reader(self.process.stdout, control=True)
        self._reader(self.process.stderr, control=False)
        try:
            self.control = self._startup()
            assert self.process.pid in (self.control.pid, self.control.parent_pid)
            write_json(
                self.directory / "runtime.json",
                {
                    **self.control.model_dump(exclude={"credentials"}),
                    "endpoint": self.endpoint,
                    "command": command,
                    "ai_services": "disabled",
                    "failure_mode": self.failure,
                },
            )
            return self
        except BaseException:
            self.close(failed=True)
            raise

    def _reader(self, pipe: IO[str], *, control: bool) -> None:
        def consume() -> None:
            if control:
                for line in pipe:
                    self._messages.put(line)
            else:
                self._diagnostics.extend(pipe.readlines())

        thread = threading.Thread(target=consume, daemon=True)
        thread.start()
        self._readers.append(thread)

    def observe(self, result_ref: str | None = None) -> TargetObservation:
        assert self.process is not None and self.process.stdin is not None
        request_id = uuid4().hex
        self.process.stdin.write(
            json.dumps({"command": "observe", "request_id": request_id, "result_ref": result_ref})
            + "\n"
        )
        self.process.stdin.flush()
        observation = TargetObservation.model_validate_json(
            self._messages.get(timeout=self.timeout)
        )
        assert observation.request_id == request_id
        assert self.control is not None and observation.epoch == self.control.epoch
        write_json(self.directory / "target-observation.json", observation.model_dump())
        with (self.directory / "target-observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(observation.model_dump_json() + "\n")
        return observation

    def _startup(self) -> Control:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                message = self._messages.get(timeout=0.1)
            except queue.Empty:
                assert self.process is not None
                if self.process.poll() is not None:
                    break
                continue
            if not message:
                break
            try:
                return Control.model_validate_json(message)
            except ValueError:
                raise StartupFailure("Invalid private startup record") from None
        raise StartupFailure("Installed service did not start; see sanitized diagnostics")

    def _stop(self) -> bool:
        assert self.process is not None
        if self.process.poll() is not None:
            return False
        try:
            assert self.process.stdin is not None
            self.process.stdin.write("shutdown\n")
            self.process.stdin.flush()
        except OSError:
            # A startup failure may close stdin before its launcher has exited.
            pass
        try:
            self.process.wait(timeout=self.timeout)
            return False
        except subprocess.TimeoutExpired:
            if self.process.poll() is not None:
                return False
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            return True

    def close(self, *, failed: bool = False) -> None:
        if self.cleanup or self.process is None:
            return
        forced = self._stop()
        for reader in self._readers:
            reader.join(timeout=5)
        for pipe in (self.process.stdin, self.process.stdout, self.process.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    if not pipe.closed:
                        raise
        diagnostic = "".join(self._diagnostics)
        for secret in self.secrets:
            diagnostic = diagnostic.replace(secret, "[REDACTED]")
        (self.directory / "server-diagnostics.log").write_text(diagnostic, encoding="utf-8")
        child_path = self.directory / "cleanup.json"
        try:
            child = ChildCleanup.model_validate_json(child_path.read_bytes())
        except (OSError, ValueError):
            child = None
        passed = self._clean(child, diagnostic) and not failed and not forced
        self.cleanup = {
            "status": "passed" if passed else "failed",
            "pid": self.process.pid,
            "runtime_pid": self.control.pid if self.control else None,
            "exit_code": self.process.returncode,
            "forced_termination": forced,
            "providers": child.model_dump() if child else None,
            "pipes_closed": True,
        }
        write_json(child_path, self.cleanup)

    def _clean(self, child: ChildCleanup | None, diagnostic: str) -> bool:
        assert self.process is not None
        return (
            self.process.returncode == 0
            and child is not None
            and child.providers_closed
            and child.code == 0
            and child.status == "closed"
            and "released" in child.plugin_events
            and not any(reader.is_alive() for reader in self._readers)
            and "Traceback (most recent call last)" not in diagnostic
            and "ERROR:" not in diagnostic
        )

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close(failed=kind is not None)
        if kind is None and self.cleanup["status"] != "passed":
            raise CleanupFailure("Installed service cleanup failed; see cleanup.json")
