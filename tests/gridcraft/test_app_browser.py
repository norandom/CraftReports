"""Tests for released browser session, same-document observation, and workbook byte inspection."""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
import xlsxwriter  # pyright: ignore[reportMissingTypeStubs]
from craftreport_gridcraft.app_values import (
    AppSettings,
    BrowserTarget,
    SavedCandidate,
    TargetObservation,
)
from craftreport_gridcraft.artifacts import (
    inspect_workbook_bytes,
    verify_scratch_artifact,
)
from craftreport_gridcraft.browser import RECEIVER_SCRIPT, BrowserDriver
from craftreport_gridcraft.values import (
    AppIssue,
    Cell,
    MappingPlan,
    OwnedLayout,
)

from craftreport.contracts.pins import VersionPin
from craftreport.policies.values import CheckId, QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins


def valid_fixture_bytes(marker: str, run_id: str = "run-1") -> bytes:
    output = io.BytesIO()
    with xlsxwriter.Workbook(
        output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    ) as book:
        sheet = book.add_worksheet("Report")  # pyright: ignore[reportUnknownMemberType]
        bold = book.add_format({"bold": True, "bg_color": "#DCE6F1"})  # pyright: ignore[reportUnknownMemberType]
        numeric = book.add_format({"num_format": "0.00;-0.00"})  # pyright: ignore[reportUnknownMemberType]
        sheet.write_string(0, 0, "DRAFT", bold)
        sheet.write_string(0, 9, marker)
        sheet.write_string(1, 9, run_id)
        sheet.write_string(0, 12, "OUTSIDE-UNCHANGED")
        for addr, val in {
            "A5": "Category",
            "B5": "Value",
            "C5": "Literal",
            "A6": "Alpha",
            "A7": "Beta",
            "A8": "Gamma",
            "C6": "=1+1",
            "F5": "Category",
            "G5": "Series",
            "F6": "Alpha",
            "F7": "Beta",
            "F8": "Gamma",
            "A9": "Delta",
            "F9": "Delta",
        }.items():
            sheet.write_string(int(addr[1:]) - 1, ord(addr[0]) - 65, val)
        for addr, num in {"B6": 10, "B8": 30, "G6": 10, "G8": 30, "B9": 20, "G9": 20}.items():
            sheet.write_number(int(addr[1:]) - 1, ord(addr[0]) - 65, num, numeric)
        sheet.write_blank(6, 1, None, numeric)
        sheet.write_blank(6, 6, None, numeric)
        chart = book.add_chart({"type": "line"})
        assert chart is not None
        chart.add_series(
            {
                "name": "Report!$G$5",
                "categories": "Report!$F$6:$F$9",
                "values": "Report!$G$6:$G$9",
                "line": {"color": "#4472C4"},
            }
        )
        chart.set_title({"name": "Supplied series"})
        chart.show_blanks_as("gap")
        sheet.insert_chart(17, 0, chart, {"x_scale": 0.8, "y_scale": 0.8})
        sheet.insert_textbox(2, 12, "SAFE", {"width": 120, "height": 35})
    return output.getvalue()


@pytest.fixture
def plan(
    prepared: PreparedReport,
    quality: QualityEvaluation,
    run: RunPins,
    browser_target: BrowserTarget,
) -> MappingPlan:
    layout = OwnedLayout(browser_target, run)
    cells = (
        Cell("A5", "Category", cast(Any, "row_label")),
        Cell("B5", "Value", cast(Any, "output")),
        Cell("C5", "Literal", cast(Any, "note")),
        Cell("A6", "Alpha", cast(Any, "row_label")),
        Cell("B6", 10, cast(Any, "output")),
        Cell("C6", "=1+1", cast(Any, "note")),
    )
    return MappingPlan(prepared, quality, layout, cells)


