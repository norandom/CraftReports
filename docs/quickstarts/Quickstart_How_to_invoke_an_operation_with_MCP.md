# Quickstart: how to invoke an operation with MCP

Use the official MCP client to discover and call a versioned operation without
an AI service. Read the structured business receipt after the protocol exchange.

## Before you start

You need an operator's running [assembled host](../kernel-host.md), enabled
capabilities, guarantee providers, authentication/access policy, endpoint and
bearer credential. The integration harness closes its temporary hosts. For an
evaluation requiring no separately assembled host,
[verify the kernel](Quickstart_How_to_verify_the_kernel.md).

Use the checkout's locked environment (`uv.exe sync --frozen --group dev`) and
operator-provided `CRAFTREPORT_URL` and `CRAFTREPORT_TOKEN` environment values.
The pinned MCP 2.3 transport uses `httpx2`, distinct from the REST client's httpx.
Keep credentials out of scripts and transcripts.

## Discover the contract

Save this as `mcp_quickstart.py` in an ignored local working directory:

```python
import asyncio
import json
import os
from pathlib import Path

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client


async def main():
    endpoint = os.environ["CRAFTREPORT_URL"].rstrip("/") + "/mcp"
    headers = {"Authorization": "Bearer " + os.environ["CRAFTREPORT_TOKEN"]}
    async with httpx2.AsyncClient(headers=headers) as http:
        async with Client(streamable_http_client(endpoint, http_client=http)) as client:
            tools = (await client.list_tools()).tools
            print("Available tools:", [tool.name for tool in tools])
            catalog = await client.call_tool("craftreport.catalog.v1", {})
            print(json.dumps(catalog.structured_content, indent=2))
            request_path = Path("invocation.json")
            if not request_path.exists():
                return
            request = json.loads(request_path.read_text(encoding="utf-8"))
            tool = request["operation"] + ".v" + request["contract_version"]
            if not any(item.name == tool for item in tools):
                raise RuntimeError("Requested contract is absent from tool discovery")
            invoked = await client.call_tool(tool, request)
            receipt = invoked.structured_content
            print("Invocation:", invoked.is_error, json.dumps(receipt, indent=2))
            if receipt is None or "operation_id" not in receipt:
                return
            inspected = await client.call_tool(
                "craftreport.inspect.v1", {"operation_id": receipt["operation_id"]}
            )
            print(
                "Inspection:", inspected.is_error,
                json.dumps(inspected.structured_content, indent=2),
            )


asyncio.run(main())
```

From the checkout root, run `uv.exe run --frozen python <path-to-mcp_quickstart.py>`.
The script reads `invocation.json` from your current directory. Run discovery
with that file absent first; check the authorized catalog and exact tool names.

## Invoke and inspect

Create `invocation.json` for an advertised operation using its payload schema,
name and string contract version. The
[REST quickstart](Quickstart_How_to_invoke_an_operation_with_REST.md#discover-and-invoke)
provides a conditional synthetic query example and command prerequisites. Run
the script again to submit the envelope and inspect its retained identity.

## Verify the result

Read `structured_content` and `is_error`. A JSON-RPC success can contain a
structured rejection or failed business outcome. A rejection has no accepted
operation ID. Accepted/pending work needs later inspection of the same ID.
Complete work must satisfy the declared evidence and actual target effect;
failed, partial and ambiguous states need their recorded recovery guidance.

For commands, independently observe the identified target/version. For queries,
[retrieve the retained value](Quickstart_How_to_retrieve_an_operation_result.md).
REST and MCP share normalized retry content and identity; never automatically
replay an ambiguous effect.

## If it does not work

| Observation | Next action |
| --- | --- |
| Connection or JSON-RPC error | Check endpoint `/mcp`, credentials and host's allowed Host/Origin configuration |
| Tool absent | Discover under the current credential; the adapter does not upgrade versions |
| Structured rejection | Read its safe diagnostic, location and recovery disposition |
| Receipt is pending or ambiguous | Inspect the existing ID; follow evidence and recovery guidance |

## Next action

[Retrieve the result](Quickstart_How_to_retrieve_an_operation_result.md) or read
the [MCP reference](../mcp-client.md) for protocol and framing details. Synthetic
evidence establishes no production durability or browser workbook behavior.
