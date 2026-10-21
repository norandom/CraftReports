"""Read-only bounded workbook byte inspection, staging, and verifier reopen."""

from __future__ import annotations

import hashlib
import io
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import openpyxl  # pyright: ignore[reportMissingTypeStubs]

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
)
from craftreport_gridcraft.browser import BrowserDriver
from craftreport_gridcraft.values import (
    AppIssue,
    MappingPlan,
    SavedCandidate,
    StagedArtifact,
)

CHART_NS = {"c": "http://schemas.openxmlformats.org/drawingml/2006/chart"}
EXPECTED_FORMULAS = [
    "Report!$G$5",
    "Report!$F$6:$F$9",
    "Report!$G$6:$G$9",
]


def _extract_archive_xml(data: bytes) -> tuple[ET.Element, ET.Element]:
    if len(data) > 4194304:
        raise ValueError("Exceeds maximum compressed size (4 MiB)")

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infolist = archive.infolist()
        if len(infolist) > 256:
            raise ValueError("Exceeds maximum zip member count (256)")
        if sum(x.file_size for x in infolist) > 33554432:
            raise ValueError("Exceeds maximum uncompressed size (32 MiB)")
        if any(x.flag_bits & 0x1 for x in infolist):
            raise ValueError("Encrypted ZIP member detected")
        if any(x.filename.lower().endswith((".bin", ".vba", ".exe", ".dll")) for x in infolist):
            raise ValueError("Disallowed executable or macro member detected")
        parts = {p: archive.read(p) for p in archive.namelist()}
        for name, part_bytes in parts.items():
            if b"<!DOCTYPE" in part_bytes or b"<!ENTITY" in part_bytes:
                raise ValueError(f"Suspicious XML entity or DOCTYPE in {name}")
            if name.endswith(".rels") and b'TargetMode="External"' in part_bytes:
                raise ValueError(f"External relationship detected in {name}")
        chart = ET.fromstring(parts["xl/charts/chart1.xml"])
        drawings = ET.fromstring(parts["xl/drawings/drawing1.xml"])
    return chart, drawings


def _verify_chart(chart: ET.Element) -> tuple[list[str | None], list[str | None]]:
    formulas = [x.text for x in chart.findall(".//c:f", CHART_NS)]
    if formulas != EXPECTED_FORMULAS:
        raise ValueError(f"Chart formulas mismatch: {formulas}")

    categories = [x.text for x in chart.findall(".//c:cat//c:v", CHART_NS)]
    series_values = [x.text for x in chart.findall(".//c:val//c:v", CHART_NS)]
    gap = chart.find(".//c:dispBlanksAs", CHART_NS)
    if gap is not None and gap.get("val") != "gap":
        raise ValueError("Invalid dispBlanksAs setting in chart")
    return categories, series_values


def _verify_sheet_cells(sheet: Any, marker: str, run: str) -> None:
    actual_marker = getattr(sheet["K1"], "value", None) or getattr(sheet["J1"], "value", None)
    if actual_marker != marker:
        raise ValueError(f"Marker mismatch: {actual_marker} != {marker}")
    actual_run = getattr(sheet["K2"], "value", None) or getattr(sheet["J2"], "value", None)
    if actual_run != run:
        raise ValueError(f"Run mismatch: {actual_run} != {run}")
    if getattr(sheet["M1"], "value", None) != "OUTSIDE-UNCHANGED":
        raise ValueError(f"Outside sentinel modified: {sheet['M1'].value}")
    if getattr(sheet["C6"], "data_type", None) != "s":
        raise ValueError(f"Literal formula C6 must have data_type 's', got {sheet['C6'].data_type}")
    font = getattr(sheet["A1"], "font", None)
    if not (font and getattr(font, "bold", False)):
        raise ValueError("Expected bold font in A1")
    if getattr(sheet["B6"], "number_format", None) != "0.00;-0.00":
        raise ValueError(f"Expected number format in B6: {sheet['B6'].number_format}")


def inspect_workbook_bytes(
    data: bytes, expected_marker: str, expected_run: str
) -> dict[str, object]:
    """Inspect scratch workbook bytes enforcing size/XML limits, chart and styles."""
    chart, drawings = _extract_archive_xml(data)
    categories, series_values = _verify_chart(chart)

    outside = ET.tostring(drawings).decode("utf-8")
    if "SAFE" not in outside:
        raise ValueError("Missing SAFE outside drawing signature")

    book = cast(Any, openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False))
    try:
        sheet = book["Report"]
        _verify_sheet_cells(sheet, expected_marker, expected_run)
    finally:
        book.close()

    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "categories": categories,
        "series_values": series_values,
        "marker": expected_marker,
        "run": expected_run,
        "outside": outside,
    }


def verify_scratch_artifact(
    data: bytes, expected_marker: str, expected_run: str
) -> dict[str, object] | AppIssue:
    """Validate scratch inspection bytes, returning inspected dict or typed AppIssue."""
    try:
        return inspect_workbook_bytes(data, expected_marker, expected_run)
    except (ValueError, KeyError, zipfile.BadZipFile) as err:
        code = "limit" if "Exceeds" in str(err) else "conflict"
        return AppIssue(code, ("artifact",), stage="inspect")


