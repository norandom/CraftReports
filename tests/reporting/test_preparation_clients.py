"""Exact adopter invocation against installed production providers; no target UI."""

import json
import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from craftreport.adapters.report_codecs import preparation_result_codec
from craftreport.reporting.ports import PreparationResult
from tests.kernel.fixture_packaging import ROOT


@pytest.mark.parametrize("run_id", ["../outside", "C:/outside", "/outside", "x" * 65])
def test_demo_rejects_unsafe_run_id_before_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_id: str
) -> None:
    from tests.reporting import report_demo

    def forbidden(directory: Path) -> None:
        raise AssertionError("Build must not start")

    monkeypatch.setattr(report_demo, "build_fixture", forbidden)
    with pytest.raises(ValueError, match="run-id"):
        report_demo.launch("rest", run_id, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("run_id", ["../outside", "C:/outside", "/outside"])
def test_cli_rejects_unsafe_run_id_without_files(tmp_path: Path, run_id: str) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.examples.prepare_reusable_report",
            "--demo",
            "--run-id",
            run_id,
            "--evidence-root",
            str(tmp_path / "evidence"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 2
    assert "--run-id" in completed.stderr
    assert not list(tmp_path.iterdir())


@pytest.mark.integration
def test_public_recipe_rest_mcp_and_owned_cleanup() -> None:
    command = [
        sys.executable,
        "-m",
        "scripts.examples.prepare_reusable_report",
        "--demo",
        "--transport",
        "both",
        "--evidence-root",
        str(ROOT / "artifacts/report-task9-recipe/tests" / uuid4().hex),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=240,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(completed.stdout)
    evidence = Path(summary["evidence_directory"])
    results: dict[str, Any] = json.loads((evidence / "results.json").read_text())
    for transport in ("rest", "mcp"):
        assert_journey(results[transport])
    for index in range(2):
        assert results["rest"]["drafts"][index]["value"] == results["mcp"]["drafts"][index]["value"]
    assert results["rest"]["publications"] == results["mcp"]["publications"]
    cleanup = json.loads((evidence / "lifecycle.json").read_text())
    assert cleanup == {"host_closed": True, "pack_root_removed": True, "environment_restored": True}
    transcript = (evidence / "host" / "transcript.jsonl").read_text()
    records = [json.loads(line) for line in transcript.splitlines()]
    assert records[-1]["cleanup"]["exit_code"] == 0
    assert not records[-1]["cleanup"]["forced"]
    assert {c["manifest"]["identity"] for c in records[1]["result"]["capabilities"]} == {
        "snapshot",
        "reporting",
    }
    assert "credentials" not in transcript
    inventory = json.loads((evidence / "inventory.json").read_text())
    assert inventory["environment"]["kernel_implementation_digest"]
    invocation = json.loads((evidence / "invocation.json").read_text())
    assert invocation["exit_code"] == 0
    for source, digest in invocation["public_source_sha256"].items():
        assert sha256((ROOT / source).read_bytes()).hexdigest() == digest


def assert_journey(result: dict[str, Any]) -> None:
    assert result["missing_binding"]["receipt"]["state"] == "failed"
    assert result["missing_binding"]["value"]["failure"]["code"] == "incomplete_binding"
    expected = [
        [
            (date(2026, 10, 15), Decimal("-12.50"), Decimal("101.25"), "=SUM(A1)"),
            (date(2026, 10, 13), None, Decimal("0.00"), "@literal"),
            (date(2026, 10, 14), Decimal("0.00"), None, "+literal"),
        ],
        [
            (date(2026, 10, 16), Decimal("203.10"), None, "second snapshot"),
            (date(2026, 10, 12), Decimal("-1.20"), Decimal("97.00"), "-literal"),
        ],
    ]
    for index, readback in enumerate(result["drafts"]):
        prepared = preparation_result_codec().decode(readback["value"])
        assert isinstance(prepared, PreparationResult)
        assert prepared.prepared.tables[0].rows == tuple(expected[index])
        chart = prepared.prepared.charts[0]
        assert chart.categories == tuple(row[0] for row in expected[index])
        assert chart.series[0].values == tuple(row[1] for row in expected[index])
        assert chart.series[1].values == tuple(row[2] for row in expected[index])
        assert chart.null_behavior == "gap"
        assert prepared.prepared.title == "Synthetic portfolio"
        assert [column.field.name for column in prepared.prepared.tables[0].columns] == [
            "date",
            "nav",
            "benchmark",
            "note",
        ]
        assert prepared.quality.draft_eligible
        assert not prepared.quality.validated_release_eligible
        assert prepared.quality.draft_designation == "DRAFT"
        assert prepared.prepared.definition == prepared.prepared.template
        assert prepared.prepared.definition.identity == "public/supplied_portfolio"
        assert prepared.prepared.definition.version == "1.0.0"
        assert prepared.prepared.theme.identity == "house"
        assert prepared.prepared.theme.version == "1.0.0"
        assert (
            prepared.prepared.snapshot.content_digest
            == (result["publications"][index + 1]["value"]["requested"]["content_digest"])
        )
        assert [column.field.kind for column in prepared.prepared.tables[0].columns] == [
            "date",
            "decimal",
            "decimal",
            "text",
        ]
        assert [column.field.unit for column in prepared.prepared.tables[0].columns] == [
            None,
            "USD",
            "USD",
            None,
        ]
        assert all(
            finding.scope.content_digest == prepared.prepared.content_digest
            for finding in prepared.quality.findings
        )
        assert readback["receipt"]["state"] == "complete"
        assert_full_pins(readback)
    blocked = result["validated"]
    assert blocked["receipt"]["state"] == "failed"
    assert [stage["state"] for stage in blocked["receipt"]["stages"]] == ["passed", "failed"]
    assert blocked["value"]["prepared"] == result["drafts"][0]["value"]["prepared"]
    assert any(
        finding["check_id"] == "layout_fit" and finding["status"] == "unevaluated"
        for finding in blocked["value"]["quality"]["findings"]
    )
    assert_full_pins(blocked)


def assert_full_pins(readback: dict[str, Any]) -> None:
    assert len(readback["receipt"]["evidence"]) == 2
    for fact in readback["receipt"]["evidence"]:
        assert {pin["resource"]["kind"] for pin in fact["resource_versions"]} == {
            "snapshot",
            "report_pack_source",
            "report_pack_artifact_scope",
        }
        snapshot = readback["value"]["prepared"]["snapshot"]
        for pin in fact["resource_versions"]:
            if pin["resource"]["kind"] == "snapshot":
                assert pin["version"] == snapshot["content_digest"]
                assert pin["resource"]["identity"] == (
                    f"{snapshot['feed_id']}:{snapshot['producer_version']}"
                )
            else:
                assert pin["resource"]["identity"] == "public/supplied_portfolio@1.0.0"


def _stage_maximal_pack(root: Path, statement_op_id: str) -> None:
    from collections.abc import Callable
    from dataclasses import replace
    from typing import cast

    from test_pack_reader import write_pack
    from test_prepare import definition as base_definition
    from test_themes import theme as base_theme

    from craftreport.adapters import report_codecs as c
    from craftreport.contracts.identity import OperationKey
    from craftreport.contracts.outcomes import EvidenceRef
    from craftreport.policies.values import CheckId, ExternalStatement, ReleasePolicy
    from craftreport.reporting import definitions as d
    from craftreport.themes.values import SemanticRole, Theme, ValueFormat

    defn = cast(Callable[[], d.ReportDefinition], getattr(base_definition, "__wrapped__"))()
    thm = cast(Callable[[], Theme], getattr(base_theme, "__wrapped__"))()
    source = d.MetricRef("metric", "USD", ("decimal",), "series")
    parameters = (replace(defn.parameters[0], default="T" * 510),) + tuple(
        d.ParameterDefinition("p" + str(i) + "n" * 120, "text", False, "v" * 510) for i in range(15)
    )
    defn = replace(
        defn,
        parameters=parameters,
        release_policy=ReleasePolicy(tuple(CheckId)[:3], "P" * 510),
        compliance_statement=ExternalStatement(
            "C" * 31000,
            "S" * 510,
            "I" * 126,
            (
                EvidenceRef(
                    "supplied",
                    "statement",
                    statement_op_id,
                    OperationKey("snapshot.publish", "1"),
                ),
            ),
        ),
        table=d.TableDefinition(
            "table",
            source,
            (
                d.ColumnSelection("label", SemanticRole.ROW_LABEL, ValueFormat("text")),
                d.ColumnSelection("value", SemanticRole.OUTPUT, ValueFormat("decimal", 8)),
            ),
        ),
        chart=d.LineChartDefinition(
            "chart",
            source,
            "label",
            (
                d.SeriesSelection(
                    "amount", "Amount", "value", SemanticRole.OUTPUT, ValueFormat("decimal", 8)
                ),
            ),
        ),
    )
    maximal_theme = replace(
        thm,
        styles=tuple(
            (role, replace(style, font_family="F" * 126, size_pt=144.0))
            for role, style in thm.styles
        ),
        chart=replace(thm.chart, series_colors=("#123456",) * 32, line_width=20.0),
        grid=replace(thm.grid, header_height=4096.0, column_width=4096.0),
        null_marker="N" * 126,
        empty_note="E" * 510,
        formats=tuple(
            ValueFormat(kind, date_pattern="D" * 126 if kind in ("date", "datetime") else None)
            for kind in ("text", "bool", "int64", "decimal", "date", "datetime")
        ),
    )
    maximal_theme = replace(
        maximal_theme,
        version_pin=replace(
            maximal_theme.version_pin, content_digest=c.theme_identifier(maximal_theme)
        ),
    )
    encoded_defn = c.encode_definition(defn)
    assets = {
        "definition.json": encoded_defn,
        "template.json": encoded_defn,
        "theme.json": c.encode_theme(maximal_theme),
    }
    write_pack(
        root,
        assets,
        source_visibility_scope="public_source",
        artifact_visibility_scope="public_artifact",
    )


def test_wheel_and_sdist_exclude_private_sentinels(tmp_path: Path) -> None:
    import shutil
    import tarfile
    import zipfile

    uv = shutil.which("uv")
    assert uv is not None
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    completed = subprocess.run(
        [
            uv,
            "build",
            "--offline",
            "--no-build-isolation",
            "--python",
            sys.executable,
            "--out-dir",
            str(dist_dir),
            str(ROOT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = list(dist_dir.glob("*.whl"))
    sdists = list(dist_dir.glob("*.tar.gz"))
    assert len(wheels) == 1 and len(sdists) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        assert not any("tests/" in name or "PRIVATE_TEST_ONLY" in name for name in names)
        for name in names:
            assert b"PRIVATE_TEST_ONLY" not in archive.read(name)
    with tarfile.open(sdists[0], "r:gz") as archive:
        for member in archive.getmembers():
            assert "PRIVATE_TEST_ONLY" not in member.name
            is_test_sentinel = member.name.endswith(
                ("test_pack_reader.py", "test_preparation_clients.py")
            )
            if member.isfile() and not is_test_sentinel:
                extracted = archive.extractfile(member)
                if extracted is not None:
                    assert b"PRIVATE_TEST_ONLY" not in extracted.read()


@pytest.mark.integration
def test_installed_maximal_transport_restart_and_snapshot_bound() -> None:
    import asyncio
    import sqlite3

    from test_preparation_codecs import maximal_snapshot

    from craftreport.adapters.canonical import canonical_bytes
    from craftreport.adapters.snapshot_wire import snapshot_codec
    from tests.kernel.fixture_packaging import build_fixture
    from tests.snapshot_runtime.installed_client import SnapshotProcess

    directory = ROOT / "artifacts/report-preparation" / f"task10-{uuid4().hex[:12]}"
    directory.mkdir(parents=True)
    installed = build_fixture(directory)
    database = directory / "retained.sqlite3"
    pack_root = directory / "pack"
    snap, snap_size = maximal_snapshot()
    assert 1_040_000 < snap_size <= 1_048_576
    raw_snap = {
        k: v
        for k, v in json.loads(canonical_bytes(snapshot_codec().encode(snap))).items()
        if k not in ("content_digest", "received_at", "accepted_at")
    }
    _stage_maximal_pack(pack_root, "seed-op")
    host = SnapshotProcess(installed, database, directory / "host1", pack_root=pack_root)
    try:
        pub_req = {
            "operation": "snapshot.publish",
            "contract_version": "1",
            "payload": raw_snap,
            "correlation_id": "pub-max",
            "retry_key": "pub-max",
            "expected_versions": [
                {"resource": {"kind": "feed", "identity": snap.feed_id}, "version": "absent"}
            ],
        }
        pub_receipt = host.rest("POST", "/v1/invoke", pub_req)
        assert pub_receipt["state"] == "complete", pub_receipt
        pub_res = host.rest("GET", f"/v1/operations/{pub_receipt['operation_id']}/result")
        snap_ref = pub_res["value"]["requested"]
    finally:
        host.close()
    _stage_maximal_pack(pack_root, pub_receipt["operation_id"])
    reopened = SnapshotProcess(installed, database, directory / "host2", pack_root=pack_root)
    try:
        pack_sel = {"namespace": "public", "name": "example", "version": "1.0.0"}
        prep_payload = {
            "pack": pack_sel,
            "snapshot": snap_ref,
            "parameters": [{"name": "title", "value": {"kind": "text", "value": "=Maximal title"}}],
        }
        prep_req = {
            "operation": "reports.prepare",
            "contract_version": "1",
            "payload": prep_payload,
            "correlation_id": "prep-max",
            "retry_key": "prep-max",
        }
        prep_receipt = reopened.rest("POST", "/v1/invoke", prep_req)
        assert prep_receipt["state"] == "complete", prep_receipt
        assert reopened.rest("POST", "/v1/invoke", prep_req) == prep_receipt
        conflict_req = {
            **prep_req,
            "payload": {
                **prep_payload,
                "parameters": [{"name": "title", "value": {"kind": "text", "value": "Changed"}}],
            },
        }
        conflict = reopened.rest("POST", "/v1/invoke", conflict_req)
        assert conflict["diagnostic"]["code"] == "retry_conflict"
        denied = reopened.rest("POST", "/v1/invoke", prep_req, subject="bob")
        assert denied["diagnostic"]["code"] == "access_denied"
        readback = reopened.rest("GET", f"/v1/operations/{prep_receipt['operation_id']}/result")
        mcp_readback = asyncio.run(
            reopened.mcp("craftreport.result.v1", {"operation_id": prep_receipt["operation_id"]})
        )
        assert readback == mcp_readback
        wire_bytes = canonical_bytes(readback["value"])
        assert 2_800_000 < len(wire_bytes) <= 6 * snap_size + 524_288 < 8_388_608
        decoded = preparation_result_codec().decode(readback["value"])
        assert isinstance(decoded, PreparationResult)
        assert decoded.prepared.title == "=Maximal title"
        assert len(decoded.prepared.tables[0].rows) == 1000
    finally:
        reopened.close()
    with sqlite3.connect(database) as conn:
        conn.execute(
            "UPDATE snapshots SET snapshot_bytes = ? WHERE feed_id = ?",
            (b" " * 1_048_577, snap.feed_id),
        )
    corrupted = SnapshotProcess(installed, database, directory / "host3", pack_root=pack_root)
    try:
        bad_prep = corrupted.rest(
            "POST",
            "/v1/invoke",
            {
                "operation": "reports.prepare",
                "contract_version": "1",
                "payload": {"pack": pack_sel, "snapshot": snap_ref},
                "correlation_id": "prep-over-1mib",
                "retry_key": "prep-over-1mib",
            },
        )
        assert bad_prep["diagnostic"]["code"] == "service_unavailable"
    finally:
        corrupted.close()
    (directory / "task10-summary.json").write_text(
        json.dumps(
            {
                "snapshot_bytes": snap_size,
                "result_bytes": len(wire_bytes),
                "operation_id": prep_receipt["operation_id"],
                "content_digest": decoded.prepared.content_digest,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
