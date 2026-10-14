"""Read-only semantic inspector for the reviewed reference workbook."""

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Literal, NamedTuple
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile
from zlib import error as CompressionError

from .contracts import ArtifactIdentity, CheckSet, Outcome, Rejected, StageFinding, Succeeded
from .fixture import CellExpectation, FixtureExpectation
from .xlsx_parts import NS, Parts, element, relation_id, require, text_at


class SourceReference(NamedTuple):
    sheet: str
    cell_range: str


def normalized_reference(value: str) -> SourceReference:
    reference = value.removeprefix("=")
    require(reference.count("!") == 1, "unsupported-chart-reference")
    sheet, cell_range = reference.split("!")
    if sheet.startswith("'"):
        require(sheet.endswith("'"), "invalid-sheet-quoting")
        quoted = sheet[1:-1]
        require(re.fullmatch(r"(?:[^']|'')+", quoted) is not None, "invalid-sheet-quoting")
        sheet = quoted.replace("''", "'")
    else:
        require("'" not in sheet, "invalid-sheet-quoting")
    require(bool(sheet) and "[" not in sheet and "]" not in sheet, "external-chart-reference")
    require(
        re.fullmatch(r"\$?[A-Za-z]+\$?[1-9][0-9]*:\$?[A-Za-z]+\$?[1-9][0-9]*", cell_range)
        is not None,
        "unsupported-chart-range",
    )
    return SourceReference(sheet.upper(), cell_range.replace("$", "").upper())


def string_content(node: ET.Element) -> str:
    return "".join(item.text or "" for item in node.findall(".//s:t", NS))


def indexed(nodes: list[ET.Element], raw: str) -> ET.Element:
    index = int(raw)
    require(0 <= index < len(nodes), "invalid-style-index")
    return nodes[index]


def cell_value(cell: ET.Element, strings: list[str]) -> CellExpectation:
    require(cell.find("s:f", NS) is None, "unexpected-cell-formula")
    kind = cell.get("t", "n")
    value = text_at(cell, "s:v")
    if kind == "s":
        index = int(value)
        require(0 <= index < len(strings), "shared-string-index")
        return CellExpectation(type="string", value=strings[index])
    if kind == "inlineStr":
        return CellExpectation(type="string", value=string_content(cell))
    if kind == "str":
        return CellExpectation(type="string", value=value)
    require(kind == "n", "unexpected-cell-type")
    return CellExpectation(type="number", value=float(value))


def check_cells(
    parts: Parts,
    book: str,
    sheet: ET.Element,
    expected: FixtureExpectation,
    phase: Literal["before", "after"],
) -> dict[str, ET.Element]:
    refs = parts.relationships(book)
    shared = [path for role, path in refs.values() if role == "sharedStrings"]
    require(len(shared) <= 1, "ambiguous-shared-strings")
    strings = [] if not shared else [string_content(item) for item in parts.root(shared[0])]
    nodes = sheet.findall("s:sheetData/s:row/s:c", NS)
    cells = {node.get("r", ""): node for node in nodes}
    require(len(cells) == len(nodes), "duplicate-cell")
    for address, wanted in (expected.before if phase == "before" else expected.after).items():
        require(address in cells, "missing-cell")
        require(cell_value(cells[address], strings) == wanted, "cell-mismatch-" + address)
    require(not sheet.findall(".//s:f", NS), "unexpected-cell-formula")
    return cells


def check_styles(
    parts: Parts, book: str, cells: dict[str, ET.Element], expected: FixtureExpectation
) -> None:
    styles = parts.root(parts.related(book, "styles"))
    formats = styles.findall("s:cellXfs/s:xf", NS)
    fonts = styles.findall("s:fonts/s:font", NS)
    custom = {
        item.get("numFmtId"): item.get("formatCode")
        for item in styles.findall("s:numFmts/s:numFmt", NS)
    }
    for address in expected.presentation.bold_cells:
        style = indexed(formats, cells[address].get("s", "0"))
        require(style.get("applyFont", "1") in ("1", "true"), "header-font-not-applied")
        bold = indexed(fonts, style.get("fontId", "0")).find("s:b", NS)
        require(bold is not None and bold.get("val", "1") in ("1", "true"), "header-bold")
    for address in expected.presentation.integer_cells:
        style = indexed(formats, cells[address].get("s", "0"))
        require(style.get("applyNumberFormat", "1") in ("1", "true"), "format-not-applied")
        number_id = style.get("numFmtId", "0")
        code = "0" if number_id == "1" else custom.get(number_id)
        require(code == expected.presentation.number_format, "integer-format")


