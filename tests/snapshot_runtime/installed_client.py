"""Narrow subprocess and ordinary transport clients for durable restart acceptance."""

import asyncio
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, TextIO

import httpx
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from tests.kernel.fixture_packaging import InstalledFixture


class SnapshotProcess:
    def __init__(
        self,
        installed: InstalledFixture,
        database: Path,
        directory: Path,
        *,
        pack_root: Path | None = None,
        source_scope: str = "public_source",
        artifact_scope: str = "public_artifact",
    ) -> None:
        self.directory = directory
        directory.mkdir()
        self.log = (directory / "server.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            [
                str(installed.python),
                "-I",
                str(Path(__file__).with_name("installed_host.py")),
                str(database),
                *([str(pack_root), source_scope, artifact_scope] if pack_root is not None else []),
            ],
            env={
                key: os.environ[key]
                for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
                if key in os.environ
            },
            cwd=installed.directory,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.lines: queue.Queue[str] = queue.Queue()
        assert self.process.stdout is not None
        self.reader = threading.Thread(target=self._read, args=(self.process.stdout,), daemon=True)
        self.reader.start()
        try:
            self.control: dict[str, Any] = json.loads(self.lines.get(timeout=20))
            assert self.process.pid in (self.control["pid"], self.control["parent_pid"])
            self.record(
                {
                    "startup": {
                        key: value for key, value in self.control.items() if key != "credentials"
                    },
                    "launcher_pid": self.process.pid,
                    "environment_keys": ["SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH"],
                }
            )
            self.endpoint = f"http://127.0.0.1:{self.control['port']}"
            self.catalog = self.rest("GET", "/v1/catalog")
        except BaseException:
            self.close()
            raise

    def _read(self, stream: TextIO) -> None:
        for line in stream:
            self.lines.put(line)

    def record(self, value: object) -> None:
        with (self.directory / "transcript.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value) + "\n")

    def rest(
        self, method: str, path: str, body: object = None, subject: str = "alice"
    ) -> dict[str, Any]:
        with httpx.Client(
            base_url=self.endpoint,
            trust_env=False,
            timeout=10,
            headers={"Authorization": "Bearer " + self.control["credentials"][subject]},
        ) as client:
            deadline = time.monotonic() + 15
            while True:
                try:
                    response = client.request(method, path, json=body)
                    break
                except httpx.ConnectError:
                    assert time.monotonic() < deadline and self.process.poll() is None
                    time.sleep(0.05)
        result: dict[str, Any] = response.json()
        self.record(
            {
                "transport": "rest",
                "method": method,
                "path": path,
                "body": body,
                "subject": subject,
                "status": response.status_code,
                "result": result,
            }
        )
        return result

    async def mcp(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async with (
            asyncio.timeout(20),
            httpx2.AsyncClient(
                headers={"Authorization": "Bearer " + self.control["credentials"]["alice"]},
                trust_env=False,
            ) as http,
            Client(streamable_http_client(self.endpoint + "/mcp", http_client=http)) as client,
        ):
            result = await client.call_tool(name, arguments)
            assert result.structured_content is not None
            self.record(
                {
                    "transport": "mcp",
                    "name": name,
                    "arguments": arguments,
                    "result": result.structured_content,
                }
            )
            return result.structured_content

    def close(self) -> None:
        forced = False
        try:
            if self.process.poll() is None:
                assert self.process.stdin is not None
                self.process.stdin.write("shutdown\n")
                self.process.stdin.flush()
            try:
                code = self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                forced = True
                self.process.kill()
                code = self.process.wait(timeout=5)
            self.reader.join(timeout=5)
            assert not self.reader.is_alive()
            records: list[object] = []
            while not self.lines.empty():
                records.append(json.loads(self.lines.get_nowait()))
            self.record(
                {
                    "cleanup": {
                        "exit_code": code,
                        "forced": forced,
                        "records": records,
                        "launcher_pid": self.process.pid,
                        "runtime_pid": self.control.get("pid"),
                    }
                }
            )
            assert code == 0 and not forced
            assert {"closed": True, "pid": self.control["pid"]} in records
        finally:
            self.log.close()
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
