"""Fixed-profile mapping and text-safe XlsxWriter bootstrap, without app IO."""

import io
import json
import unicodedata
from hashlib import sha256
from typing import cast

import xlsxwriter  # pyright: ignore[reportMissingTypeStubs] -- pinned library lacks py.typed
from xlsxwriter.exceptions import XlsxWriterException  # pyright: ignore[reportMissingTypeStubs]
from xlsxwriter.format import Format  # pyright: ignore[reportMissingTypeStubs]

from craftreport.contracts.identity import CapabilityRequirement
from craftreport.contracts.pins import VersionPin
from craftreport.data.values import Field
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedColumn, PreparedReport
from craftreport.themes.values import (
    ChartStyle,
    GridStyle,
    ResolvedTheme,
    TextStyle,
    ValueFormat,
)
from craftreport.themes.values import (
    SemanticRole as R,
)
from craftreport_gridcraft.codecs import mapping_pins_match, prepared_content_matches
from craftreport_gridcraft.values import (
    PROFILE,
    AppIssue,
    Cell,
    MappingPlan,
    OwnedLayout,
    profile_matches,
)

THEME = ResolvedTheme(
    VersionPin(
        "public/gridcraft-fixed-theme",
        "1.0.0",
        "f8c0a8b07dae4377cc31f62de1bf9d76e027a239a73535fa6762e4e57ed5d980",
    ),
    tuple(
        (
            r,
            TextStyle(
                "Arial",
                11,
                r in (R.TITLE, R.HEADER, R.DRAFT),
                False,
                "#000000",
                "#DCE6F1" if r in (R.HEADER, R.DRAFT) else None,
                "left",
                True,
            ),
        )
        for r in R
    ),
    (ValueFormat("text"), ValueFormat("int64", 2)),
    ChartStyle(("#4472C4",), 2.25, False, False),
    GridStyle(False, 24, 18),
)
_COLUMNS = tuple(
    PreparedColumn(field, field.label, role, fmt)
    for field, role, fmt in (
        (Field("category", "Category", "text", False), R.ROW_LABEL, ValueFormat("text")),
        (Field("value", "Value", "int64", False), R.OUTPUT, ValueFormat("int64", 2)),
        (Field("literal", "Literal", "text", False), R.NOTE, ValueFormat("text")),
    )
)


def validate_mapping(
    prepared: PreparedReport, quality: QualityEvaluation, layout: OwnedLayout
) -> MappingPlan | AppIssue:
    return _candidate_mapping(prepared, quality, layout)


def _candidate_mapping(
    prepared: PreparedReport, quality: QualityEvaluation, layout: OwnedLayout
) -> MappingPlan | AppIssue:
    """Validate the exact mapping shared by public admission and isolated fidelity checks."""
    if layout.profile != PROFILE or not profile_matches(layout.target):
        return AppIssue("untested", ("profile",))
    if not mapping_pins_match(prepared, quality, layout.run):
        return AppIssue("conflict", ("run",))
    if (
        prepared.definition,
        prepared.template,
        prepared.theme,
        prepared.pack.version_pin,
        prepared.snapshot,
        prepared.content_digest,
    ) != (
        layout.definition,
        layout.template,
        layout.theme,
        layout.pack,
        layout.snapshot,
        layout.prepared_digest,
    ):
        return AppIssue("conflict", ("pins",))
    if prepared.presentation != THEME or prepared.theme != THEME.version_pin:
        return AppIssue("untested", ("presentation",))
    expected = tuple(
        CapabilityRequirement(c, ">=1,<2")
        for c in ("report.table", "report.line_chart", "report.semantic_style")
    )
    if prepared.required_capabilities != expected:
        return AppIssue("unsupported", ("required_capabilities",))
    if not quality.draft_eligible or any(
        f.scope.content_digest != prepared.content_digest
        or f.scope.validation_scope_digest != layout.run.validation_scope
        for f in quality.findings
    ):
        return AppIssue("conflict", ("quality",))
    if len(json.dumps(quality.validation_summary, ensure_ascii=False).encode()) > 1024:
        return AppIssue("limit", ("quality", "validation_summary"))
    issue = _content_issue(prepared)
    if issue is None and not prepared_content_matches(prepared):
        return AppIssue("conflict", ("prepared", "content_digest"))
    return issue or MappingPlan(prepared, quality, layout, _cells(prepared, quality, layout))


