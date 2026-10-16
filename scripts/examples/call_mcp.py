"""Call the official MCP client with an explicit operation envelope; no AI."""

import asyncio
import json

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from scripts.examples.common import (
    ExampleFailure,
    JsonObject,
    Readback,
    Receipt,
    cli,
    configuration,
    parse_object,
    require_operation,
    workflow,
)


def tool_name(action: str, value: JsonObject) -> str:
    if action != "invoke":
        return f"craftreport.{action}.v1"
    operation, version = value.get("operation"), value.get("contract_version")
    if not isinstance(operation, str) or not isinstance(version, str):
        raise ExampleFailure("Envelope requires string operation and contract_version")
    return f"{operation}.v{version}"


def failed_result_available(response: JsonObject) -> bool:
    """MCP marks genuine failed receipts as errors; preserve their inspectable result."""
    try:
        receipt = (
            Readback.model_validate(response).receipt
            if "receipt" in response
            else Receipt.model_validate(response)
        )
    except ValidationError:
        return False
    return (
        "diagnostic" not in response
        and receipt.state == "failed"
        and receipt.result_availability == "available"
        and bool(receipt.result_ref)
    )


async def run(
    request: JsonObject | None, identity: str | None, *, allow_failed: bool = False
) -> JsonObject:
    url, token = configuration()
    async with (
        asyncio.timeout(30),
        httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=10, trust_env=False
        ) as http,
        Client(streamable_http_client(url + "/mcp", http_client=http)) as client,
    ):

        async def execute(action: str, value: JsonObject) -> JsonObject:
            result = await client.call_tool(tool_name(action, value), value)
            if result.structured_content is None:
                raise ExampleFailure("MCP returned no structured JSON result")
            response = parse_object(json.dumps(result.structured_content))
            if result.is_error and not (allow_failed and failed_result_available(response)):
                raise ExampleFailure(
                    "MCP tool returned an error; inspect retained diagnostics", response
                )
            return response

        if identity is None:
            tools = await client.list_tools()
            catalog = await execute("catalog", {})
            if request is None:
                return {"catalog": catalog, "tools": parse_object(tools.model_dump_json())}
            require_operation(catalog, request)
            if tool_name("invoke", request) not in {tool.name for tool in tools.tools}:
                raise ExampleFailure("Requested exact tool is not in authorized MCP discovery")
        return await workflow(execute, request, identity, allow_failed=allow_failed)


if __name__ == "__main__":
    raise SystemExit(cli("mcp"))
