"""Installed transport journey vocabulary and sanitized observations."""

import asyncio
import json
from typing import Any
from urllib.parse import quote

from installed_clients import mcp_client, rest_client
from installed_process import InstalledProcess, write_json
from mcp.types import TextContent


def envelope(**changes: object) -> dict[str, object]:
    return {
        "operation": "synthetic.write",
        "contract_version": "1",
        "payload": {"resource": "target-1", "value": "café ☃"},
        "correlation_id": "journey-correlation",
        "retry_key": "journey-retry",
        "expected_versions": [
            {"resource": {"kind": "synthetic", "identity": "target-1"}, "version": "1"}
        ],
        **changes,
    }


def invoke(
    owner: InstalledProcess, transport: str, request: dict[str, object], *, principal: str = "alice"
) -> dict[str, Any]:
    if transport == "rest":
        with rest_client(owner, principal) as client:
            response = client.post("/v1/invoke", json=request)
        result = response.json()
        expected = (
            200
            if "operation_id" in result
            else {
                "invalid_input": 422,
                "access_denied": 404,
                "unsupported_operation": 404,
                "limit_exceeded": 413,
                "retry_conflict": 409,
            }[result["diagnostic"]["code"]]
        )
        assert response.status_code == expected
        status: object = response.status_code
    else:
        result, status = asyncio.run(mcp_invoke(owner, request, principal))
    path = owner.directory / "journey-transcript.jsonl"
    record = {
        "transport": transport,
        "principal": principal,
        "request": request,
        "status": status,
        "response": result,
    }
    encoded = json.dumps(record, ensure_ascii=True)
    assert all(secret not in encoded for secret in owner.secrets)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(encoded + "\n")
    return result


async def mcp_invoke(
    owner: InstalledProcess, request: dict[str, object], principal: str
) -> tuple[dict[str, Any], bool]:
    async with mcp_client(owner, principal) as client:
        tools = await client.list_tools()
        write_json(
            owner.directory / "mcp-transcript.json",
            {
                "protocol_version": client.protocol_version,
                "principal": principal,
                "method": "tools/list",
                "response": tools.model_dump(mode="json"),
            },
            secrets=owner.secrets,
        )
        result = await client.call_tool(str(request["operation"]) + ".v1", request)
        assert result.structured_content is not None
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text) == result.structured_content
        assert result.is_error == (
            "diagnostic" in result.structured_content
            or result.structured_content.get("state") in {"failed", "partial", "ambiguous"}
        )
        return result.structured_content, result.is_error


def rejected(result: dict[str, Any], code: str, location: list[str] | None = None) -> None:
    assert "operation_id" not in result
    assert result["correlation_id"] == "journey-correlation"
    assert result["diagnostic"]["code"] == code
    if location is not None:
        assert result["diagnostic"]["location"] == location


def record_case(owner: InstalledProcess, purpose: str, requirements: list[str]) -> None:
    write_json(owner.directory / "purpose.json", {"purpose": purpose, "requirements": requirements})


def read_result(
    owner: InstalledProcess, transport: str, operation_id: str, *, principal: str = "alice"
) -> dict[str, Any]:
    if transport == "rest":
        with rest_client(owner, principal) as client:
            response = client.get("/v1/operations/" + quote(operation_id, safe="") + "/result")
        result = response.json()
        assert response.status_code == (404 if principal == "bob" else 200)
    else:
        result = asyncio.run(mcp_read_result(owner, operation_id, principal))
    record = {
        "transport": transport,
        "principal": principal,
        "operation_id": operation_id,
        "response": result,
    }
    encoded = json.dumps(record)
    assert all(secret not in encoded for secret in owner.secrets)
    with (owner.directory / "result-readback-transcript.jsonl").open(
        "a", encoding="utf-8"
    ) as stream:
        stream.write(encoded + "\n")
    return result


async def mcp_read_result(
    owner: InstalledProcess, operation_id: str, principal: str
) -> dict[str, Any]:
    async with mcp_client(owner, principal) as client:
        fetched = await client.call_tool("craftreport.result.v1", {"operation_id": operation_id})
        result = fetched.structured_content
        assert result is not None and isinstance(fetched.content[0], TextContent)
        assert json.loads(fetched.content[0].text) == result
        assert fetched.is_error == (
            "diagnostic" in result
            or result["receipt"]["state"] in {"failed", "partial", "ambiguous"}
        )
        return result