def _content_issue(prepared: PreparedReport) -> AppIssue | None:
    if len(prepared.tables) != 1 or len(prepared.charts) != 1:
        return AppIssue("unsupported", ("content",))
    table, chart = prepared.tables[0], prepared.charts[0]
    if (
        prepared.title != "Supplied series"
        or table.identity != "report_table"
        or table.columns != _COLUMNS
        or len(table.rows) != 4
        or table.null_text != "—"
        or chart.identity != "report_line"
        or chart.category_schema != _COLUMNS[0].field
        or chart.categories != tuple(row[0] for row in table.rows)
        or len(chart.series) != 1
    ):
        return AppIssue("unsupported", ("content",))
    series = chart.series[0]
    if (series.identity, series.label, series.field, series.role, series.format) != (
        "series",
        "Series",
        Field("series_value", "Series", "int64", True),
        R.OUTPUT,
        ValueFormat("int64", 2),
    ) or tuple(v is None for v in series.values) != (False, True, False, False):
        return AppIssue("unsupported", ("charts", 0, "series", 0))
    for i, row in enumerate(table.rows):
        for j, value in enumerate(row):
            issue = _value_issue(value, ("tables", 0, "rows", i, j), 16 if j == 0 else 32)
            if issue:
                return issue
    for i, value in enumerate(series.values):
        if value is not None:
            issue = _value_issue(value, ("charts", 0, "series", 0, "values", i))
            if issue:
                return issue
    return None


def _value_issue(
    value: object, location: tuple[str | int, ...], text_limit: int = 32
) -> AppIssue | None:
    if type(value) is int and not 0 <= value <= 9999:
        return AppIssue("limit", location)
    if type(value) is str:
        if any(unicodedata.category(c) in ("Cc", "Cf", "Cs", "Zl", "Zp") for c in value):
            return AppIssue("untested", location)
        if len(json.dumps(value, ensure_ascii=False).encode()) > text_limit:
            return AppIssue("limit", location)
    return None


def _cells(p: PreparedReport, q: QualityEvaluation, layout: OwnedLayout) -> tuple[Cell, ...]:
    cells = [
        Cell("A1", q.draft_designation, R.DRAFT),
        Cell("A2", p.title, R.TITLE),
        Cell("A3", q.validation_summary, R.NOTE),
    ]
    table, chart = p.tables[0], p.charts[0]
    for j, column in enumerate(table.columns):
        cells.append(Cell(f"{chr(65 + j)}5", column.display_label, R.HEADER))
        cells.extend(
            Cell(f"{chr(65 + j)}{6 + i}", cast(str | int, row[j]), column.role)
            for i, row in enumerate(table.rows)
        )
    cells.extend((Cell("F5", "Category", R.HEADER), Cell("G5", "Series", R.HEADER)))
    cells.extend(
        Cell(f"F{6 + i}", cast(str, v), R.ROW_LABEL) for i, v in enumerate(chart.categories)
    )
    cells.extend(
        Cell(f"G{6 + i}", cast(int | None, v), R.OUTPUT)
        for i, v in enumerate(chart.series[0].values)
    )
    pins = (p.definition, p.template, p.theme, p.pack.version_pin, layout.profile.pin)
    metadata = [
        ("document", layout.document_marker, None),
        ("run", layout.run.run_id, None),
        (
            "snapshot",
            f"{p.snapshot.feed_id}@{p.snapshot.producer_version}",
            p.snapshot.content_digest,
        ),
        ("prepared", p.content_digest, None),
        *(
            (label, f"{pin.identity}@{pin.version}", pin.content_digest)
            for label, pin in zip(
                ("definition", "template", "theme", "pack", "profile"), pins, strict=True
            )
        ),
        ("designation", q.draft_designation, None),
        ("summary_sha256", sha256(q.validation_summary.encode()).hexdigest(), None),
        ("quality_scope", q.scope_label, None),
    ]
    for row, (label, value, digest) in enumerate(metadata, 1):
        cells.extend((Cell(f"J{row}", label, R.HEADER), Cell(f"K{row}", value, R.SOURCE)))
        if digest is not None:
            cells.append(Cell(f"L{row}", digest, R.SOURCE))
    return tuple(cells)


