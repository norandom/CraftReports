"""The child oracle must reject missing effects and canonical query mutation."""

import sys
from pathlib import Path

import pytest
from installed_sensitivity import EFFECT_ASSERTION, QUERY_ASSERTION, run_assertion


@pytest.mark.parametrize("check,marker", [("effect", EFFECT_ASSERTION), ("query", QUERY_ASSERTION)])
def test_sensitivity_child_really_fails(tmp_path: Path, check: str, marker: str) -> None:
    before = {
        "epoch": "epoch",
        "resource": "target-1",
        "value": "before",
        "version": "1",
        "effect_count": 0,
    }
    after = (
        before
        if check == "effect"
        else {**before, "value": "mutated", "version": "2", "effect_count": 1}
    )
    result = run_assertion(
        Path(sys.executable), tmp_path, {"check": check, "before": before, "after": after}
    )
    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert result["stderr"].rstrip().endswith("AssertionError: " + marker)


@pytest.mark.parametrize("check", ["effect", "query"])
def test_sensitivity_child_accepts_restored_observation(tmp_path: Path, check: str) -> None:
    before = {
        "epoch": "epoch",
        "resource": "target-1",
        "value": "before",
        "version": "1",
        "effect_count": 0,
    }
    after = (
        before
        if check == "query"
        else {**before, "value": "caf\u00e9 \u2603", "version": "2", "effect_count": 1}
    )
    result = run_assertion(
        Path(sys.executable), tmp_path, {"check": check, "before": before, "after": after}
    )
    assert result["exit_code"] == 0, result["stderr"]
    assert result["status"] == "passed"


def test_sensitivity_child_retains_unexpected_failure(tmp_path: Path) -> None:
    result = run_assertion(Path(sys.executable), tmp_path, {"check": "query"})
    assert result["exit_code"] == 1
    assert result["status"] == "failed"
    assert "KeyError" in result["stderr"]
    assert not result["stderr"].rstrip().endswith("AssertionError: " + QUERY_ASSERTION)
