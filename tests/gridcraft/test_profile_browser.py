"""Fixed candidate effect probe; no production support or run integration claim."""

import asyncio
import csv
import hashlib
import io
import json
import platform
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

import openpyxl
import pytest
import test_browser as host
import test_feasibility as route
from craftreport_gridcraft.app_values import BrowserTarget
from craftreport_gridcraft.values import PROFILE, MappingPlan, OwnedLayout
from craftreport_gridcraft.workbook import (
    _candidate_mapping,  # pyright: ignore[reportPrivateUsage] -- isolated candidate evidence
    bootstrap,
)
from playwright.async_api import Page
from profile_cases import boundary_plans, drawing_signature, metadata_expected
from profile_visual import label_ink, selected_column

from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins, TargetIdentity
from scripts.browser_verification import browser, deployment
from scripts.browser_verification.config import OwnedDeployment, RunConfig


def inspect_properties(
    data: bytes, plan: MappingPlan, line_width: str = "28575"
) -> dict[str, dict[str, object]]:
    """Compare app bytes to independent fixed literals, including absent defaults."""
    findings: dict[str, dict[str, object]] = {}

    def check(name: str, actual: object, expected: object) -> None:
        findings[name] = {"actual": actual, "expected": expected, "equal": actual == expected}

    book = openpyxl.load_workbook(io.BytesIO(data))
    try:
        sheet = book["Report"]
        bold = {"A1", "A2", "A5", "B5", "C5", "F5", "G5", *(f"J{i}" for i in range(1, 13))}
        for mapped in plan.cells:
            address = mapped.address
            cell = sheet[address]
            check(address + ".value", cell.value, mapped.value)
            check(address + ".font", (cell.font.name, cell.font.sz), ("Arial", 11))
            check(address + ".bold", bool(cell.font.bold), address in bold)
            check(address + ".italic", bool(cell.font.italic), False)
            check(
                address + ".color",
                str(cell.font.color.rgb) if cell.font.color else None,
                "FF000000",
            )
            check(
                address + ".fill",
                cell.fill.fgColor.rgb,
                "FFDCE6F1" if address in bold - {"A2"} else "00000000",
            )
            check(address + ".alignment", cell.alignment.horizontal, "left")
            check(address + ".wrap", bool(cell.alignment.wrap_text), True)
        check("literal.type", sheet["C6"].data_type, "s")
        check("url.type", sheet["C7"].data_type, "s")
        check("url.hyperlink", sheet["C7"].hyperlink, None)
        check("format.numeric", sheet["B7"].number_format, "0.00;-0.00")
        check("grid.visible", sheet.sheet_view.showGridLines, False)
        check("grid.header_height", getattr(sheet.row_dimensions[5], "height"), 24)
        check("grid.column_width", sheet.column_dimensions["A"].width, 18.7109375)
        check("summary.merge", "A3:H3" in sheet.merged_cells, True)
        check("summary.height", getattr(sheet.row_dimensions[3], "height"), 160)
        check("summary.complete", sheet["A3"].value, plan.quality.validation_summary)
        check("designation", sheet["A1"].value, plan.quality.draft_designation)
        for address, value in metadata_expected(plan).items():
            check(address + ".input_pin", sheet[address].value, value)
        check("outside.cell", sheet["M1"].value, "OUTSIDE-UNCHANGED")
    finally:
        book.close()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        chart = ET.fromstring(archive.read("xl/charts/chart1.xml"))
        check("outside.textbox", b"SAFE" in archive.read("xl/drawings/drawing1.xml"), True)
    ns = {
        "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    }
    check(
        "chart.references",
        [x.text for x in chart.findall(".//c:f", ns)],
        ["Report!$G$5", "Report!$F$6:$F$9", "Report!$G$6:$G$9"],
    )
    line = chart.find(".//c:ser/c:spPr/a:ln", ns)
    check("chart.line_width", line.get("w") if line is not None else None, line_width)
    color = chart.find(".//c:ser/c:spPr/a:ln/a:solidFill/a:srgbClr", ns)
    check("chart.color", color.get("val") if color is not None else None, "4472C4")
    check("chart.legend", chart.find(".//c:legend", ns) is not None, False)
    check("chart.grid", chart.find(".//c:majorGridlines", ns) is not None, False)
    gap = chart.find(".//c:dispBlanksAs", ns)
    findings["chart.gap_encoding"] = {
        "actual": gap.get("val") if gap is not None else None,
        "interpretation": "Absent dispBlanksAs uses the OOXML gap default",
        "equal": True,
    }
    check("chart.gap", gap.get("val") if gap is not None else "gap", "gap")
    return findings


async def candidate_cell(
    page: Page, address: str, diagnostic: Path | None = None
) -> dict[str, str]:
    """Read actual selection and cell with fresh clipboard nonces at candidate geometry."""
    await route.click(page, 60, 179)
    await route.key(page, "Control+a")
    await page.keyboard.insert_text(address)
    await route.frame(page)
    await route.key(page, "Enter")
    async with asyncio.timeout(5):
        while True:
            pixels = await page.screenshot(path=str(diagnostic) if diagnostic else None)
            if selected_column(pixels, address[0], merged=address == "A3"):
                break
            await route.frame(page)
    if diagnostic:
        async with asyncio.timeout(5):
            hit_test: dict[str, object] = await page.frames[1].evaluate("""() => {
              const describe = e => {
                if (!e) return null;
                const r=e.getBoundingClientRect(), s=getComputedStyle(e);
                return {tag:e.tagName,id:e.id,rect:{x:r.x,y:r.y,width:r.width,height:r.height},
                  padding:{left:s.paddingLeft,right:s.paddingRight,top:s.paddingTop,bottom:s.paddingBottom},
                  pointerEvents:s.pointerEvents,visibility:s.visibility,display:s.display,opacity:s.opacity};
              };
              return {url:location.href,point40:describe(document.elementFromPoint(40,179)),
                point60:describe(document.elementFromPoint(60,179)),
                activeElement:describe(document.activeElement),
                inputs:Array.from(document.querySelectorAll('input,textarea')).slice(0,10).map(describe)};
            }""")
        host.write_json(diagnostic.with_suffix(".json"), hit_test)
    await route.click(page, 60, 179)
    await route.key(page, "Control+a")
    async with asyncio.timeout(5):
        reference, rn = await route.copy_text(page)
    assert reference in (address, "A3:H3" if address == "A3" else address)
    await route.key(page, "Escape")
    await page.frames[1].locator("#gridcraft_canvas").focus()
    async with asyncio.timeout(5):
        value, vn = await route.copy_text(page)
    return {"reference": reference, "value": value, "reference_nonce": rn, "value_nonce": vn}


def clipboard_encoding(value: str, *, merged: bool = False) -> str:
    if not value:
        return ""
    output = io.StringIO(newline="")
    csv.writer(output, delimiter="\t", lineterminator="\n").writerow(
        [value, *([""] * 7 if merged else [])]
    )
    return output.getvalue().removesuffix("\n")


async def visible_candidate(page: Page, plan: MappingPlan, directory: Path) -> None:
    cells = {cell.address: cell.value for cell in plan.cells}
    expected = {
        "K1": plan.layout.document_marker,
        "K2": plan.layout.run.run_id,
        "A1": "DRAFT",
        "A2": "Supplied series",
        "A3": plan.quality.validation_summary,
        "B7": f"{cells['B7']}.00",
        "G7": "",
        "C6": str(cells["C6"]),
        "C7": str(cells["C7"]),
        "M1": "OUTSIDE-UNCHANGED",
    }
    observed: list[dict[str, str]] = []
    for address, value in expected.items():
        item = await candidate_cell(page, address)
        observed.append(item)
        host.write_json(directory / "cells.json", observed)
        assert item["value"] == clipboard_encoding(value, merged=address == "A3"), (
            address,
            item,
            value,
        )
    host.write_json(directory / "run-pins.json", asdict(plan.layout.run))
    await candidate_cell(page, "K2")
    await page.screenshot(path=str(directory / "run.png"))
    await candidate_cell(page, "A1")
    await page.screenshot(path=str(directory / "table.png"))
    host.write_json(
        directory / "summary.json",
        {
            "expected": plan.quality.validation_summary,
            "serialized_utf8_bytes": len(
                json.dumps(plan.quality.validation_summary, ensure_ascii=False).encode()
            ),
            "screenshot": "table.png",
            "fit_review": "pending manual full-text comparison; clipboard equality is not fit",
        },
    )
    await page.mouse.move(500, 800)
    await page.mouse.wheel(0, 700)
    await route.frame(page)
    await page.screenshot(path=str(directory / "chart.png"))
    assert plan.prepared.charts[0].categories[-2:] == ("Gamma", "Delta")
    ink = label_ink(directory / "chart.png")
    host.write_json(directory / "label-ink.json", ink)
    assert ink["delta_visible"], ink
    await page.mouse.wheel(0, -700)
    await route.frame(page)


async def update_candidate(
    page: Page, before: MappingPlan, after: MappingPlan, directory: Path
) -> None:
    old = {cell.address: cell.value for cell in before.cells}
    changed = [cell for cell in after.cells if cell.value != old[cell.address]]
    assert (await candidate_cell(page, "K1"))["value"] == before.layout.document_marker
    for cell in changed:
        previous = old[cell.address]
        expected = f"{previous}.00" if type(previous) is int else str(previous)
        diagnostic = directory / "K11-before.png" if cell.address == "K11" else None
        assert (await candidate_cell(page, cell.address, diagnostic))[
            "value"
        ] == clipboard_encoding(expected, merged=cell.address == "A3"), cell.address
    for cell in changed:
        diagnostic = directory / "K11-edit.png" if cell.address == "K11" else None
        await candidate_cell(page, cell.address, diagnostic)
        await route.click(page, 300, 179)
        await route.key(page, "Control+a")
        assert cell.value is not None
        text = "'" + cell.value if type(cell.value) is str else str(cell.value)
        await page.keyboard.insert_text(text)
        await route.frame(page)
        await route.key(page, "Enter")


@pytest.mark.integration
@pytest.mark.skipif(platform.system() != "Windows", reason="approved Windows headless profile")
def test_candidate_real_save_and_reopen(
    monkeypatch: pytest.MonkeyPatch,
    prepared: PreparedReport,
    quality: QualityEvaluation,
    run: RunPins,
    quality_factory: Callable[[PreparedReport], QualityEvaluation],
) -> None:
    config = RunConfig(
        deployment=OwnedDeployment(mode="owned-wsl"),
        headed=False,
        output_root=host.ROOT / "artifacts/gridcraft/task-4/profile-browser",
        trusted_release_sha256=host.ARCHIVE,
        trust_source="approved v0.7.0 Design",
    )
    config.run_directory.mkdir(parents=True)
    (config.run_directory / "probe-source.py.txt").write_bytes(Path(__file__).read_bytes())
    for name in ("profile_cases.py", "profile_visual.py", "conftest.py"):
        (config.run_directory / (name + ".txt")).write_bytes(
            Path(__file__).with_name(name).read_bytes()
        )
    original = host.observe_bridge
    marker = "task4-" + uuid4().hex

    async def probe(
        config: RunConfig, lease: deployment.DeploymentLease, state: browser.BrowserState
    ) -> dict[str, object]:
        report = await original(config, lease, state)
        assert state.page and state.diagnostics and lease.project
        identity = TargetIdentity("gridcraft", "browser", str(state.context_id), marker)
        target = BrowserTarget(
            identity,
            lease.project,
            str(state.context_id),
            str(state.page_id),
            1,
            lease.origin,
            lease.build_sha256,
            next(a.sha256 for a in lease.assets if a.path.endswith(".js")),
            next(a.sha256 for a in lease.assets if a.path.endswith(".wasm")),
            PROFILE.pin,
            marker,
        )
        layout = OwnedLayout(target, replace(run, target=identity))
        plan = _candidate_mapping(prepared, quality, layout)
        assert isinstance(plan, MappingPlan)
        data = bootstrap(plan, marker)
        assert isinstance(data, bytes)
        (config.run_directory / "candidate.xlsx").write_bytes(data)
        report.update(
            {
                "scope": "candidate only; runtime5.1 and full property evidence pending",
                "calibration_artifact_only": False,
                "category_diagnostic_only": False,
                "profile_digest": PROFILE.pin.content_digest,
                "marker": marker,
                "prepared_digest": prepared.content_digest,
                "test_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
        )
        host.write_json(config.run_directory / "identity.json", report)
        state.diagnostics.stage = "open"
        await route.bootstrap(state.page, data, config.run_directory)
        await visible_candidate(state.page, plan, config.run_directory)
        saved = await route.save(state.page, config.run_directory, "saved")
        results = {
            "bootstrap": inspect_properties(data, plan),
            "saved": inspect_properties(saved, plan),
        }
        outside = drawing_signature(saved)
        plans = boundary_plans(plan, quality_factory)
        for index, next_plan in enumerate(plans, 1):
            state.diagnostics.stage = "edit"
            stage = config.run_directory / f"update-{index}"
            stage.mkdir()
            await update_candidate(state.page, plan, next_plan, stage)
            plan = next_plan
            saved = await route.save(state.page, stage, "saved")
            results[f"update-{index}"] = inspect_properties(saved, plan)
            assert drawing_signature(saved) == outside
            host.write_json(config.run_directory / "properties.json", results)
            await visible_candidate(state.page, plan, stage)
        host.write_json(config.run_directory / "properties.json", results)
        child_config = config.model_copy(update={"output_root": config.run_directory / "reopen"})
        child_config.run_directory.mkdir(parents=True)
        child = browser.BrowserState(state.registry)
        try:
            fresh = await original(child_config, lease, child)
            assert child.page and child.diagnostics
            child.diagnostics.stage = "open"
            await route.bootstrap(child.page, saved, child_config.run_directory)
            await visible_candidate(child.page, plan, child_config.run_directory)
            again = await route.save(child.page, child_config.run_directory, "resaved")
            results["reopened"] = inspect_properties(again, plan)
            assert drawing_signature(again) == outside
            fresh["opened_sha256"] = hashlib.sha256(saved).hexdigest()
            host.write_json(child_config.run_directory / "identity.json", fresh)
            assert all(not d.fatal for d in child.diagnostics.events)
        finally:
            await browser.close(child_config, child)
            if child.diagnostics:
                child.diagnostics.write(child_config.run_directory / "diagnostics.json")
            host.write_json(
                child_config.run_directory / "video.json",
                child.video.model_dump(mode="json") if child.video else None,
            )
            host.write_json(config.run_directory / "properties.json", results)
        failures = {
            stage: {name: value for name, value in checks.items() if not value["equal"]}
            for stage, checks in results.items()
        }
        host.write_json(config.run_directory / "failures.json", failures)
        assert not any(failures.values()), failures
        return report

    monkeypatch.setattr(host, "PARENT", host.PARENT + route.RECEIVER)
    monkeypatch.setattr(host, "observe_bridge", probe)
    asyncio.run(host.readiness(config, monkeypatch, observer_timeout=360))