def _make_artifact_observation(
    staged: StagedArtifact,
    plan: MappingPlan,
    check_id: CheckId,
    reason: str,
) -> CheckObservation:
    source_scope = plan.quality.findings[0].scope
    scope = CheckScope(
        content_digest=plan.layout.run.prepared_digest,
        resource_versions=source_scope.resource_versions,
        target=ExpectedVersion(
            ResourceRef("app_document", staged.candidate.target.identity.document_id),
            "1",
        ),
        artifact_digest=staged.bytes_digest,
        validation_scope_digest=plan.layout.run.validation_scope,
    )
    ev_ref = EvidenceRef(
        identity=f"evidence-{check_id.value}-{staged.staged_id}",
        scope="app-artifact",
        operation_id=f"{check_id.value}-{staged.staged_id}",
        operation=OperationKey(f"gridcraft.{check_id.value}", "1"),
        resource_versions=scope.resource_versions,
        content_digest=staged.bytes_digest,
    )
    return CheckObservation(
        check_id,
        scope,
        CheckStatus.PASSED,
        (ev_ref,),
        CheckOrigin.CRAFTREPORT,
        reason,
    )


def stage_artifact(
    candidate: SavedCandidate,
    data: bytes,
    staging_dir: Path,
    staged_id: str | None = None,
) -> StagedArtifact | AppIssue:
    """Freeze candidate bytes in a private staging path, fsync, and read back digest."""
    if candidate.purpose != "export":
        return AppIssue("conflict", ("candidate_purpose",), stage="stage")
    if len(data) > 4194304:
        return AppIssue("limit", ("size",), stage="stage")
    if hashlib.sha256(data).hexdigest() != candidate.bytes_digest:
        return AppIssue("conflict", ("bytes_digest",), stage="stage")

    sid = staged_id if staged_id is not None else f"stage-{uuid4().hex[:12]}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    staging_path = staging_dir / f"{sid}.xlsx"

    try:
        with staging_path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return AppIssue("conflict", ("destination_exists",), stage="stage")
    except OSError:
        return AppIssue("unavailable", ("io_error",), stage="stage")

    readback = staging_path.read_bytes()
    if hashlib.sha256(readback).hexdigest() != candidate.bytes_digest:
        return AppIssue("unavailable", ("readback_digest",), stage="stage")

    ev_ref = EvidenceRef(
        identity=f"evidence-stage-{sid}",
        scope="artifact-stage",
        operation_id=f"stage-{sid}",
        operation=OperationKey("gridcraft.stage", "1"),
        resource_versions=(
            ExpectedVersion(
                ResourceRef("app_document", candidate.target.identity.document_id), "1"
            ),
        ),
        content_digest=candidate.bytes_digest,
    )
    return StagedArtifact(
        staged_id=sid,
        candidate=candidate,
        staging_path=str(staging_path),
        bytes_digest=candidate.bytes_digest,
        size=len(data),
        stage_fact=ev_ref,
    )


def inspect_staged_artifact(
    staged: StagedArtifact, plan: MappingPlan
) -> tuple[CheckObservation, ...] | AppIssue:
    """Independently inspect staged workbook bytes against limits, XML rules, and plan content."""
    path = Path(staged.staging_path)
    if not path.is_file():
        return AppIssue("unavailable", ("staging_path",), stage="inspect")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != staged.bytes_digest:
        return AppIssue("conflict", ("staged_digest",), stage="inspect")

    try:
        chart, drawings = _extract_archive_xml(data)
        _verify_chart(chart)
        outside = ET.tostring(drawings).decode("utf-8")
        if "SAFE" not in outside:
            return AppIssue("conflict", ("outside_drawing",), stage="inspect")
    except (ValueError, KeyError, zipfile.BadZipFile) as err:
        words = ("Exceeds", "Encrypted", "Disallowed", "Suspicious", "External")
        code = "limit" if any(w in str(err) for w in words) else "conflict"
        return AppIssue(code, ("archive",), stage="inspect")

    book = cast(Any, openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=False))
    try:
        sheet = book["Report"]
        marker = staged.candidate.target.document_marker
        _verify_sheet_cells(sheet, marker, staged.candidate.run.run_id)
        for cell in plan.cells:
            actual = getattr(sheet[cell.address], "value", None)
            if actual != cell.value and str(actual or "") != str(cell.value or ""):
                return AppIssue("conflict", ("cells", cell.address), stage="inspect")
    except (ValueError, KeyError) as err:
        return AppIssue("conflict", ("sheet_content", str(err)), stage="inspect")
    finally:
        book.close()

    obs = _make_artifact_observation(
        staged, plan, CheckId.ARTIFACT_CONSISTENCY, "artifact_consistency_verified"
    )
    return (obs,)


async def reopen_staged_artifact(
    staged: StagedArtifact,
    plan: MappingPlan,
    page: Any,
    driver: BrowserDriver,
) -> tuple[CheckObservation, ...] | AppIssue:
    """Reopen exact staged bytes in a fresh verifier page context and assert observations."""
    path = Path(staged.staging_path)
    if not path.is_file():
        return AppIssue("unavailable", ("staging_path",), stage="reopen")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != staged.bytes_digest:
        return AppIssue("conflict", ("staged_digest",), stage="reopen")

    res = await driver.reopen(
        page, data, plan, staged.candidate.target.document_marker, staged.candidate.run.run_id
    )
    if isinstance(res, AppIssue):
        return res

    obs = _make_artifact_observation(
        staged, plan, CheckId.ARTIFACT_REOPEN, "artifact_reopen_verified"
    )
    return (obs,)
