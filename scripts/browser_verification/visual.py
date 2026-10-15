"""VisualOracle: validate typed chart/cell observations without driving the app."""

from collections import Counter
from pathlib import Path

from .contracts import CheckSet, StageFinding
from .fixture import FixtureExpectation
from .visual_profile import ChartObservation, VisualProfile, compare_crop


def compare_visual(
    observed: ChartObservation, profile: VisualProfile, expected: FixtureExpectation
) -> CheckSet:
    phase = observed.phase
    mandatory = {
        "expanded-controls",
        "home",
        "bold-A1",
        "bold-B1",
        "number",
        "chart-" + phase,
        "middle-" + phase,
        "range-" + phase,
        "title",
        "legend",
        "background",
        "dialog",
        "series",
    }
    names = Counter(frame.check for frame in observed.captures)
    valid_names = (
        mandatory <= names.keys()
        and names.keys() <= mandatory | {"home-inactive"}
        and all(count == 1 for count in names.values())
    )
    expected_cells = expected.before if phase == "before" else expected.after
    expected_text = {
        key: cell.value if isinstance(cell.value, str) else format(cell.value, "g")
        for key, cell in expected_cells.items()
    }
    valid_cells = all(
        len(cells) == len(expected_text)
        and {cell.address: cell.value for cell in cells} == expected_text
        for cells in (observed.cells_before, observed.cells)
    )
    identity = (
        observed.profile_id == profile.profile_id
        and observed.target.build_sha256 == profile.build_sha256
        and observed.target.artifact_sha256 == profile.fixture_sha256
        and observed.target.fixture_marker == expected.marker.value
        and observed.copy_receipt.target == observed.target
        and observed.copy_receipt.status == "observed"
    )
    findings = [
        StageFinding(
            stage="chart-observation-contract",
            requirements=("3.4", "3.6"),
            status="passed" if valid_names and valid_cells and identity else "failed",
        )
    ]
    for frame in observed.captures:
        correct_key = frame.crop_name == (
            "bold" if frame.check.startswith("bold-") else frame.check
        )
        passed = (
            correct_key
            and frame.crop_name in profile.crops
            and compare_crop(Path(frame.cropped), profile.crops[frame.crop_name], profile.root)
        )
        findings.append(
            StageFinding(
                stage="visual-" + frame.check,
                requirements=("3.4", "3.6", "5.2"),
                status="passed" if passed else "failed",
                evidence_refs=(frame.screenshot, frame.cropped),
            )
        )
    findings.append(
        StageFinding(
            stage="chart-category-copy",
            requirements=("3.4",),
            status="passed"
            if observed.category == "=" + expected.chart.categories
            and observed.category != observed.category_nonce
            else "failed",
            expected=(expected.chart.categories,),
            observed=(observed.category, observed.category_nonce),
            evidence_refs=observed.copy_receipt.observation_refs,
        )
    )
    return CheckSet(findings=tuple(findings))
