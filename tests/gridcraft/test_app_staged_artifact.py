"""Tests for staging pinned app saves, security inspection, and verifier reopen (Task 11)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest
from craftreport_gridcraft.app_values import (
    AppSettings,
    BrowserTarget,
    SavedCandidate,
    StagedArtifact,
)
from craftreport_gridcraft.artifacts import (
    inspect_staged_artifact,
    reopen_staged_artifact,
    stage_artifact,
)
from craftreport_gridcraft.browser import BrowserDriver
from craftreport_gridcraft.values import (
    AppIssue,
    Cell,
    MappingPlan,
    OwnedLayout,
)

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.policies.values import CheckId, CheckObservation, CheckStatus, QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins


def _make_valid_workbook_bytes(marker: str, run_id: str) -> bytes:
    import xlsxwriter  # pyright: ignore[reportMissingTypeStubs]

    output = io.BytesIO()
    with cast(Any, xlsxwriter.Workbook(output, {"in_memory": True})) as book:
        sheet = book.add_worksheet("Report")
        bold = book.add_format({"bold": True})
        numeric = book.add_format({"num_format": "0.00;-0.00"})
        sheet.write_string(0, 0, "Report", bold)
        sheet.write_string(0, 9, marker)
        sheet.write_string(1, 9, run_id)
        sheet.write_string(0, 10, marker)
        sheet.write_string(1, 10, run_id)
        sheet.write_string(0, 12, "OUTSIDE-UNCHANGED")
        for addr, val in {
            "A5": "Category",
            "B5": "Value",
            "C5": "Literal",
            "A6": "Alpha",
            "C6": "=1+1",
            "F6": "Alpha",
            "A7": "Beta",
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


class VerifierFakePage:
    def __init__(self, cells: dict[str, str], lane: dict[str, object] | None = None) -> None:
        self.cells = cells
        self.lane = lane or {"armed": False, "count": 1, "failed": False, "candidate": None}
        self.context = self
        self.mouse = self
        self.keyboard = self
        self.frames = [self]
        self._last_click: tuple[int, int] = (0, 0)
        self._current_address: str = "A1"
        self._last_clipboard: str = ""

    async def grant_permissions(self, perms: list[str], origin: str) -> None:
        pass

    async def evaluate(self, script: str, *args: Any) -> Any:
        if "window.saveLane.candidate.bytes" in script:
            candidate = self.lane.get("candidate")
            if isinstance(candidate, dict):
                return cast(dict[str, object], candidate).get("bytes", [])
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

    def locator(self, selector: str) -> VerifierFakePage:
        return self

    async def focus(self) -> None:
        self._last_clipboard = self.cells.get(self._current_address, "")


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


def test_staged_artifact_validation_and_immutability(
    browser_target: BrowserTarget, run: RunPins
) -> None:
    ev_ref = EvidenceRef(
        identity="ev-1",
        scope="artifact-stage",
        operation_id="op-1",
        operation=OperationKey("gridcraft.stage", "1"),
        resource_versions=(
            ExpectedVersion(ResourceRef("app_document", browser_target.identity.document_id), "1"),
        ),
        content_digest="a" * 64,
    )
    cand = SavedCandidate(browser_target, run, "export", "a" * 64, 1024, ev_ref)
    staged = StagedArtifact("s-1", cand, "/tmp/s-1.xlsx", "a" * 64, 1024, ev_ref)
    assert staged.staged_id == "s-1"
    assert staged.candidate == cand
    assert staged.bytes_digest == "a" * 64

    # Non-export candidate rejected
    insp_cand = SavedCandidate(browser_target, run, "inspection", "a" * 64, 1024, ev_ref)
    with pytest.raises(ValueError, match="Only exported candidates"):
        StagedArtifact("s-1", insp_cand, "/tmp/s-1.xlsx", "a" * 64, 1024, ev_ref)

    # Digest mismatch rejected
    with pytest.raises(ValueError, match="must match candidate digest"):
        StagedArtifact("s-1", cand, "/tmp/s-1.xlsx", "b" * 64, 1024, ev_ref)

    # Invalid stage fact scope rejected
    bad_fact = replace(ev_ref, scope="other-scope")
    with pytest.raises(ValueError, match="Invalid staged artifact evidence"):
        StagedArtifact("s-1", cand, "/tmp/s-1.xlsx", "a" * 64, 1024, bad_fact)


def test_stage_artifact_atomic_write_and_readback(
    browser_target: BrowserTarget, run: RunPins, tmp_path: Path
) -> None:
    data = b"PK\x03\x04valid_export_content"
    digest = hashlib.sha256(data).hexdigest()
    ev_ref = EvidenceRef(
        identity="ev-save",
        scope="app-save",
        operation_id="save-1",
        operation=OperationKey("gridcraft.save", "1"),
        resource_versions=(
            ExpectedVersion(ResourceRef("app_document", browser_target.identity.document_id), "1"),
        ),
        content_digest=digest,
    )
    candidate = SavedCandidate(browser_target, run, "export", digest, len(data), ev_ref)

    staging_dir = tmp_path / "staging"
    res = stage_artifact(candidate, data, staging_dir, staged_id="stage-custom-1")
    assert isinstance(res, StagedArtifact)
    assert res.staged_id == "stage-custom-1"
    assert res.bytes_digest == digest
    assert res.size == len(data)
    assert res.stage_fact.scope == "artifact-stage"
    assert res.stage_fact.content_digest == digest

    staged_file = Path(res.staging_path)
    assert staged_file.is_file()
    assert staged_file.read_bytes() == data


def test_stage_artifact_rejects_non_export_oversized_corrupt_collision(
    browser_target: BrowserTarget, run: RunPins, tmp_path: Path
) -> None:
    data = b"PK\x03\x04test_data"
    digest = hashlib.sha256(data).hexdigest()
    ev_ref = EvidenceRef(
        identity="ev-save",
        scope="app-save",
        operation_id="save-1",
        operation=OperationKey("gridcraft.save", "1"),
        resource_versions=(
            ExpectedVersion(ResourceRef("app_document", browser_target.identity.document_id), "1"),
        ),
        content_digest=digest,
    )
    staging_dir = tmp_path / "staging"

    # 1. Non-export purpose rejected
    insp_cand = SavedCandidate(browser_target, run, "inspection", digest, len(data), ev_ref)
    issue1 = stage_artifact(insp_cand, data, staging_dir)
    assert isinstance(issue1, AppIssue)
    assert issue1.code == "conflict"
    assert issue1.stage == "stage"

    # 2. Oversized data (>4 MiB) rejected
    cand = SavedCandidate(browser_target, run, "export", digest, len(data), ev_ref)
    huge_data = b"x" * 4194305
    issue2 = stage_artifact(cand, huge_data, staging_dir)
    assert isinstance(issue2, AppIssue)
    assert issue2.code == "limit"
    assert issue2.stage == "stage"

    # 3. Digest mismatch rejected
    issue3 = stage_artifact(cand, b"corrupt_data", staging_dir)
    assert isinstance(issue3, AppIssue)
    assert issue3.code == "conflict"
    assert issue3.stage == "stage"

    # 4. Destination collision (file already exists) rejected
    collision_file = staging_dir / "colliding.xlsx"
    collision_file.parent.mkdir(parents=True, exist_ok=True)
    collision_file.write_bytes(b"existing")
    issue4 = stage_artifact(cand, data, staging_dir, staged_id="colliding")
    assert isinstance(issue4, AppIssue)
    assert issue4.code == "conflict"
    assert issue4.location == ("destination_exists",)


def test_inspect_staged_artifact_success(
    browser_target: BrowserTarget, run: RunPins, plan: MappingPlan, tmp_path: Path
) -> None:
    data = _make_valid_workbook_bytes(browser_target.document_marker, run.run_id)
    digest = hashlib.sha256(data).hexdigest()
    ev_ref = EvidenceRef(
        identity="ev-save",
        scope="app-save",
        operation_id="save-1",
        operation=OperationKey("gridcraft.save", "1"),
        resource_versions=(
            ExpectedVersion(ResourceRef("app_document", browser_target.identity.document_id), "1"),
        ),
        content_digest=digest,
    )
    cand = SavedCandidate(browser_target, run, "export", digest, len(data), ev_ref)
    staging_dir = tmp_path / "staging"
    staged = stage_artifact(cand, data, staging_dir, "staged-1")
    assert isinstance(staged, StagedArtifact)

    findings = inspect_staged_artifact(staged, plan)
    assert isinstance(findings, tuple)
    assert len(findings) == 1
    obs = findings[0]
    assert isinstance(obs, CheckObservation)
    assert obs.check_id is CheckId.ARTIFACT_CONSISTENCY
    assert obs.status is CheckStatus.PASSED
    assert obs.reason_code == "artifact_consistency_verified"
    assert obs.scope.artifact_digest == staged.bytes_digest


def test_inspect_staged_artifact_security_bounds_and_tampering(
    browser_target: BrowserTarget, run: RunPins, plan: MappingPlan, tmp_path: Path
) -> None:
    data = _make_valid_workbook_bytes(browser_target.document_marker, run.run_id)
    digest = hashlib.sha256(data).hexdigest()
    ev_ref = EvidenceRef(
        identity="ev-save",
        scope="app-save",
        operation_id="save-1",
        operation=OperationKey("gridcraft.save", "1"),
        resource_versions=(
            ExpectedVersion(ResourceRef("app_document", browser_target.identity.document_id), "1"),
        ),
        content_digest=digest,
    )
    cand = SavedCandidate(browser_target, run, "export", digest, len(data), ev_ref)
    staging_dir = tmp_path / "staging"
    staged = stage_artifact(cand, data, staging_dir, "staged-sec")
    assert isinstance(staged, StagedArtifact)

    # 1. Missing staging path
    missing_staged = replace(staged, staging_path=str(tmp_path / "nonexistent.xlsx"))
    issue1 = inspect_staged_artifact(missing_staged, plan)
    assert isinstance(issue1, AppIssue)
    assert issue1.code == "unavailable"
    assert issue1.stage == "inspect"

    # 2. Tampered bytes on disk (digest mismatch)
    tampered_path = Path(staged.staging_path)
    original_bytes = tampered_path.read_bytes()
    tampered_path.write_bytes(original_bytes + b"\x00")
    issue2 = inspect_staged_artifact(staged, plan)
    assert isinstance(issue2, AppIssue)
    assert issue2.code == "conflict"
    assert issue2.location == ("staged_digest",)
    tampered_path.write_bytes(original_bytes)

    # 3. Disallowed macro member (.bin)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf, "w") as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("xl/vbaProject.bin", b"fake-macro-payload")
    macro_data = buf.getvalue()
    macro_cand = replace(
        cand, bytes_digest=hashlib.sha256(macro_data).hexdigest(), size=len(macro_data)
    )
    macro_staged = stage_artifact(macro_cand, macro_data, staging_dir, "macro-test")
    assert isinstance(macro_staged, StagedArtifact)
    issue3 = inspect_staged_artifact(macro_staged, plan)
    assert isinstance(issue3, AppIssue)
    assert issue3.code == "limit"

    # 4. XML DOCTYPE injection
    buf2 = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf2, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "xl/charts/chart1.xml":
                content = b"<!DOCTYPE chart SYSTEM 'evil.dtd'>" + content
            dst.writestr(item, content)
    xxe_data = buf2.getvalue()
    xxe_cand = replace(cand, bytes_digest=hashlib.sha256(xxe_data).hexdigest(), size=len(xxe_data))
    xxe_staged = stage_artifact(xxe_cand, xxe_data, staging_dir, "xxe-test")
    assert isinstance(xxe_staged, StagedArtifact)
    issue4 = inspect_staged_artifact(xxe_staged, plan)
    assert isinstance(issue4, AppIssue)
    assert issue4.code == "limit"

    # 5. External relationship injection
    buf3 = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, zipfile.ZipFile(buf3, "w") as dst:
        for item in src.infolist():
            content = src.read(item.filename)
            if item.filename == "_rels/.rels":
                content = content.replace(
                    b"/>",
                    b' TargetMode="External" Target="http://evil.com"/>',
                )
            dst.writestr(item, content)
    rel_data = buf3.getvalue()
    rel_cand = replace(cand, bytes_digest=hashlib.sha256(rel_data).hexdigest(), size=len(rel_data))
    rel_staged = stage_artifact(rel_cand, rel_data, staging_dir, "rel-test")
    assert isinstance(rel_staged, StagedArtifact)
    issue5 = inspect_staged_artifact(rel_staged, plan)
    assert isinstance(issue5, AppIssue)
    assert issue5.code == "limit"


@pytest.mark.anyio
async def test_capture_export_save_precheck_and_lane_release(
    settings: AppSettings,
    browser_target: BrowserTarget,
    run: RunPins,
    plan: MappingPlan,
) -> None:
    driver = BrowserDriver(settings)

    # 1. Precheck failure when live page run_id mismatches
    mismatch_page = VerifierFakePage(
        {"J1": browser_target.document_marker, "J2": "run-WRONG", "M1": "OUTSIDE-UNCHANGED"}
    )
    res1 = await driver.capture_export_save(
        cast(Any, mismatch_page), browser_target, run, plan, "exp1"
    )
    assert isinstance(res1, AppIssue)
    assert res1.code == "conflict"
    assert res1.location == ("run_id",)
    assert res1.stage == "capture"

    # 2. Precheck failure when live page marker mismatches
    marker_mismatch_page = VerifierFakePage(
        {"J1": "marker-WRONG", "J2": run.run_id, "M1": "OUTSIDE-UNCHANGED"}
    )
    res2 = await driver.capture_export_save(
        cast(Any, marker_mismatch_page), browser_target, run, plan, "exp2"
    )
    assert isinstance(res2, AppIssue)
    assert res2.code == "conflict"
    assert res2.location == ("document_marker",)
    assert res2.stage == "capture"

    # 3. Successful capture
    data = b"PK\x03\x04export_content"
    cand_dict = {"name": "export.xlsx", "bytes": list(data)}
    success_page = VerifierFakePage(
        {"J1": browser_target.document_marker, "J2": run.run_id, "M1": "OUTSIDE-UNCHANGED"},
        lane={"armed": True, "count": 1, "failed": False, "candidate": cand_dict},
    )
    res3 = await driver.capture_export_save(
        cast(Any, success_page), browser_target, run, plan, "exp3"
    )
    assert isinstance(res3, tuple)
    cand, captured_bytes = res3
    assert isinstance(cand, SavedCandidate)
    assert cand.purpose == "export"
    assert captured_bytes == data
    assert cand.bytes_digest == hashlib.sha256(data).hexdigest()
    assert cand.size == len(data)


@pytest.mark.anyio
async def test_export_during_publication_lane_concurrency(
    settings: AppSettings,
    browser_target: BrowserTarget,
    run: RunPins,
    plan: MappingPlan,
    tmp_path: Path,
) -> None:
    """Export-during-publication preserves one pinned run while live document moves to run-2."""
    driver = BrowserDriver(settings)

    # 1. Live page has run-1 content
    run1_data = _make_valid_workbook_bytes(browser_target.document_marker, run.run_id)
    cand_dict = {"name": "report.xlsx", "bytes": list(run1_data)}
    live_page = VerifierFakePage(
        {
            "J1": browser_target.document_marker,
            "J2": run.run_id,
            "M1": "OUTSIDE-UNCHANGED",
            "A5": "Category",
            "B5": "Value",
            "C5": "Literal",
            "A6": "Alpha",
            "B6": "10.00",
            "C6": "=1+1",
        },
        lane={"armed": True, "count": 1, "failed": False, "candidate": cand_dict},
    )

    # 2. Capture run-1 export
    cap_res = await driver.capture_export_save(
        cast(Any, live_page), browser_target, run, plan, "exp-run1"
    )
    assert isinstance(cap_res, tuple)
    candidate_1, raw_1 = cap_res
    assert candidate_1.run.run_id == run.run_id

    # 3. Stage run-1 into private staging path
    staging_dir = tmp_path / "staging"
    staged_1 = stage_artifact(candidate_1, raw_1, staging_dir, "staged-run1")
    assert isinstance(staged_1, StagedArtifact)

    # 4. Live document moves to run-2 under the same lane!
    run_2 = replace(run, run_id="run-2")
    assert run_2.run_id == "run-2"
    live_page.cells["J2"] = "run-2"
    live_page.cells["B6"] = "99.00"

    # 5. Staged artifact bytes remain immutable run-1!
    findings = inspect_staged_artifact(staged_1, plan)
    assert isinstance(findings, tuple)
    assert findings[0].check_id is CheckId.ARTIFACT_CONSISTENCY
    assert findings[0].status is CheckStatus.PASSED

    # 6. Reopen staged bytes in fresh verifier page verifying pinned run-1
    verifier_page = VerifierFakePage(
        {
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
    )
    reopen_res = await reopen_staged_artifact(staged_1, plan, cast(Any, verifier_page), driver)
    assert isinstance(reopen_res, tuple)
    assert reopen_res[0].check_id is CheckId.ARTIFACT_REOPEN
    assert reopen_res[0].status is CheckStatus.PASSED
    assert reopen_res[0].scope.artifact_digest == staged_1.bytes_digest