def check_chart(chart: ET.Element, expected: FixtureExpectation) -> None:
    plot = element(chart, "c:chart/c:plotArea")
    charts = [node for node in plot if node.tag.endswith("Chart")]
    require(len(charts) == 1 and charts[0].tag == "{" + NS["c"] + "}lineChart", "chart-type")
    title = element(chart, "c:chart/c:title/c:tx/c:rich")
    require(
        "".join(node.text or "" for node in title.findall(".//a:t", NS)) == expected.chart.title,
        "chart-title",
    )
    series = charts[0].findall("c:ser", NS)
    require(len(series) == 1, "chart-series-count")
    require(text_at(series[0], "c:tx/c:v") == expected.chart.series_name, "chart-series-name")
    for key, formula in (("cat", expected.chart.categories), ("val", expected.chart.values)):
        formulas = series[0].findall(f"c:{key}/*/c:f", NS)
        require(
            len(formulas) == 1
            and normalized_reference(formulas[0].text or "") == normalized_reference(formula),
            "chart-binding-" + key,
        )
    legend = chart.find("c:chart/c:legend", NS)
    wanted = expected.presentation.legend
    require((legend is not None) == wanted.visible, "chart-legend-visibility")
    if legend is not None:
        require(
            element(legend, "c:legendPos").get("val") == wanted.position, "chart-legend-position"
        )
        overlay = legend.find("c:overlay", NS)
        actual = overlay is not None and overlay.get("val", "1") in ("1", "true")
        require(actual == wanted.overlay, "chart-legend-overlay")


def column_width(sheet: ET.Element, index: int) -> float:
    width = 64.0
    default = sheet.find("s:sheetFormatPr", NS)
    if default is not None and default.get("defaultColWidth"):
        width = int(float(default.get("defaultColWidth", "8.43")) * 7 + 0.5) + 5
    for col in sheet.findall("s:cols/s:col", NS):
        if int(col.get("min", "0")) <= index + 1 <= int(col.get("max", "0")):
            width = int(float(col.get("width", "8.43")) * 7 + 0.5) + 5
    return width


def row_height(sheet: ET.Element, index: int) -> float:
    default = sheet.find("s:sheetFormatPr", NS)
    height = float(default.get("defaultRowHeight", "15")) if default is not None else 15.0
    for row in sheet.findall("s:sheetData/s:row", NS):
        if int(row.get("r", "0")) == index + 1:
            height = float(row.get("ht", str(height)))
    return height * 4 / 3


def check_anchor(anchor: ET.Element, sheet: ET.Element, expected: FixtureExpectation) -> None:
    require(
        anchor.tag in ("{" + NS["x"] + "}twoCellAnchor", "{" + NS["x"] + "}oneCellAnchor"),
        "unsupported-chart-anchor",
    )
    start = element(anchor, "x:from")
    col, row = int(text_at(start, "x:col")), int(text_at(start, "x:row"))
    require((col, row) == (5, 1), "chart-anchor")
    offsets = (int(text_at(start, "x:colOff")), int(text_at(start, "x:rowOff")))
    wanted = expected.presentation
    require(
        offsets == (wanted.chart_offset_pixels.x * 9525, wanted.chart_offset_pixels.y * 9525),
        "chart-offset",
    )
    end = anchor.find("x:to", NS)
    if end is None:
        extent = element(anchor, "x:ext")
        width, height = float(extent.get("cx", "0")) / 9525, float(extent.get("cy", "0")) / 9525
    else:
        last_col, last_row = int(text_at(end, "x:col")), int(text_at(end, "x:row"))
        require(col <= last_col <= 100 and row <= last_row <= 100, "anchor-bounds")
        width = sum(column_width(sheet, i) for i in range(col, last_col))
        height = sum(row_height(sheet, i) for i in range(row, last_row))
        width += (int(text_at(end, "x:colOff")) - offsets[0]) / 9525
        height += (int(text_at(end, "x:rowOff")) - offsets[1]) / 9525
    require(
        abs(width - wanted.chart_size_pixels.width) < 0.01
        and abs(height - wanted.chart_size_pixels.height) < 0.01,
        "chart-size",
    )