@pytest.fixture
def settings(browser_target: BrowserTarget) -> AppSettings:
    return AppSettings(
        origin=browser_target.origin,
        deployment_id=browser_target.deployment_id,
        context_id=browser_target.context_id,
        principal_id="principal-1",
        artifact_root="D:/artifacts",
        destination_ids=("dest-1",),
        archive_digest=browser_target.archive_digest,
        javascript_digest=browser_target.javascript_digest,
        wasm_digest=browser_target.wasm_digest,
        profile_pin=browser_target.profile_pin,
    )


def test_inspect_workbook_bytes_success() -> None:
    data = valid_fixture_bytes("doc-marker-123", "run-1")
    inspected = inspect_workbook_bytes(data, "doc-marker-123", "run-1")
    assert inspected["marker"] == "doc-marker-123"
    assert inspected["run"] == "run-1"
    assert "SAFE" in str(inspected["outside"])
    assert inspected["categories"] == ["Alpha", "Beta", "Gamma", "Delta"]

    verified = verify_scratch_artifact(data, "doc-marker-123", "run-1")
    assert isinstance(verified, dict)
    assert verified["marker"] == "doc-marker-123"


def test_inspect_workbook_bytes_rejects_oversized_and_limits() -> None:
    huge = b"PK" + b"\x00" * (4194304 + 1)
    with pytest.raises(ValueError, match="Exceeds maximum compressed size"):
        inspect_workbook_bytes(huge, "m", "r")

    issue = verify_scratch_artifact(huge, "m", "r")
    assert isinstance(issue, AppIssue)
    assert issue.code == "limit"
    assert issue.stage == "inspect"


def test_inspect_workbook_bytes_rejects_xml_entities() -> None:
    valid = valid_fixture_bytes("m", "r")
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(valid)) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "xl/charts/chart1.xml":
                content = b"<!DOCTYPE chart [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]>" + content
            dst.writestr(item, content)

    tampered = buf.getvalue()
    with pytest.raises(ValueError, match="Suspicious XML entity"):
        inspect_workbook_bytes(tampered, "m", "r")

    issue = verify_scratch_artifact(tampered, "m", "r")
    assert isinstance(issue, AppIssue)
    assert issue.code == "conflict"


def test_inspect_workbook_bytes_rejects_mismatched_marker_or_sentinel() -> None:
    data = valid_fixture_bytes("marker-A", "run-1")

    # Mismatched marker
    with pytest.raises(ValueError, match="Marker mismatch"):
        inspect_workbook_bytes(data, "marker-WRONG", "run-1")

    # Mismatched run
    with pytest.raises(ValueError, match="Run mismatch"):
        inspect_workbook_bytes(data, "marker-A", "run-WRONG")


class FakePage:
    def __init__(self, cells: dict[str, str], lane: dict[str, Any] | None = None) -> None:
        self.cells = cells
        self.lane = lane or {"armed": False, "count": 0, "failed": False, "candidate": None}
        self.context = self
        self.mouse = self
        self.keyboard = self
        self.frames = [self]
        self.permissions: list[tuple[list[str], str]] = []
        self.evaluations: list[str] = []
        self._last_click: tuple[int, int] = (0, 0)
        self._current_address: str = "A1"
        self._last_clipboard: str = ""
        self.typed_edits: list[tuple[str, str]] = []
        self.fail_on_edit_index: int | None = None

    async def grant_permissions(self, perms: list[str], origin: str) -> None:
        self.permissions.append((perms, origin))

    async def evaluate(self, script: str, *args: Any) -> Any:
        self.evaluations.append(script)
        if "window.saveLane.candidate.bytes" in script:
            candidate = self.lane.get("candidate")
            if isinstance(candidate, dict):
                raw = cast(dict[str, object], candidate).get("bytes", [])
                return cast(list[int], raw)
            return []
        if "window.saveLane.candidate" in script:
            return self.lane.get("candidate")
        if "window.saveLane.failed" in script:
            return self.lane.get("failed")
        if "window.saveLane" in script:
            return self.lane
        if "navigator.clipboard.readText" in script:
            return self._last_clipboard
        return None

    async def click(self, x: int, y: int) -> None:
        self._last_click = (x, y)

    async def press(self, chord: str) -> None:
        pass

    async def insert_text(self, text: str) -> None:
        if self._last_click == (60, 179):
            self._current_address = text
            self._last_clipboard = text
        elif self._last_click == (300, 179):
            if (
                self.fail_on_edit_index is not None
                and len(self.typed_edits) >= self.fail_on_edit_index
            ):
                raise RuntimeError("Simulated mid-update browser failure")
            clean = text[1:] if text.startswith("'") else text
            if clean.isdigit():
                clean = f"{clean}.00"
            self.cells[self._current_address] = clean
            self.typed_edits.append((self._current_address, text))

    def locator(self, selector: str) -> FakePage:
        return self

    async def focus(self) -> None:
        self._last_clipboard = self.cells.get(self._current_address, "")


