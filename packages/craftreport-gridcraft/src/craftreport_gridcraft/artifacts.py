"""Read-only bounded workbook byte inspection for scratch inspection saves."""

from __future__ import annotations

import hashlib
import io
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, cast

import openpyxl  # pyright: ignore[reportMissingTypeStubs]

from craftreport_gridcraft.values import AppIssue

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
        parts = {p: archive.read(p) for p in archive.namelist()}
        for name, content in parts.items():
            if b"<!DOCTYPE" in content or b"<!ENTITY" in content:
                raise ValueError(f"Suspicious XML entity or DOCTYPE in {name}")
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