def compare(parts: Parts, expected: FixtureExpectation, phase: Literal["before", "after"]) -> None:
    book = parts.related("", "officeDocument")
    sheets = parts.root(book).findall("s:sheets/s:sheet", NS)
    require(len(sheets) == 1 and sheets[0].get("name") == expected.sheet, "sheet-identity")
    sheet_name = parts.related(book, "worksheet", relation_id(sheets[0]))
    sheet = parts.root(sheet_name)
    cells = check_cells(parts, book, sheet, expected, phase)
    check_styles(parts, book, cells, expected)
    drawings = sheet.findall("s:drawing", NS)
    require(len(drawings) == 1, "missing-or-ambiguous-drawing")
    drawing_name = parts.related(sheet_name, "drawing", relation_id(drawings[0]))
    drawing = parts.root(drawing_name)
    charts = drawing.findall(".//c:chart", NS)
    require(len(charts) == expected.chart.count, "chart-count")
    anchors = [anchor for anchor in drawing if anchor.find(".//c:chart", NS) is not None]
    require(len(anchors) == 1, "chart-anchor-count")
    check_anchor(anchors[0], sheet, expected)
    check_chart(parts.root(parts.related(drawing_name, "chart", relation_id(charts[0]))), expected)
    require(
        not any(
            role in ("vbaProject", "externalLink")
            for name in parts.xml
            for role, _ in parts.relationships(name).values()
        ),
        "unsupported-workbook-link",
    )


def inspect(
    path: Path, expected: FixtureExpectation, phase: Literal["before", "after"] = "after"
) -> Outcome[CheckSet]:
    """Inspect a known source path; saved outputs must use inspect_artifact for binding."""
    try:
        require(phase in ("before", "after"), "invalid-phase")
        require(path.stat().st_size <= 4_000_000, "archive-size")
        with path.open("rb") as stream:
            data = stream.read(4_000_001)
        return inspect_bytes(data, expected, phase)
    except (
        OSError,
        BadZipFile,
        ValueError,
        KeyError,
        IndexError,
        ET.ParseError,
        RuntimeError,
        OverflowError,
        CompressionError,
    ):
        return rejected("artifact-semantics-or-safety-rejected")


def inspect_bytes(
    data: bytes, expected: FixtureExpectation, phase: Literal["before", "after"]
) -> Outcome[CheckSet]:
    try:
        require(len(data) <= 4_000_000, "archive-size")
        require(phase in ("before", "after"), "invalid-phase")
        with ZipFile(BytesIO(data)) as archive:
            compare(Parts(archive), expected, phase)
    except (
        BadZipFile,
        ValueError,
        KeyError,
        IndexError,
        ET.ParseError,
        RuntimeError,
        OverflowError,
        CompressionError,
    ):
        return rejected("artifact-semantics-or-safety-rejected")
    checks = tuple("typed-cell-" + address for address in expected.before) + (
        "sheet-identity",
        "marker-and-sentinels",
        "bold-headers",
        "integer-formats",
        "chart-count-and-type",
        "chart-literal-title-and-series",
        "chart-category-binding",
        "chart-values-binding",
        "chart-legend",
        "chart-anchor-offset-and-size",
        "archive-safety",
    )
    findings = tuple(
        StageFinding(
            stage="byte-inspection",
            requirements=("4.5", "4.7"),
            status="passed",
            expected=(check, phase),
            observed=(check, phase),
        )
        for check in checks
    )
    return Succeeded(payload=CheckSet(findings=findings))


def rejected(code: str) -> Rejected:
    return Rejected(
        finding=StageFinding(
            stage="byte-inspection", requirements=("4.5", "4.7"), status="failed", observed=(code,)
        )
    )


def inspect_artifact(
    artifact: ArtifactIdentity,
    expected: FixtureExpectation,
    phase: Literal["before", "after"] = "after",
) -> Outcome[CheckSet]:
    """Bind actual retained output bytes to the recorded size/hash before inspection."""
    try:
        require(artifact.size <= 4_000_000, "archive-size")
        with artifact.destination.open("rb") as stream:
            data = stream.read(4_000_001)
        require(
            len(data) == artifact.size and hashlib.sha256(data).hexdigest() == artifact.sha256,
            "artifact-identity-mismatch",
        )
    except (OSError, ValueError):
        return rejected("artifact-identity-rejected")
    return inspect_bytes(data, expected, phase)