def test_receiver_script_contains_required_events() -> None:
    assert "gridcraft:ready" in RECEIVER_SCRIPT
    assert "gridcraft:save" in RECEIVER_SCRIPT
    assert "gridcraft:failed" in RECEIVER_SCRIPT
    assert "saveLane" in RECEIVER_SCRIPT


@pytest.mark.anyio
async def test_browser_driver_open_report_validations(
    plan: MappingPlan, settings: AppSettings, browser_target: BrowserTarget
) -> None:
    driver = BrowserDriver(settings)

    # 1. Profile mismatch
    untested_plan = replace(
        plan,
        layout=replace(
            plan.layout,
            target=replace(browser_target, profile_pin=VersionPin("untested", "1", "a" * 64)),
        ),
    )
    fake = FakePage({})
    res1 = await driver.open_report(untested_plan, cast(Any, fake), "m1", bootstrap_data=b"data")
    assert isinstance(res1, AppIssue)
    assert res1.code == "untested"
    assert res1.location == ("profile",)

    # 2. Origin mismatch
    origin_mismatch_plan = replace(
        plan,
        layout=replace(
            plan.layout,
            target=replace(browser_target, origin="http://other-host:8080"),
        ),
    )
    res2 = await driver.open_report(
        origin_mismatch_plan, cast(Any, fake), "m1", bootstrap_data=b"data"
    )
    assert isinstance(res2, AppIssue)
    assert res2.code == "conflict"
    assert res2.location == ("origin",)

    # 3. Marker mismatch in opened cells
    mismatch_page = FakePage(
        {"J1": "wrong-marker", "J2": plan.layout.run.run_id, "M1": "OUTSIDE-UNCHANGED"}
    )
    res3 = await driver.open_report(plan, cast(Any, mismatch_page), "m1", bootstrap_data=b"data")
    assert isinstance(res3, AppIssue)
    assert res3.code == "conflict"
    assert res3.location == ("document_marker",)

    # 4. Successful open
    success_page = FakePage({"J1": "m1", "J2": plan.layout.run.run_id, "M1": "OUTSIDE-UNCHANGED"})
    res4 = await driver.open_report(plan, cast(Any, success_page), "m1", bootstrap_data=b"data")
    assert isinstance(res4, BrowserTarget)
    assert res4.document_marker == "m1"
    assert res4.deployment_id == settings.deployment_id
    assert res4.origin == settings.origin


@pytest.mark.anyio
async def test_browser_driver_observe_success_and_conflicts(
    plan: MappingPlan, settings: AppSettings, browser_target: BrowserTarget, run: RunPins
) -> None:
    driver = BrowserDriver(settings)

    # 1. Target mismatch
    other_target = replace(
        browser_target, identity=replace(browser_target.identity, document_id="other")
    )
    fake = FakePage({})
    res1 = await driver.observe(other_target, run, plan, cast(Any, fake))
    assert isinstance(res1, AppIssue)
    assert res1.code == "conflict"
    assert res1.location == ("target",)

    # 2. Marker mismatch
    page_mismatch = FakePage({"J1": "different", "J2": run.run_id, "M1": "OUTSIDE-UNCHANGED"})
    res2 = await driver.observe(browser_target, run, plan, cast(Any, page_mismatch))
    assert isinstance(res2, AppIssue)
    assert res2.code == "conflict"
    assert res2.location == ("document_marker",)

    # 3. Successful observation
    cell_data = {
        "J1": browser_target.document_marker,
        "J2": run.run_id,
        "M1": "OUTSIDE-UNCHANGED",
        "A5": "Category",
        "B5": "Value",
        "C5": "Literal",
        "A6": "Alpha",
        "B6": "10.00",
        "C6": "=1+1",
    }
    page_success = FakePage(cell_data)
    obs = await driver.observe(browser_target, run, plan, cast(Any, page_success))
    assert isinstance(obs, TargetObservation)
    assert obs.target == browser_target
    assert obs.run == run
    assert obs.revision == 1
    assert len(obs.findings) == 2
    assert obs.findings[0].check_id is CheckId.LAYOUT_FIT
    assert obs.findings[1].check_id is CheckId.TARGET_CONSISTENCY
    assert len(obs.evidence) == 1


