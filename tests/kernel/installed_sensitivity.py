"""Independent child assertion oracle for installed sensitivity observations."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EFFECT_ASSERTION = "actual_effect_missing"
QUERY_ASSERTION = "query_changed_canonical_state"


def assert_observation(packet: dict[str, Any]) -> None:
    before, after = packet["before"], packet["after"]
    if packet["check"] == "effect":
        assert (after["value"], after["version"], after["effect_count"]) == ("café ☃", "2", 1), (
            EFFECT_ASSERTION
        )
    elif packet["check"] == "query":
        keys = ("epoch", "resource", "value", "version", "effect_count")
        assert {key: before[key] for key in keys} == {key: after[key] for key in keys}, (
            QUERY_ASSERTION
        )
    else:
        raise ValueError("Unknown sensitivity assertion")


def run_assertion(python: Path, directory: Path, packet: dict[str, Any]) -> dict[str, Any]:
    packet_path = directory / "sensitivity-observations.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=True, indent=2), encoding="utf-8")
    child = subprocess.run(
        [str(python), "-I", "-X", "utf8", str(Path(__file__).resolve()), str(packet_path)],
        cwd=directory,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    result = {
        "exit_code": child.returncode,
        "stdout": child.stdout,
        "stderr": child.stderr,
        "status": "passed" if child.returncode == 0 else "failed",
        "observation_packet": packet_path.name,
    }
    (directory / "sensitivity-child.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    assert_observation(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
