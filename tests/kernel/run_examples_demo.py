"""Run ordinary adopter CLIs against one owned installed synthetic deployment."""

import argparse
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fixture_packaging import ROOT, build_fixture
from installed_clients import discover
from installed_process import InstalledProcess, write_json
from pydantic import JsonValue, TypeAdapter

JsonObject = dict[str, JsonValue]
JSON_OBJECT = TypeAdapter(JsonObject)


def run_cli(owner: InstalledProcess, module: str, arguments: list[str], name: str) -> JsonObject:
    assert owner.control is not None
    environment = {
        **os.environ,
        "CRAFTREPORT_URL": owner.endpoint,
        "CRAFTREPORT_TOKEN": owner.control.credentials["alice"],
    }
    command = [sys.executable, "-m", "scripts.examples." + module, *arguments]
    child = subprocess.run(
        command, cwd=ROOT, env=environment, capture_output=True, text=True, timeout=45, check=False
    )
    write_json(
        owner.directory / (name + ".json"),
        {
            "command": command,
            "exit_code": child.returncode,
            "stdout": child.stdout,
            "stderr": child.stderr,
        },
        secrets=owner.secrets,
    )
    assert child.returncode == 0, f"Example {name} failed; see its sanitized transcript"
    return JSON_OBJECT.validate_json(child.stdout)


def verify_effect(owner: InstalledProcess, receipt: JsonObject) -> None:
    reference = receipt["result_ref"]
    assert isinstance(reference, str)
    actual = owner.observe(reference)
    assert (actual.resource, actual.value, actual.version, actual.effect_count) == (
        "target-1",
        "adopter-demo",
        "2",
        1,
    ), "Example command did not produce the single declared target effect"
    assert actual.result == {"value": "adopter-demo", "version": "2"}


def scenario(owner: InstalledProcess) -> None:
    discovery = discover(owner)
    write_json(owner.directory / "discovery.json", discovery.__dict__)
    assert discovery.operations == ("synthetic.read", "synthetic.write")
    before_discovery = owner.observe()
    assert before_discovery.effect_count == 0
    rest_discovery = run_cli(owner, "call_rest", [], "rest-discovery")
    mcp_discovery = run_cli(owner, "call_mcp", [], "mcp-discovery")
    mcp_catalog = mcp_discovery["catalog"]
    assert isinstance(mcp_catalog, dict)
    assert rest_discovery["transport_limits"] == {"max_raw_bytes": 4194304}
    assert mcp_catalog == {k: v for k, v in rest_discovery.items() if k != "transport_limits"}
    after_discovery = owner.observe()
    assert after_discovery.effect_count == 0, "Discovery unexpectedly mutated the target"
    assert after_discovery.receipts == before_discovery.receipts
    assert after_discovery.admissions == before_discovery.admissions
    write: JsonObject = {
        "operation": "synthetic.write",
        "contract_version": "1",
        "payload": {"resource": "target-1", "value": "adopter-demo"},
        "correlation_id": "adopter-demo-write",
        "retry_key": "adopter-demo-retry",
        "expected_versions": [
            {"resource": {"kind": "synthetic", "identity": "target-1"}, "version": "1"}
        ],
    }
    path = owner.directory / "write-request.json"
    write_json(path, write)
    first = run_cli(owner, "call_rest", ["--request", str(path)], "rest-write")
    verify_effect(owner, first)
    retry = run_cli(owner, "call_mcp", ["--request", str(path)], "mcp-equivalent-retry")
    assert retry == first, "Equivalent cross-transport retry changed the retained receipt"
    verify_effect(owner, retry)
    query: JsonObject = {
        "operation": "synthetic.read",
        "contract_version": "1",
        "payload": {"resource": "target-1"},
        "correlation_id": "adopter-demo-read",
    }
    path = owner.directory / "read-request.json"
    write_json(path, query)
    read = run_cli(owner, "call_mcp", ["--request", str(path)], "mcp-query")
    identity = read["operation_id"]
    assert isinstance(identity, str)
    for transport in ("rest", "mcp"):
        result = run_cli(
            owner,
            "read_result",
            ["--operation-id", identity, "--transport", transport],
            transport + "-retained-result",
        )
        assert result == {"receipt": read, "value": {"value": "adopter-demo", "version": "2"}}
        verify_effect(owner, read)
    write_json(
        owner.directory / "verified-workflow.json",
        {"write": first, "retry": retry, "query": read, "effect_count": 1, "version": "2"},
    )


def output_directory(path: Path | None) -> Path:
    artifacts = (ROOT / "artifacts").resolve()
    selected = path.resolve() if path else artifacts / ("examples-" + uuid4().hex[:10])
    if not selected.is_relative_to(artifacts) or selected == artifacts:
        raise ValueError(
            "Output must be a new owned subdirectory of the ignored artifacts directory"
        )
    selected.mkdir(parents=True, exist_ok=False)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = output_directory(args.output)
    print(f"Evidence: {directory}", flush=True)
    owner: InstalledProcess | None = None
    status = "failed"
    try:
        installed = build_fixture(directory)
        owner = InstalledProcess(installed, "adopter-demo")
        with owner:
            scenario(owner)
        assert owner.cleanup["status"] == "passed"
        status = "passed"
        print(
            "Passed: one synthetic effect, equivalent retry, retained REST/MCP results and cleanup"
        )
        return 0
    finally:
        write_json(
            directory / "summary.json",
            {
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "scope": "temporary synthetic kernel only; no browser, report or XLSX evidence",
                "cleanup": owner.cleanup if owner else None,
            },
        )


if __name__ == "__main__":
    raise SystemExit(main())