@pytest.mark.anyio
async def test_browser_driver_capture_inspection_save(
    settings: AppSettings, browser_target: BrowserTarget, run: RunPins, tmp_path: Path
) -> None:
    driver = BrowserDriver(settings)

    # 1. Failed save lane returns AppIssue conflict
    failed_page = FakePage({}, lane={"armed": False, "count": 1, "failed": True, "candidate": None})
    res1 = await driver.capture_inspection_save(
        cast(Any, failed_page), browser_target, run, tmp_path, "test1"
    )
    assert isinstance(res1, AppIssue)
    assert res1.code == "conflict"
    assert res1.location == ("save_lane",)

    # 2. Successful save
    data = b"PK\x03\x04test_candidate"
    cand_dict = {"name": "candidate.xlsx", "bytes": list(data)}
    success_page = FakePage(
        {}, lane={"armed": True, "count": 1, "failed": False, "candidate": cand_dict}
    )
    res2 = await driver.capture_inspection_save(
        cast(Any, success_page), browser_target, run, tmp_path, "test2"
    )
    assert isinstance(res2, tuple)
    cand, saved_bytes = res2
    assert isinstance(cand, SavedCandidate)
    assert cand.purpose == "inspection"
    assert saved_bytes == data
    saved_file = tmp_path / "test2.xlsx"
    assert saved_file.is_file()
    assert saved_file.read_bytes() == data


@pytest.mark.anyio
async def test_browser_driver_apply_two_sequential_runs_and_preserve_outside(
    plan: MappingPlan, settings: AppSettings, browser_target: BrowserTarget, run: RunPins
) -> None:
    driver = BrowserDriver(settings)
    cell_data = {
        "J1": browser_target.document_marker,
        "J2": run.run_id,
        "M1": "OUTSIDE-UNCHANGED",
        "A5": "Category",
        "B5": "Value",
        "C5": "Literal",
        "A6": "Alpha",
        "B6": "10.00",
        "C6": "=1+1",
    }
    page = FakePage(cell_data)
    obs1 = await driver.observe(browser_target, run, plan, cast(Any, page))
    assert isinstance(obs1, TargetObservation)

    # Run 2 updates A6, B6, C6 and J2
    run2 = replace(run, run_id="run-2")
    cells2 = (
        Cell("J2", "run-2", cast(Any, "source")),
        Cell("A5", "Category", cast(Any, "row_label")),
        Cell("B5", "Value", cast(Any, "output")),
        Cell("C5", "Literal", cast(Any, "note")),
        Cell("A6", "Alpha-2", cast(Any, "row_label")),
        Cell("B6", 42, cast(Any, "output")),
        Cell("C6", "=2+2", cast(Any, "note")),
    )
    plan2 = MappingPlan(plan.prepared, plan.quality, OwnedLayout(browser_target, run2), cells2)
    obs2 = await driver.apply(plan2, run2, obs1, cast(Any, page), before_plan=plan)
    assert isinstance(obs2, TargetObservation)
    assert obs2.revision == 2
    assert obs2.before_fingerprint == obs1.after_fingerprint
    assert obs2.after_fingerprint != obs1.after_fingerprint
    assert obs2.outside_fingerprint == obs1.outside_fingerprint
    assert page.cells["M1"] == "OUTSIDE-UNCHANGED"
    assert page.cells["A6"] == "Alpha-2"
    assert page.cells["B6"] == "42.00"
    assert page.cells["C6"] == "=2+2"
    # Strings were prefixed with ' when typed into formula bar
    assert ("C6", "'=2+2") in page.typed_edits

    # Run 3 updates again on the same document
    run3 = replace(run, run_id="run-3")
    cells3 = (
        Cell("J2", "run-3", cast(Any, "source")),
        Cell("A5", "Category", cast(Any, "row_label")),
        Cell("B5", "Value", cast(Any, "output")),
        Cell("C5", "Literal", cast(Any, "note")),
        Cell("A6", "Alpha-3", cast(Any, "row_label")),
        Cell("B6", 99, cast(Any, "output")),
        Cell("C6", "=3+3", cast(Any, "note")),
    )
    plan3 = MappingPlan(plan.prepared, plan.quality, OwnedLayout(browser_target, run3), cells3)
    obs3 = await driver.apply(plan3, run3, obs2, cast(Any, page), before_plan=plan2)
    assert isinstance(obs3, TargetObservation)
    assert obs3.revision == 3
    assert obs3.before_fingerprint == obs2.after_fingerprint
    assert page.cells["A6"] == "Alpha-3"
    assert page.cells["B6"] == "99.00"
    assert page.cells["M1"] == "OUTSIDE-UNCHANGED"


