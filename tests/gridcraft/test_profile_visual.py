"""Explicit local historical evidence regression; requires retained real screenshots."""

from pathlib import Path

import pytest
from profile_visual import label_ink, selected_column

ROOT = Path(__file__).resolve().parents[2] / "artifacts/gridcraft/task-4/profile-browser"


@pytest.mark.parametrize(
    "run,visible",
    [
        ("c7c04f8c-9675-4985-80c7-bfd38d00a9f7", False),
        ("cf993bea-2309-4477-8996-0cc88d7f78f0", True),
    ],
)
def test_retained_real_label_thinning(run: str, visible: bool) -> None:
    path = ROOT / run / "update-1/chart.png"
    if not path.exists():
        pytest.skip("Retained local browser evidence is required; no synthetic substitute")
    assert label_ink(path)["delta_visible"] is visible


@pytest.mark.parametrize("name,column", [("table.png", "A"), ("run.png", "K")])
def test_retained_selection_column(name: str, column: str) -> None:
    path = ROOT / "183fca6c-070b-4565-85fc-5828b83e8669" / name
    if not path.exists():
        pytest.skip("Retained actual profile screenshot required")
    pixels = path.read_bytes()
    assert selected_column(pixels, column)
    assert not selected_column(pixels, "B")


def test_actual_failed_region_is_not_a_single_selected_column() -> None:
    path = ROOT / "183fca6c-070b-4565-85fc-5828b83e8669/final-state.png"
    if not path.exists():
        pytest.skip("Retained actual failed selection screenshot required")
    assert not selected_column(path.read_bytes(), "J")
    assert not selected_column(path.read_bytes(), "K")
