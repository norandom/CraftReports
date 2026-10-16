"""Explicit demo bootstrap, separate from the ordinary public caller recipe."""

import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

from scripts.examples.common import JsonObject
from scripts.examples.prepare_reusable_report import journey, run_identity
from tests.kernel.fixture_packaging import ROOT, build_fixture
from tests.snapshot_runtime.installed_client import SnapshotProcess

ASSETS = {
    "manifest.json": "examples/templates/public_report/manifest.json",
    "definition.json": "examples/reports/supplied_portfolio.json",
    "template.json": "examples/reports/supplied_portfolio.json",
    "theme.json": "examples/themes/house.json",
}


@contextmanager
def credentials(host: SnapshotProcess) -> Generator[None]:
    values = {
        "CRAFTREPORT_URL": host.endpoint,
        "CRAFTREPORT_TOKEN": host.control["credentials"]["alice"],
    }
    previous = {name: os.environ.get(name) for name in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def launch(transport: str, run_id: str, evidence_root: Path) -> JsonObject:
    """Retain evidence; remove only this invocation's temporary pack root."""
    directory = evidence_root / run_identity(run_id)
    directory.mkdir(parents=True)
    installed = build_fixture(directory)
    before = {name: os.environ.get(name) for name in ("CRAFTREPORT_URL", "CRAFTREPORT_TOKEN")}
    temporary = tempfile.TemporaryDirectory(prefix="craftreport-public-pack-")
    pack_root = Path(temporary.name).resolve()
    hashes: dict[str, str] = {}
    identity: JsonObject = {
        "argv": list(sys.argv),
        "exit_code": 1,
        "public_source_sha256": dict(hashes),
        "caller_source_sha256": sha256(
            (ROOT / "scripts/examples/prepare_reusable_report.py").read_bytes()
        ).hexdigest(),
        "scope": "installed production preparation; synthetic inputs; AI absent",
    }
    host: SnapshotProcess | None = None
    try:
        for name, source in ASSETS.items():
            content = (ROOT / source).read_bytes()
            (pack_root / name).write_bytes(content)
            hashes[source] = sha256(content).hexdigest()
        identity["public_source_sha256"] = dict(hashes)
        host = SnapshotProcess(
            installed,
            directory / "retained.sqlite3",
            directory / "host",
            pack_root=pack_root,
        )
        with credentials(host):
            results = asyncio.run(journey(transport, run_id))
        (directory / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    finally:
        try:
            if host is not None:
                host.close()
        finally:
            temporary.cleanup()
            cleanup: JsonObject = {
                "host_closed": host is not None and host.process.poll() == 0,
                "pack_root_removed": not pack_root.exists(),
                "environment_restored": before == {name: os.environ.get(name) for name in before},
            }
            for name, value in (("lifecycle", cleanup), ("invocation", identity)):
                (directory / f"{name}.json").write_text(
                    json.dumps(value, indent=2), encoding="utf-8"
                )
    assert all(cleanup.values())
    identity["exit_code"] = 0
    (directory / "invocation.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    return {"evidence_directory": str(directory), "transports": transport, "cleanup": cleanup}
