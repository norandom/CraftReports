"""Scoped harness evidence; never emit a capability conformance verification record."""

import json
import subprocess
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from fixture_packaging import ROOT
from installed_process import write_json


def source_identity() -> dict[str, object]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    paths = [ROOT / "pyproject.toml", ROOT / "breadth.toml", ROOT / "quality.toml"]
    paths.extend(
        path for folder in ("src", "scripts", "tests") for path in (ROOT / folder).rglob("*.py")
    )
    return {
        "revision": revision,
        "dirty": bool(status),
        "worktree_status": status.splitlines(),
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)
        },
    }


@dataclass
class Evidence:
    directory: Path
    cases: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    source: dict[str, object] = field(default_factory=source_identity)

    def finish(self, exit_code: int) -> None:
        inventory = self.directory / "inventory.json"
        cleanups = {
            path.parent.name: json.loads(path.read_text(encoding="utf-8"))
            for path in self.directory.glob("*/cleanup.json")
        }
        protocols = {
            path.parent.name: json.loads(path.read_text(encoding="utf-8"))["protocol_version"]
            for path in self.directory.glob("*/mcp-transcript.json")
        }
        runtimes = {
            path.parent.name: json.loads(path.read_text(encoding="utf-8"))
            for path in self.directory.glob("*/runtime.json")
        }
        manifest = {
            "scope": "installed synthetic runtime harness smoke only",
            "fixture_suite": "kernel-installed-harness-v1",
            "requirements": ["6.1", "6.3", "7.1", "7.4"],
            "harness_smoke": "passed" if exit_code == 0 else "failed",
            "conformance_status": "pending",
            "pending_tasks": ["8.2", "8.3", "8.4"],
            "excluded_claims": ["production durability", "browser behavior", "GridCraft", "XLSX"],
            "source": self.source,
            "installed": json.loads(inventory.read_text(encoding="utf-8"))
            if inventory.exists()
            else None,
            "negotiated_protocols": protocols,
            "runtimes": runtimes,
            "expected_lifecycle_failures": ["startup-failure", "cleanup-failure"],
            "command": "uv.exe run --frozen python scripts/check.py --integration",
            "exit_code": exit_code,
        }
        write_json(self.directory / "kernel-manifest.json", manifest)
        write_json(self.directory / "cases.json", self.cases)
        write_json(self.directory / "cleanup.json", cleanups)
