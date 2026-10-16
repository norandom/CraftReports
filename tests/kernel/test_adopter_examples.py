"""Caller safety: inspect pending work, never replay effects, reject false success."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.examples.common import (
    ExampleFailure,
    JsonObject,
    complete,
    require_operation,
    workflow,
)


def receipt(state: str = "complete") -> JsonObject:
    return {
        "operation_id": "operation-1",
        "state": state,
        "result_ref": "retained-1",
        "result_availability": "available",
    }


@pytest.mark.anyio
async def test_pending_inspects_once_without_replaying_request() -> None:
    calls: list[str] = []

    async def execute(action: str, value: JsonObject) -> JsonObject:
        calls.append(action)
        assert value == {"operation_id": "operation-1"}
        return receipt()

    assert await complete(receipt("pending"), execute, interval=0) == receipt()
    assert calls == ["inspect"]


@pytest.mark.anyio
@pytest.mark.parametrize("state", ["pending", "failed", "partial", "ambiguous"])
async def test_noncomplete_receipts_fail_truthfully(state: str) -> None:
    calls: list[str] = []

    async def execute(action: str, value: JsonObject) -> JsonObject:
        calls.append(action)
        return receipt(state)

    with pytest.raises(ExampleFailure, match="not complete"):
        await complete(receipt(state), execute, attempts=2, interval=0)
    assert calls == (["inspect", "inspect"] if state == "pending" else [])


@pytest.mark.anyio
async def test_readback_diagnostic_does_not_reinvoke() -> None:
    calls: list[str] = []

    async def execute(action: str, value: JsonObject) -> JsonObject:
        calls.append(action)
        return receipt() if action == "inspect" else {"diagnostic": {"code": "result_missing"}}

    with pytest.raises(ExampleFailure, match="Retained result unavailable") as caught:
        await workflow(execute, None, "operation-1")
    assert caught.value.response == {"diagnostic": {"code": "result_missing"}}
    assert calls == ["inspect", "result"]


@pytest.mark.anyio
async def test_readback_must_match_requested_operation() -> None:
    async def execute(action: str, value: JsonObject) -> JsonObject:
        other = receipt()
        other["operation_id"] = "wrong-operation"
        return receipt() if action == "inspect" else {"receipt": other, "value": {}}

    with pytest.raises(ExampleFailure, match="different operation identity"):
        await workflow(execute, None, "operation-1")


@pytest.mark.anyio
async def test_last_inspection_must_match_original_identity() -> None:
    async def execute(action: str, value: JsonObject) -> JsonObject:
        other = receipt()
        other["operation_id"] = "wrong-operation"
        return other

    with pytest.raises(ExampleFailure, match="different operation identity"):
        await complete(receipt("pending"), execute, attempts=1, interval=0)


def test_discovery_does_not_upgrade_requested_contract() -> None:
    catalog: JsonObject = {
        "operations": [{"key": {"name": "synthetic.write", "contract_version": "2"}}]
    }
    with pytest.raises(ExampleFailure, match="exact operation/version"):
        require_operation(catalog, {"operation": "synthetic.write", "contract_version": "1"})


@pytest.mark.anyio
async def test_failed_readback_opt_in_preserves_failure_and_never_replays() -> None:
    calls: list[str] = []
    failed = receipt("failed")
    expected: JsonObject = {"receipt": failed, "value": {"failure": {"code": "release_blocked"}}}

    async def execute(action: str, value: JsonObject) -> JsonObject:
        calls.append(action)
        return failed if action == "inspect" else expected

    assert await workflow(execute, None, "operation-1", allow_failed=True) == expected
    assert calls == ["inspect", "result"]


@pytest.mark.anyio
@pytest.mark.parametrize("state", ["pending", "partial", "ambiguous"])
async def test_failed_opt_in_does_not_admit_other_incomplete_states(state: str) -> None:
    async def execute(action: str, value: JsonObject) -> JsonObject:
        raise AssertionError("No command or inspection expected")

    with pytest.raises(ExampleFailure, match="not complete"):
        await complete(receipt(state), execute, attempts=0, allow_failed=True)


@pytest.mark.anyio
async def test_failed_opt_in_requires_available_retained_result() -> None:
    async def execute(action: str, value: JsonObject) -> JsonObject:
        raise AssertionError("No command or inspection expected")

    with pytest.raises(ExampleFailure, match="no available retained result"):
        await complete(
            {**receipt("failed"), "result_availability": "unavailable"}, execute, allow_failed=True
        )


@pytest.mark.parametrize("readback", [False, True])
def test_mcp_error_opt_in_recognizes_only_available_failed_receipts(readback: bool) -> None:
    from scripts.examples.call_mcp import failed_result_available

    failed = receipt("failed")
    content: JsonObject = {"receipt": failed, "value": {}} if readback else failed
    assert failed_result_available(content)
    for state in ("complete", "partial", "ambiguous", "pending"):
        other = receipt(state)
        assert not failed_result_available({"receipt": other, "value": {}} if readback else other)
    assert not failed_result_available({"diagnostic": {"code": "access_denied"}})
    assert not failed_result_available({**failed, "result_availability": "unavailable"})
    assert not failed_result_available({**failed, "result_ref": None})
    assert not failed_result_available({"receipt": failed})
