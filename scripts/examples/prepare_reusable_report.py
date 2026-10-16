"""Reuse the public portfolio definition through REST/MCP, without AI.

Operator host: set CRAFTREPORT_URL/TOKEN, configure public/supplied_portfolio@1.0.0,
then run ``uv.exe run --frozen python -m scripts.examples.prepare_reusable_report``.
This publishes only uniquely named synthetic feeds and leaves the operator host running.
``--demo`` installs a wheel and owns a bounded background host and temporary pack root.
Output contains retained values, pins and findings; no rendering or export is performed.
"""

import argparse
import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

from scripts.examples.common import ExampleFailure, JsonObject, emit, parse_object

PACK: JsonObject = {"namespace": "public", "name": "supplied_portfolio", "version": "1.0.0"}


def run_identity(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise ValueError("run-id requires 1-64 ASCII letters, digits, underscores or hyphens")
    return value


def snapshot(run_id: str, index: int) -> JsonObject:
    """Small producer payloads with deliberate source order, literal text and nulls."""
    rows = (
        [
            ["2026-10-15", "-12.50", "101.25", "=SUM(A1)"],
            ["2026-10-13", None, "0.00", "@literal"],
            ["2026-10-14", "0.00", None, "+literal"],
        ]
        if index != 2
        else [
            ["2026-10-16", "203.10", None, "second snapshot"],
            ["2026-10-12", "-1.20", "97.00", "-literal"],
        ]
    )
    fields = [
        {"name": "date", "label": "Date", "kind": "date", "nullable": False},
        {
            "name": "nav",
            "label": "NAV",
            "kind": "decimal",
            "nullable": True,
            "unit": "USD",
            "precision": 18,
            "scale": 2,
        },
        {
            "name": "benchmark",
            "label": "Benchmark",
            "kind": "decimal",
            "nullable": True,
            "unit": "USD",
            "precision": 18,
            "scale": 2,
        },
        {"name": "note", "label": "Note", "kind": "text", "nullable": False},
    ]
    if index == 0:
        fields.pop(2)
        rows = [[*row[:2], row[3]] for row in rows]
    return parse_object(
        json.dumps(
            {
                "schema_version": "1",
                "feed_id": f"public-demo-{run_id}-{index}",
                "producer_version": "1",
                "datasets": [
                    {
                        "name": "portfolio",
                        "label": "Synthetic portfolio",
                        "fields": fields,
                        "rows": rows,
                        "keys": ["date"],
                        "source_ref": "public:synthetic-portfolio",
                        "producer_id": "public-demo",
                        "source_version": str(index),
                    }
                ],
                "metrics": [],
                "observation_time": None,
                "generation_time": None,
            }
        )
    )


async def run(transport: str, run_id: str) -> JsonObject:
    """Use existing authenticated clients for invocation, polling and readback."""
    if transport == "rest":
        from scripts.examples.call_rest import run as caller
    else:
        from scripts.examples.call_mcp import run as caller

    async def invoke(
        name: str,
        payload: JsonObject,
        label: str,
        *,
        failed: bool = False,
        versions: list[JsonObject] | None = None,
    ) -> JsonObject:
        envelope: JsonObject = {
            "operation": name,
            "contract_version": "1",
            "payload": payload,
            "correlation_id": f"{run_id}-{label}",
            "retry_key": f"{run_id}-{label}",
        }
        if versions is not None:
            envelope["expected_versions"] = list(versions)
        receipt = await caller(envelope, None, allow_failed=failed)
        identity = receipt["operation_id"]
        assert isinstance(identity, str)
        return await caller(None, identity, allow_failed=failed)

    discovered = await invoke("reports.discover_packs", {}, "discover")
    validated = await invoke("reports.validate_definition", {"pack": PACK}, "validate")
    publications: list[JsonObject] = []
    preparations: list[JsonObject] = []
    for index in range(3):
        supplied = snapshot(run_id, index)
        published = await invoke(
            "snapshot.publish",
            supplied,
            f"publish-{index}",
            versions=[
                {
                    "resource": {"kind": "feed", "identity": supplied["feed_id"]},
                    "version": "absent",
                }
            ],
        )
        publications.append(published)
        value = published["value"]
        assert isinstance(value, dict)
        payload: JsonObject = {"pack": PACK, "snapshot": value["requested"]}
        preparations.append(
            await invoke(
                "reports.prepare",
                payload,
                f"draft-{index}",
                failed=index == 0,
            )
        )
    first = publications[1]["value"]
    assert isinstance(first, dict)
    blocked = await invoke(
        "reports.prepare",
        {
            "pack": PACK,
            "snapshot": first["requested"],
            "requested_designation": "validated",
        },
        "validated",
        failed=True,
    )
    return {
        "discovery": discovered,
        "validation": validated,
        "publications": list(publications),
        "missing_binding": preparations[0],
        "drafts": list(preparations[1:]),
        "validated": blocked,
    }


async def journey(transport: str, run_id: str) -> JsonObject:
    selected = ("rest", "mcp") if transport == "both" else (transport,)
    return {name: await run(name, run_id) for name in selected}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transport", choices=("rest", "mcp", "both"), default="both")
    parser.add_argument("--demo", action="store_true", help="Own an installed production host")
    parser.add_argument("--evidence-root", type=Path, default=Path("artifacts/report-preparation"))
    parser.add_argument(
        "--run-id",
        type=run_identity,
        default=uuid4().hex,
        help="Unique synthetic feed/retry prefix (1-64 letters, digits, _ or -)",
    )
    args = parser.parse_args()
    try:
        if args.demo:
            from tests.reporting.report_demo import launch

            emit(launch(args.transport, args.run_id, args.evidence_root.resolve()))
        else:
            emit(asyncio.run(journey(args.transport, args.run_id)))
        return 0
    except ExampleFailure as error:
        emit({"error": str(error), "response": error.response}, error=True)
    except Exception as error:
        emit({"error": "Recipe failed", "category": type(error).__name__}, error=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
