"""Actual native handles cover the test-only attached Compose lifetime boundary."""

import io
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pytest
import test_browser as host
import test_feasibility as feasibility

from scripts.browser_verification import deployment
from scripts.browser_verification.journey import ResourceRegistry

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
XDR = "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}"


def packed(parts: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    return output.getvalue()


@pytest.fixture
def conflict_parts() -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(feasibility.fixture("conflict-regression"))) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
    view = root.find(f"{S}sheetViews/{S}sheetView")
    assert view is not None
    ET.SubElement(view, S + "selection", {"activeCell": "A10", "sqref": "A10"})
    parts["xl/worksheets/sheet1.xml"] = ET.tostring(root)
    return parts


@pytest.mark.parametrize(
    "attributes", [{"activeCell": "A9"}, {"sqref": "A9"}, {"activeCell": "A9", "sqref": "A9"}]
)
def test_conflict_allows_only_selection_locations(
    conflict_parts: dict[str, bytes], attributes: dict[str, str]
) -> None:
    changed = dict(conflict_parts)
    root = ET.fromstring(changed["xl/worksheets/sheet1.xml"])
    selection = root.find(f"{S}sheetViews/{S}sheetView/{S}selection")
    assert selection is not None
    selection.attrib.update(attributes)
    changed["xl/worksheets/sheet1.xml"] = ET.tostring(root)
    observed = feasibility.compare_conflict(packed(conflict_parts), packed(changed))
    assert observed == {
        "before": {"activeCell": "A10", "sqref": "A10"},
        "after": {"activeCell": "A10", "sqref": "A10"} | attributes,
    }


@pytest.mark.parametrize(
    ("part", "path", "attribute", "value"),
    [
        ("xl/worksheets/sheet1.xml", f"{S}sheetData/{S}row/{S}c[@r='B9']/{S}v", None, "999"),
        ("xl/worksheets/sheet1.xml", f"{S}sheetData/{S}row/{S}c[@r='B9']", "s", "99"),
        ("xl/worksheets/sheet1.xml", f"{S}sheetData/{S}row/{S}c[@r='B9']", "activeCell", "A9"),
        ("xl/worksheets/sheet1.xml", f"{S}sheetData/{S}row/{S}c[@r='B9']", "sqref", "A9"),
        ("xl/worksheets/sheet1.xml", f"{S}sheetViews/{S}sheetView", "zoomScale", "90"),
        ("xl/worksheets/sheet1.xml", f"{S}sheetViews/{S}sheetView/{S}selection", "pane", "topLeft"),
        ("xl/styles.xml", f"{S}fonts/{S}font/{S}sz", "val", "99"),
        ("xl/charts/chart1.xml", f".//{C}f", None, "Report!$G$6:$G$8"),
        ("xl/charts/chart1.xml", f".//{C}val//{C}v", None, "999"),
        ("xl/drawings/drawing1.xml", f".//{XDR}cNvPr", "name", "CHANGED"),
    ],
)
def test_conflict_rejects_other_content_changes(
    conflict_parts: dict[str, bytes], part: str, path: str, attribute: str | None, value: str
) -> None:
    changed = dict(conflict_parts)
    root = ET.fromstring(changed[part])
    element = root.find(path)
    assert element is not None
    if attribute is None:
        element.text = value
    else:
        element.set(attribute, value)
    changed[part] = ET.tostring(root)
    with pytest.raises(AssertionError):
        feasibility.compare_conflict(packed(conflict_parts), packed(changed))


@pytest.mark.parametrize(
    "mutation",
    ["formula", "missing", "duplicate", "wrong-path", "text", "tail", "child", "comment", "pi"],
)
def test_conflict_rejects_formula_and_structure_changes(
    conflict_parts: dict[str, bytes],
    mutation: Literal[
        "formula", "missing", "duplicate", "wrong-path", "text", "tail", "child", "comment", "pi"
    ],
) -> None:
    changed = dict(conflict_parts)
    root = ET.fromstring(changed["xl/worksheets/sheet1.xml"])
    view = root.find(f"{S}sheetViews/{S}sheetView")
    assert view is not None
    selection = view.find(S + "selection")
    assert selection is not None
    match mutation:
        case "formula":
            target = root.find(f"{S}sheetData/{S}row/{S}c[@r='B9']")
            assert target is not None
            ET.SubElement(target, S + "f").text = "1+1"
        case "missing":
            del selection.attrib["sqref"]
        case "duplicate":
            ET.SubElement(view, S + "selection", dict(selection.attrib))
        case "wrong-path":
            view.remove(selection)
            root.append(selection)
        case "text":
            selection.text = "CHANGED"
        case "tail":
            selection.tail = "CHANGED"
        case "child":
            ET.SubElement(selection, S + "unexpected")
        case "comment":
            root.append(ET.Comment("CHANGED"))
        case "pi":
            root.append(ET.ProcessingInstruction("changed", "value"))
    changed["xl/worksheets/sheet1.xml"] = ET.tostring(root)
    with pytest.raises(AssertionError):
        feasibility.compare_conflict(packed(conflict_parts), packed(changed))


