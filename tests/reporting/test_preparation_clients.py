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