def bootstrap(plan: MappingPlan, document_marker: str) -> bytes | AppIssue:
    if document_marker != plan.layout.document_marker:
        return AppIssue("conflict", ("document_marker",), "bootstrap")
    checked = _candidate_mapping(plan.prepared, plan.quality, plan.layout)
    if isinstance(checked, AppIssue) or checked != plan:
        return AppIssue("conflict", ("plan",), "bootstrap")
    output = io.BytesIO()
    try:
        with xlsxwriter.Workbook(
            output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
        ) as book:
            _write(book, plan)
    except (OSError, ValueError, XlsxWriterException):
        return AppIssue("unavailable", ("workbook",), "bootstrap")
    return output.getvalue()


def _write(book: xlsxwriter.Workbook, plan: MappingPlan) -> None:
    sheet = book.add_worksheet("Report")  # pyright: ignore[reportUnknownMemberType]
    formats: dict[R, Format] = {}
    for role, style in THEME.styles:
        properties: dict[str, object] = {
            "font_name": style.font_family,
            "font_size": style.size_pt,
            "bold": style.bold,
            "italic": style.italic,
            "font_color": style.color,
            "align": style.alignment,
            "text_wrap": style.wrap,
        }
        if style.fill:
            properties["bg_color"] = style.fill
        formats[role] = book.add_format(properties)  # pyright: ignore[reportUnknownMemberType]
    numeric = book.add_format(  # pyright: ignore[reportUnknownMemberType]
        {
            "font_name": "Arial",
            "font_size": 11,
            "font_color": "#000000",  # pyright: ignore[reportUnknownMemberType]
            "align": "left",
            "text_wrap": True,
            "num_format": "0.00;-0.00",
        }
    )
    sheet.hide_gridlines(2)
    sheet.set_column(0, 11, 18)
    sheet.set_row(4, 24)
    sheet.set_row(2, 160)
    for cell in plan.cells:
        row, col = int(cell.address[1:]) - 1, ord(cell.address[0]) - 65
        fmt = numeric if cell.role is R.OUTPUT else formats[cell.role]
        if cell.address == "A3":
            result = sheet.merge_range(2, 0, 2, 7, cell.value, fmt)
        elif type(cell.value) is str:
            result = sheet.write_string(row, col, cell.value, fmt)
        elif cell.value is None:
            result = sheet.write_blank(row, col, None, fmt)
        else:
            result = sheet.write_number(row, col, cast(int, cell.value), fmt)
        if result != 0:
            raise ValueError("Cell write failed")
    chart = book.add_chart({"type": "line"})
    assert chart is not None
    chart.add_series(
        {
            "name": "Report!$G$5",
            "categories": "Report!$F$6:$F$9",
            "values": "Report!$G$6:$G$9",
            "line": {"color": "#4472C4", "width": 2.25},
        }
    )
    chart.set_title({"name": plan.prepared.title})
    chart.set_legend({"none": True})
    chart.set_y_axis({"major_gridlines": {"visible": False}})
    chart.show_blanks_as("gap")
    sheet.insert_chart(17, 0, chart, {"x_scale": 1.4, "y_scale": 1.2})
    sheet.write_string(0, 12, "OUTSIDE-UNCHANGED")
    sheet.insert_textbox(2, 12, "SAFE", {"width": 120, "height": 35})