@pytest.mark.anyio
async def test_browser_driver_apply_conflicts_and_partial_effects(
    plan: MappingPlan, settings: AppSettings, browser_target: BrowserTarget, run: RunPins
) -> None:
    driver = BrowserDriver(settings)
    cell_data = {
        "J1": browser_target.document_marker,
        "J2": run.run_id,
        "M1": "OUTSIDE-UNCHANGED",
        "A5": "Category",
        "B5": "Value",
        "C5": "Literal",
        "A6": "Alpha",
        "B6": "10.00",
        "C6": "=1+1",
    }
    page = FakePage(cell_data)
    obs1 = await driver.observe(browser_target, run, plan, cast(Any, page))
    assert isinstance(obs1, TargetObservation)

    run2 = replace(run, run_id="run-2")
    cells2 = (
        Cell("J2", "run-2", cast(Any, "source")),
        Cell("A5", "Category", cast(Any, "row_label")),
        Cell("B5", "Value", cast(Any, "output")),
        Cell("C5", "Literal", cast(Any, "note")),
        Cell("A6", "Alpha-2", cast(Any, "row_label")),
        Cell("B6", 25, cast(Any, "output")),
        Cell("C6", "=2+2", cast(Any, "note")),
    )
    plan2 = MappingPlan(plan.prepared, plan.quality, OwnedLayout(browser_target, run2), cells2)

    # 1. Deliberate external edit to owned cell before apply -> conflict with effect='none'
    page.cells["B6"] = "999.00"
    conflict_issue = await driver.apply(plan2, run2, obs1, cast(Any, page), before_plan=plan)
    assert isinstance(conflict_issue, AppIssue)
    assert conflict_issue.code == "conflict"
    assert conflict_issue.location == ("before_fingerprint",)
    assert conflict_issue.stage == "mutate"
    assert conflict_issue.effect == "none"
    # User edit was NOT overwritten
    assert page.cells["B6"] == "999.00"
    assert len(page.typed_edits) == 0

    # Restore B6 and test mid-update exception after first edit dispatched -> effect='unknown'
    page.cells["B6"] = "10.00"
    page.fail_on_edit_index = 1
    mid_issue = await driver.apply(plan2, run2, obs1, cast(Any, page), before_plan=plan)
    assert isinstance(mid_issue, AppIssue)
    assert mid_issue.code == "unavailable"
    assert mid_issue.stage == "mutate"
    assert mid_issue.effect == "unknown"
    assert len(page.typed_edits) == 1
