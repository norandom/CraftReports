# Call CraftReport through ordinary MCP

Discover the exact versioned tool, submit its full invocation envelope, then inspect
the returned receipt. The official MCP client works without an AI service. Keep the
same retry key and normalized content when retrying through MCP or REST.

The example below runs in the adapter tests against real guarded execution and a
readable synthetic target. The [shared host assembly](kernel-host.md) also exercises
MCP and REST together. The [installed harness](development.md#run-the-installed-harness)
checks official MCP client discovery over loopback; full conformance remains
pending for tasks 8.2 through 8.4. Deployments supply the endpoint and bearer credential.

## Discover, write and inspect

This example expects the selected synthetic `fixture.write.v1` operation. Other
capabilities publish their own payload contracts. A successful MCP exchange can
still contain a rejection or a failed business outcome: read `structured_content`.

```python
from mcp import Client


async def write_and_inspect(client: Client) -> dict[str, object]:
    tools = (await client.list_tools()).tools
    if not any(tool.name == "fixture.write.v1" for tool in tools):
        raise RuntimeError("The fixture write contract is not available to this caller")
    result = await client.call_tool("fixture.write.v1", {
        "operation": "fixture.write",
        "contract_version": "1",
        "payload": {},
        "correlation_id": "client-correlation",
        "retry_key": "retry",
        "expected_versions": [
            {"resource": {"kind": "fixture", "identity": "target"}, "version": "1"}
        ],
    })
    receipt = result.structured_content
    if receipt is None or "operation_id" not in receipt:
        raise RuntimeError("Request rejected; inspect the structured diagnostic")
    inspected = await client.call_tool(
        "craftreport.inspect.v1", {"operation_id": receipt["operation_id"]}
    )
    if inspected.structured_content is None:
        raise RuntimeError("Receipt unavailable")
    return inspected.structured_content
```

For the pinned MCP 2.3 client, open `mcp.Client` with
`mcp.client.streamable_http.streamable_http_client(endpoint, http_client=http)`.
Supply an `httpx2.AsyncClient` with `Authorization: Bearer <credential>`; the SDK
uses httpx2, while the REST example uses httpx. The default client `mode="auto"`
negotiates the protocol. Use the configured `/mcp` endpoint. Payload fields,
forwarding headers and AI-origin markers do not establish a principal.

## Choose the next action from the result

| Result | Meaning and next action |
| --- | --- |
| JSON-RPC error | Protocol/discovery failure, unknown or inaccessible tool, or malformed MCP request. No business receipt is implied. |
| Structured rejection, `is_error=true` | No accepted identity. Read the safe operation/stage/code/location/recovery diagnostic and correlation reference. |
| Accepted or pending, `is_error=false` | Work is retained. Inspect its operation ID; acceptance does not prove the effect completed. |
| Complete, `is_error=false` | Completion passed the operation's declared result and evidence rules. |
| Failed, partial or ambiguous, `is_error=true` | Accepted work has a non-complete outcome. Inspect evidence and recovery guidance; never replay an ambiguous effect automatically. |

`structured_content` contains the canonical REST-equivalent object. The text content
contains the same object serialized as canonical JSON. HTTP status codes remain a
REST adaptation; MCP preserves the body codes and receipt states.

`craftreport.catalog.v1` accepts `{}` and returns the authorized catalog with kinds,
required capabilities, input/result schemas and operation limits.
`craftreport.inspect.v1` accepts only an `operation_id` and uses receipt visibility
checks. These tools create no business receipts. Tool discovery is deterministic
and refreshed under the current principal; a previously visible tool may become
inaccessible. An operation tool binds both name and contract version. The caller
must supply that exact identity in its envelope; the adapter never upgrades it.

## Configure the host for the advertised contracts

The shared codec enforces decoded-envelope bytes, nesting depth and serialized
business-result bytes. Payload schemas retain recursive references when embedded
under the envelope's `payload`; operation result schemas are available in the
catalog, while each operation tool returns the canonical Receipt-or-Rejection
schema. Unknown fields and invalid values cannot bypass the facade through MCP.

Host composition owns `streamable_http_app`, its session manager lifespan,
Host/Origin policy and trusted principal configuration. Configure SDK
`max_request_body_size` for the entire JSON-RPC message, including method, tool
name, metadata and encoding overhead. It must allow every advertised decoded
invocation plus that framing. A framing limit is separate from the operation's
shared decoded limit; increasing it does not relax codec checks. Runtime capacity
and wait/shutdown discovery belong to host assembly.

Current evidence is synthetic and temporary. The tests disprove parity if a retained
cross-transport retry changes operation identity or produces a second target effect.
They establish no production durability, browser behavior or saved reporting artifact.
