"""Exact and over-boundary installed codec checks, including effects before bad output."""

import json
from typing import Any

import pytest
from fixture_packaging import InstalledFixture
from installed_clients import rest_catalog, rest_client
from installed_journeys import envelope, invoke, record_case, rejected
from installed_process import InstalledProcess

pytestmark = pytest.mark.integration


def serialized(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def probe(kind: str, beyond: bool) -> dict[str, object]:
    payload: dict[str, Any] = {
        "resource": "target-1",
        "value": "boundary",
        "padding": "",
        "nesting": None,
        "output_size": 0,
    }
    request = envelope(operation="synthetic.probe", payload=payload)
    if kind == "input":
        payload["padding"] = "x" * (4096 + int(beyond) - len(serialized(request)))
        assert len(serialized(request)) == 4096 + int(beyond)
    elif kind == "depth":
        node = None
        for _ in range(6 + int(beyond)):
            node = {"child": node}
        payload["nesting"] = node
    else:
        payload["output_size"] = 4096 + int(beyond)
    return request


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("kind", ["input", "depth", "output"])
@pytest.mark.parametrize("beyond", [False, True])
def test_installed_advertised_boundaries(
    installed_runtime: InstalledFixture, transport: str, kind: str, beyond: bool
) -> None:
    name = f"limit-{transport}-{kind}-{int(beyond)}"
    with InstalledProcess(installed_runtime, name, boundary_probe=True) as owner:
        rest_catalog(owner)
        record_case(
            owner,
            f"{kind} {'over' if beyond else 'exact'} advertised boundary via {transport}",
            ["2.1", "2.3", "5.3", "5.6", "6.1", "6.2", "7.2"],
        )
        with rest_client(owner) as client:
            operations = client.get("/v1/catalog").json()["operations"]
        descriptor = next(op for op in operations if op["key"]["name"] == "synthetic.probe")
        assert descriptor["limits"] == {
            "max_input_bytes": 4096,
            "max_nesting_depth": 8,
            "max_output_bytes": 4096,
        }
        before = owner.observe().model_dump(exclude={"request_id"})
        result = invoke(owner, transport, probe(kind, beyond))
        observed = owner.observe()
        if beyond and kind != "output":
            rejected(
                result,
                "limit_exceeded",
                ["max_input_bytes" if kind == "input" else "max_nesting_depth"],
            )
            assert observed.model_dump(exclude={"request_id"}) == before
        else:
            assert (observed.value, observed.version, observed.effect_count) == ("boundary", "2", 1)
            if beyond:
                assert result["state"] == "partial"
                assert result["evidence"]
                assert any(item["code"] == "effect_applied" for item in result["diagnostics"])
                other = "mcp" if transport == "rest" else "rest"
                assert invoke(owner, other, probe(kind, beyond)) == result
                assert owner.observe().effect_count == 1
                assert any(item["code"] == "result_invalid" for item in result["diagnostics"])
            else:
                assert result["state"] == "complete" and result["evidence"]
                retained = owner.observe(result["result_ref"]).result
                assert retained is not None
                if kind == "output":
                    assert len(serialized(retained)) == 4096
