# Retrieve a retained operation result

After invoking a query, use its `operation_id` to retrieve the saved value.
The response contains `receipt` and `value`. The receipt is the current authorized
journal record; `value` is the exact JSON object retained under its `result_ref`.
Calling this endpoint reads existing content and does not run the operation again.

Use the same deployment-issued credential as for invocation. REST provides
`GET /v1/operations/{operation_id}/result`; MCP provides `craftreport.result.v1`
with exactly `{"operation_id": "..."}`. The facade method is
`read_result(principal, operation_id) -> ResultReadback | Rejection`.
The server resolves the reference from the receipt. Clients cannot select a
storage path, result reference or principal.

## Query and retrieve over REST

This executable example takes an authenticated `httpx.AsyncClient` with the
service `base_url`. It requires the synthetic `fixture.read` operation used by
the adapter tests. Discover the authorized catalog and substitute your enabled
operation's name, version and payload for a real deployment.

```python
from urllib.parse import quote

import httpx


async def query_and_read_rest(client: httpx.AsyncClient) -> dict[str, object]:
    response = await client.post("/v1/invoke", json={
        "operation": "fixture.read",
        "contract_version": "1",
        "payload": {"target": "target"},
        "correlation_id": "readback-example",
    })
    response.raise_for_status()
    receipt = response.json()
    operation_id = quote(receipt["operation_id"], safe="")
    response = await client.get(f"/v1/operations/{operation_id}/result")
    response.raise_for_status()
    result = response.json()
    if result["receipt"]["state"] != "complete":
        raise RuntimeError("Inspect the retained receipt before consuming this result")
    return result
```

## Query and retrieve over MCP

Pass an authenticated official `mcp.Client`. The [MCP connection example](mcp-client.md)
describes the pinned client and HTTP transport. Neither example needs an AI service.

```python
from mcp import Client


async def query_and_read_mcp(client: Client) -> dict[str, object]:
    invoked = await client.call_tool("fixture.read.v1", {
        "operation": "fixture.read",
        "contract_version": "1",
        "payload": {"target": "target"},
        "correlation_id": "readback-example",
    })
    receipt = invoked.structured_content
    if receipt is None or "operation_id" not in receipt:
        raise RuntimeError("Invocation rejected; inspect its structured diagnostic")
    fetched = await client.call_tool("craftreport.result.v1", {
        "operation_id": receipt["operation_id"],
    })
    result = fetched.structured_content
    if result is None or "receipt" not in result:
        raise RuntimeError("Retained result unavailable; inspect its structured diagnostic")
    if fetched.is_error or result["receipt"]["state"] != "complete":
        raise RuntimeError("Inspect the retained receipt before consuming this result")
    return result
```

REST and MCP return equivalent canonical content. You can invoke through either
transport and retrieve through the other using the same authorized identity.
MCP also returns the canonical JSON in its text content. Discovery includes the
result tool's input and output schemas; invocation and receipt-inspection response
schemas remain unchanged.

## Interpret content and outcome separately

A retrievable value does not prove complete work. Its embedded receipt keeps its
recorded state, stages, versions and evidence. REST returns 202 for accepted or
pending receipts and 200 for terminal receipts. MCP sets `is_error=true` for failed,
partial or ambiguous receipts; accepted, pending and complete receipts are not
errors. Inspect `receipt.state` even when the transport succeeds.

Authorization runs before retained content lookup, and the result store checks
principal, operation and reference visibility. Failures return `correlation_id`
and a safe `diagnostic`, with no receipt or retained bytes:

| Diagnostic code | Meaning | REST status |
| --- | --- | --- |
| `access_denied` | The receipt is hidden from this caller, including hidden unknown identities. | 404 |
| `receipt_missing` | An authorized receipt lookup found no retained record. | 404 |
| `result_missing` | The receipt has no result reference or its content is absent. | 503 |
| `result_inaccessible` | The result store denied access to the retained content. | 503 |
| `result_unavailable` | Content is unavailable or the provider returned a different reference. | 503 |
| `service_unavailable` | A required provider failed. | 503 |

Missing/inaccessible result content keeps the existing conservative 503 HTTP
classification; the body code distinguishes these conditions. Authentication failures
return 401. Receipt inspection also checks retained evidence;
its safe evidence-unavailability diagnostics remain applicable to readback.
MCP returns these rejections with `is_error=true`. Follow the diagnostic's recovery
disposition; retrieval never regenerates lost content or replays an effect.

Operation-declared result limits apply when results are retained. Transport framing
has its own configured limits; the receipt wrapper does not impose a second default
result limit. Decimal quantities and large integers keep their declared string
representation. Temporary synthetic storage has no restart durability guarantee.

## Executed evidence

`tests/kernel/test_result_readback.py` and `test_result_readback_examples.py` exercise
these paths and examples through real guarded execution, REST ASGI and the official
MCP client. They check identity, authorization, exact content and unchanged synthetic
target value/version/effect count. Installed socket parity belongs to task 8.2;
this evidence does not establish production durability, browser behavior or XLSX output.