@pytest.mark.parametrize("attribute", ["activeCell", "sqref"])
def test_conflict_requires_selection_attributes_on_both_sides(
    conflict_parts: dict[str, bytes], attribute: str
) -> None:
    root = ET.fromstring(conflict_parts["xl/worksheets/sheet1.xml"])
    selection = root.find(f"{S}sheetViews/{S}sheetView/{S}selection")
    assert selection is not None
    del selection.attrib[attribute]
    invalid = dict(conflict_parts, **{"xl/worksheets/sheet1.xml": ET.tostring(root)})
    for before, after in ((invalid, conflict_parts), (conflict_parts, invalid)):
        with pytest.raises(AssertionError):
            feasibility.compare_conflict(packed(before), packed(after))


@pytest.mark.parametrize("mutation", ["added", "removed", "byte-change"])
def test_conflict_rejects_archive_member_changes(
    conflict_parts: dict[str, bytes], mutation: str
) -> None:
    changed = dict(conflict_parts)
    if mutation == "added":
        changed["unexpected.xml"] = b"changed"
    elif mutation == "removed":
        del changed["xl/styles.xml"]
    else:
        changed["xl/styles.xml"] += b" "
    with pytest.raises(AssertionError):
        feasibility.compare_conflict(packed(conflict_parts), packed(changed))


def command(stop: Path) -> list[str]:
    return [
        sys.executable,
        "-u",
        "-c",
        "import pathlib,sys,time; print('attached',flush=True); "
        "p=pathlib.Path(sys.argv[1]); "
        "exec('while not p.exists(): time.sleep(0.01)')",
        str(stop),
    ]


def test_attached_handle_survives_until_owned_cleanup(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    stop = tmp_path / "owned-cleanup"
    with host.attached_compose(command(stop), state, tmp_path / "compose.log") as child:
        assert state.processes == [child] and child.poll() is None
        assert registry.tokens[0].acquisition == "acquired"
        stop.touch()
    finding = registry.findings[0]
    assert finding.native_pid == child.pid and finding.accepted
    assert finding.exit_status == 0 and not finding.requested_force
    assert "attached" in (tmp_path / "compose.log").read_text()


def test_attached_start_failure_is_retained(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    with (
        pytest.raises(OSError),
        host.attached_compose([str(tmp_path / "missing")], state, tmp_path / "compose.log"),
    ):
        pytest.fail("startup must fail")
    finding = registry.findings[0]
    assert finding.acquisition_state == "failed" and not finding.accepted
    assert not state.processes


@pytest.mark.parametrize("failure", [KeyboardInterrupt, subprocess.TimeoutExpired])
def test_attached_partial_start_preserves_primary_failure(
    tmp_path: Path, failure: type[BaseException]
) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    stop = tmp_path / "owned-cleanup"
    error = failure("startup", 0) if failure is subprocess.TimeoutExpired else failure("startup")
    with (
        pytest.raises(failure),
        host.attached_compose(command(stop), state, tmp_path / "compose.log") as child,
    ):
        stop.touch()  # Owned deployment cleanup precedes attached-client observation.
        raise error
    assert state.processes == [child]
    assert registry.findings[0].native_pid == child.pid
    assert not registry.findings[0].accepted


def test_attached_delayed_exit_is_bounded_and_never_accepted(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    started = time.monotonic()
    with host.attached_compose(
        command(tmp_path / "never-cleaned"), state, tmp_path / "compose.log", exit_timeout=0.05
    ) as child:
        assert child.poll() is None
    finding = registry.findings[0]
    assert time.monotonic() - started < 5
    assert finding.status == "timed-out" and finding.requested_force
    assert child.poll() is not None and not finding.accepted


def test_attached_early_exit_refuses_readiness(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    with host.attached_compose(
        [sys.executable, "-c", "raise SystemExit(7)"], state, tmp_path / "compose.log"
    ) as child:
        child.wait(timeout=5)
        with pytest.raises(subprocess.CalledProcessError):
            host.wait_compose(child, ["not-dispatched", "up"], time.monotonic() + 1)
    assert not registry.findings[0].accepted


def test_attached_log_retention_is_bounded(tmp_path: Path) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    with host.attached_compose(
        [sys.executable, "-c", "print('X'*70000)"], state, tmp_path / "compose.log"
    ) as child:
        child.wait(timeout=5)
    assert len((tmp_path / "compose.log").read_text()) == 65536
    assert registry.findings[0].accepted


def test_readiness_timeout_keeps_same_owned_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = ResourceRegistry(uuid4())
    state = deployment.DeploymentState(registry)
    stop = tmp_path / "cleanup"

    def no_running_service(argv: list[str], deadline: float) -> str:
        return ""

    monkeypatch.setattr(host, "execute", no_running_service)
    with host.attached_compose(command(stop), state, tmp_path / "compose.log") as child:
        try:
            with pytest.raises(host.release.ReleaseError, match="deadline exceeded"):
                host.wait_compose(child, ["compose", "up"], time.monotonic() + 0.02)
            assert state.processes == [child] and child.poll() is None
        finally:
            stop.touch()
    assert registry.findings[0].native_pid == child.pid
