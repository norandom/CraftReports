"""Sensitivity of reviewed pixels and profile identities."""

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from scripts.browser_verification import browser
from scripts.browser_verification import visual_profile as visual

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests/fixtures/browser_verification/visual/manifest.json"


def test_reviewed_chart_matches_and_wrong_middle_fails(tmp_path: Path) -> None:
    profile = visual.VisualProfile.read(MANIFEST)
    source = profile.root / "windows-headless/chart-before.png"
    assert visual.compare_crop(source, profile.crops["chart-before"], profile.root)
    assert not visual.compare_crop(source, profile.crops["chart-after"], profile.root)
    wrong = tmp_path / "wrong.png"
    with Image.open(source) as image:
        image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(wrong)
    assert not visual.compare_crop(wrong, profile.crops["chart-before"], profile.root)


def test_unknown_runtime_and_tampered_baseline_reject(tmp_path: Path) -> None:
    profile = visual.VisualProfile.read(MANIFEST)
    runtime = browser.RuntimeProfile.model_validate(
        {
            **json.loads(MANIFEST.read_text())["runtime"],
            "executable": "/operator/chromium-1248",
            "visible": False,
            "window_handle": None,
        }
    )
    profile.require_runtime(profile.build_sha256, runtime)
    for updates in (
        {"os": "Linux"},
        {"device_scale": 2},
        {"graphics_renderer": "other"},
        {"headed": True},
    ):
        with pytest.raises(ValueError, match="visual-profile-mismatch"):
            profile.require_runtime(profile.build_sha256, runtime.model_copy(update=updates))
    with pytest.raises(ValueError, match="visual-profile-mismatch"):
        profile.require_runtime("0" * 64, runtime)
    crop = profile.crops["chart-before"].model_copy(update={"sha256": "0" * 64})
    with pytest.raises(ValueError, match="baseline-hash-mismatch"):
        visual.compare_crop(profile.root / crop.file, crop, profile.root)


def test_wrong_range_and_inactive_bold_reject(tmp_path: Path) -> None:
    profile = visual.VisualProfile.read(MANIFEST)
    for name in ("range-before", "bold", "title", "legend", "series", "number"):
        crop = profile.crops[name]
        source = profile.root / crop.file
        with Image.open(source) as image:
            wrong = Image.new("RGB", image.size, "white")
            output = tmp_path / (name + ".png")
            wrong.save(output)
        assert not visual.compare_crop(output, crop, profile.root)


def test_additional_chart_outside_expected_bounds_rejects(tmp_path: Path) -> None:
    profile = visual.VisualProfile.read(MANIFEST)
    crop = profile.crops["background"]
    with Image.open(profile.root / crop.file) as image:
        image.paste("blue", (800, 300, 900, 400))
        output = tmp_path / "additional-chart.png"
        image.save(output)
    assert not visual.compare_crop(output, crop, profile.root)


def test_values_outline_ending_at_b3_instead_of_b4_rejects(tmp_path: Path) -> None:
    profile = visual.VisualProfile.read(MANIFEST)
    crop = profile.crops["range-before"]
    with Image.open(profile.root / crop.file) as image:
        draw = ImageDraw.Draw(image)
        # Relative y49 is the reviewed B4 bottom; y33 is the B3 bottom.
        draw.line((2, 49, 52, 49), fill="white")
        draw.line((2, 33, 52, 33), fill=(50, 110, 255))
        output = tmp_path / "wrong-b2-b3-outline.png"
        image.save(output)
    assert not visual.compare_crop(output, crop, profile.root)


def test_oracle_requires_category_cells_and_all_observations() -> None:
    from uuid import uuid4

    from scripts.browser_verification import visual as oracle
    from scripts.browser_verification.contracts import ActionReceipt, CellCheck
    from scripts.browser_verification.fixture import FixtureExpectation
    from tests.browser_verification.test_contracts import target

    profile = visual.VisualProfile.read(MANIFEST)
    expected = FixtureExpectation.read(MANIFEST.parent.parent / "expected.json")
    selected = target().model_copy(
        update={
            "build_sha256": profile.build_sha256,
            "artifact_sha256": profile.fixture_sha256,
            "fixture_marker": expected.marker.value,
        }
    )
    names = [
        "expanded-controls",
        "home",
        "bold-A1",
        "bold-B1",
        "number",
        "chart-before",
        "middle-before",
        "range-before",
        "title",
        "legend",
        "background",
        "dialog",
        "series",
    ]
    frames: list[visual.VisualCapture] = []
    for name in names:
        key = "bold" if name.startswith("bold-") else name
        path = str(profile.root / profile.crops[key].file)
        frames.append(
            visual.VisualCapture(check=name, crop_name=key, screenshot=path, cropped=path)
        )
    receipt = ActionReceipt(
        target=selected,
        action="copy",
        dispatch_id=uuid4(),
        start=1.0,
        deadline=2.0,
        status="observed",
        observation_refs=("category.png",),
    )
    cells = tuple(
        CellCheck(
            address=key,
            value=cell.value if isinstance(cell.value, str) else format(cell.value, "g"),
        )
        for key, cell in expected.before.items()
    )
    observed = visual.ChartObservation(
        target=selected,
        phase="before",
        profile_id=profile.profile_id,
        category="=" + expected.chart.categories,
        category_nonce="fresh-nonce",
        captures=tuple(frames),
        cells_before=cells,
        cells=cells,
        copy_receipt=receipt,
    )
    assert oracle.compare_visual(observed, profile, expected).passed
    for updates in (
        {"category": "=Report!$A$2:$A$5"},
        {"cells": observed.cells[:-1]},
        {"cells_before": observed.cells_before[:-1]},
        {"captures": observed.captures[:-1]},
        {"category": observed.category_nonce},
    ):
        assert not oracle.compare_visual(
            observed.model_copy(update=updates), profile, expected
        ).passed
