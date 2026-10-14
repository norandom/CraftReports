"""Real-client receipt polling and explicit transport disconnection."""

import asyncio
import json
import socket
import time
from contextlib import suppress
from typing import Any

from installed_clients import mcp_client, rest_client
from installed_journeys import envelope
from installed_process import InstalledProcess, write_json


def inspect(owner: InstalledProcess, transport: str, operation_id: str) -> dict[str, Any]:
    if transport == "rest":
        with rest_client(owner) as client:
            response = client.get("/v1/operations/" + operation_id)
            value = response.json()
            expected = (
                503
                if "diagnostic" in value
                else 202
                if value.get("state") in {"accepted", "pending"}
                else 200
            )
            assert response.status_code == expected
    else:
        value = asyncio.run(mcp_inspect(owner, operation_id))
    write_json(owner.directory / f"inspection-{transport}.json", value, secrets=owner.secrets)
    return value


async def mcp_inspect(owner: InstalledProcess, operation_id: str) -> dict[str, Any]:
    async with mcp_client(owner) as client:
        result = await client.call_tool("craftreport.inspect.v1", {"operation_id": operation_id})
        assert result.structured_content is not None
        return result.structured_content


def terminal(owner: InstalledProcess, transport: str, operation_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + owner.timeout
    while time.monotonic() < deadline:
        result = inspect(owner, transport, operation_id)
        if result.get("state") not in {"accepted", "pending"}:
            return result
        time.sleep(0.05)
    raise AssertionError("Retained operation did not reach a terminal state")


def disconnect_rest(owner: InstalledProcess) -> str:
    assert owner.control is not None
    body = json.dumps(envelope()).encode()
    headers = (
        f"POST /v1/invoke HTTP/1.1\r\nHost: 127.0.0.1:{owner.control.port}\r\n"
        f"Authorization: Bearer {owner.control.credentials['alice']}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n"
    ).encode()
    with socket.create_connection(("127.0.0.1", owner.control.port), timeout=5) as client:
        client.sendall(headers + body)
        proof = owner.wait_checkpoint("before_effect")
        operation_id = admission_id(proof.admissions, owner)
        client.shutdown(socket.SHUT_RDWR)
    write_json(
        owner.directory / "disconnect.json",
        {"transport": "rest", "operation_id": operation_id, "response_read": False},
    )
    return operation_id


async def disconnect_mcp(owner: InstalledProcess) -> str:
    async with mcp_client(owner) as client:
        request = asyncio.create_task(client.call_tool("synthetic.write.v1", envelope()))
        proof = await asyncio.to_thread(owner.wait_checkpoint, "before_effect")
        operation_id = admission_id(proof.admissions, owner)
        assert not request.done()
        request.cancel()
        with suppress(asyncio.CancelledError):
            await request
    write_json(
        owner.directory / "disconnect.json",
        {"transport": "mcp", "operation_id": operation_id, "response_read": False},
    )
    return operation_id


def admission_id(admissions: list[Any], owner: InstalledProcess) -> str:
    assert len(admissions) == 1
    proof = admissions[0]
    assert owner.control is not None
    assert proof["epoch"] == owner.control.epoch
    assert proof["revision"] >= 1 and proof["lease_active"]
    return str(proof["operation_id"])
