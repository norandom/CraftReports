"""Installed durable publication capability and restart journeys."""

import asyncio
import json
import sqlite3
from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from craftreport.adapters.snapshot_wire import snapshot_codec
from craftreport.composition.snapshot_host import snapshot_factory
from tests.kernel.fixture_packaging import ROOT, build_fixture
from tests.snapshot_runtime.installed_client import SnapshotProcess

pytest_plugins = ["tests.snapshot_runtime.test_wire"]


def test_snapshot_factory_describes_real_publication() -> None:
    manifest = snapshot_factory().describe()
    assert manifest.package == "craftreport"
    assert manifest.identity == "snapshot"
    assert {op.key.name for op in manifest.operations} == {
        "snapshot.publish",
        "snapshot.read",
        "snapshot.latest",
    }


def command(content: dict[str, Any], retry: str, expected: str) -> dict[str, Any]:
    return {
        "operation": "snapshot.publish",
        "contract_version": "1",
        "payload": content,
        "correlation_id": retry,
        "retry_key": retry,
        "expected_versions": [
            {"resource": {"kind": "feed", "identity": content["feed_id"]}, "version": expected}
        ],
    }


def published(host: SnapshotProcess, request: dict[str, Any], status: str) -> dict[str, Any]:
    receipt = host.rest("POST", "/v1/invoke", request)
    assert receipt["state"] == "complete", receipt
    readback = host.rest("GET", f"/v1/operations/{receipt['operation_id']}/result")
    assert readback["value"]["status"] == status, readback
    assert readback["receipt"] == receipt
    return readback


@pytest.mark.integration
def test_installed_rest_publication_and_mcp_restart(payload: dict[str, Any]) -> None:
    directory = ROOT / "artifacts/snapshot-runtime/task-4.2" / uuid4().hex
    directory.mkdir(parents=True)
    installed = build_fixture(directory)
    database = directory / "retained.sqlite3"
    payload["producer_version"] = "3"
    request = command(payload, "original", "absent")
    host = SnapshotProcess(installed, database, directory / "first")
    try:
        assert [c["manifest"]["identity"] for c in host.catalog["capabilities"]] == ["snapshot"]
        original = published(host, request, "accepted")
        assert host.rest("POST", "/v1/invoke", request) == original["receipt"]
        assert (
            host.rest("GET", f"/v1/operations/{original['receipt']['operation_id']}")
            == original["receipt"]
        )
        assert "diagnostic" in host.rest(
            "GET", f"/v1/operations/{original['receipt']['operation_id']}/result", subject="bob"
        )
        ref = original["value"]["requested"]
        read_request = {
            "operation": "snapshot.read",
            "contract_version": "1",
            "payload": ref,
            "correlation_id": "read",
        }
        read = host.rest("POST", "/v1/invoke", read_request)
        content = host.rest("GET", f"/v1/operations/{read['operation_id']}/result")["value"]
        published(host, command(payload, "duplicate", "1"), "existing")
        stale = {**payload, "producer_version": "2"}
        published(host, command(stale, "stale", "1"), "stale_version")
        changed = deepcopy(payload)
        changed["datasets"][0]["label"] = "Changed"
        published(host, command(changed, "conflict", "1"), "version_conflict")
        retry_conflict = host.rest("POST", "/v1/invoke", command(changed, "original", "absent"))
        assert retry_conflict["diagnostic"]["code"] == "retry_conflict"
        epoch = host.catalog["deployment_epoch"]
    finally:
        host.close()
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT snapshot_bytes, content_digest, producer_bytes, snapshot_digest FROM snapshots"
        ).fetchall()
        assert len(rows) == 1
        stored, digest, producer_bytes, snapshot_digest = rows[0]
        assert sha256(producer_bytes).hexdigest() == digest
        assert sha256(stored).hexdigest() == snapshot_digest
        assert json.loads(stored) == content and digest == ref["content_digest"]
        before = connection.execute("SELECT * FROM snapshots").fetchall()
    typed = snapshot_codec().decode(content)
    assert typed.datasets[0].rows[0][0] == 9223372036854775807
    assert typed.datasets[0].rows[0][1] == Decimal("123456789012345678901234567890123456.78")
    assert typed.datasets[0].rows[0][2:] == (
        "=SUM(A1)",
        date(2026, 10, 14),
        datetime(2026, 10, 15, 9, 1, 2, 123456, tzinfo=UTC),
        True,
    )
    assert typed.datasets[0].rows[1][0] == -9223372036854775808
    assert typed.metrics[0].labels == ("last", "first", "middle")
    assert typed.metrics[0].values == (Decimal("-1.2300"), None, Decimal("0.0000"))

    (directory / "readback.json").write_text(
        json.dumps(
            {
                "snapshot_sha256": sha256(stored).hexdigest(),
                "digest": digest,
                "snapshot": content,
                "receipt": original["receipt"],
            },
            indent=2,
        )
    )
    reopened = SnapshotProcess(installed, database, directory / "reopened")
    try:
        assert reopened.catalog["deployment_epoch"] == epoch
        assert reopened.catalog["capabilities"] == host.catalog["capabilities"]
        asyncio.run(restart_reads(reopened, request, read_request, original, content))
    finally:
        reopened.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM snapshots").fetchall() == before


async def restart_reads(
    host: SnapshotProcess,
    request: dict[str, Any],
    read_request: dict[str, Any],
    original: dict[str, Any],
    content: dict[str, Any],
) -> None:
    identity = {"operation_id": original["receipt"]["operation_id"]}
    assert await host.mcp("craftreport.inspect.v1", identity) == original["receipt"]
    assert await host.mcp("craftreport.result.v1", identity) == original
    assert await host.mcp("snapshot.publish.v1", request) == original["receipt"]
    read = await host.mcp("snapshot.read.v1", read_request)
    result = await host.mcp("craftreport.result.v1", {"operation_id": read["operation_id"]})
    assert result["value"] == content


@pytest.mark.parametrize("settings", [{"provider": "volatile"}, {"owner": "bob"}])
def test_snapshot_settings_reject_caller_supplied_authority(settings: dict[str, Any]) -> None:
    from craftreport.composition.snapshot_host import SNAPSHOT_SETTINGS

    with pytest.raises(ValueError):
        SNAPSHOT_SETTINGS.decode(settings)


def test_snapshot_factory_rejects_foreign_entry_point(tmp_path: Path) -> None:
    from craftreport.adapters.storage.database import Database
    from craftreport.composition.snapshot_host import configure_snapshot
    from tests.snapshot_runtime.test_providers import provider

    async def exercise() -> None:
        database = Database(tmp_path / "entrypoint.sqlite3", "deployment-a")
        try:
            selection = configure_snapshot(provider(database), owner_policy=lambda principal: True)
            with pytest.raises(ValueError, match="Unexpected snapshot"):
                selection.prepare(lambda: snapshot_factory())
        finally:
            await database.close()

    asyncio.run(exercise())
