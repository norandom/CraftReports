# Quickstart: how to retrieve an operation result

Read an operation's retained JSON value using its accepted operation ID. Retrieval
reads existing content and does not run the operation again.

## Before you start

You need the same host and authorized identity used for invocation, an accepted
`operation_id` and an operation that retained a result. The deployment supplies
providers and credentials as described in [host assembly](../kernel-host.md).
Temporary synthetic storage provides no restart durability.

## Read with REST

With operator-provided `CRAFTREPORT_URL`, `CRAFTREPORT_TOKEN` and
`CRAFTREPORT_OPERATION_ID` environment values, run in PowerShell:

```powershell
$kernelUrl = $env:CRAFTREPORT_URL.TrimEnd('/')
$kernelHeaders = @{ Authorization = "Bearer $env:CRAFTREPORT_TOKEN" }
$kernelOperationId = [Uri]::EscapeDataString($env:CRAFTREPORT_OPERATION_ID)
$kernelResult = Invoke-RestMethod "$kernelUrl/v1/operations/$kernelOperationId/result" `
  -Headers $kernelHeaders
$kernelResult | ConvertTo-Json -Depth 100
```

## Read with MCP

Inside the authenticated `mcp.Client` context from the
[MCP quickstart](Quickstart_How_to_invoke_an_operation_with_MCP.md#discover-the-contract),
use the accepted ID:

```python
fetched = await client.call_tool(
    "craftreport.result.v1", {"operation_id": receipt["operation_id"]}
)
print(fetched.is_error, fetched.structured_content)
```

You can invoke through REST and retrieve through MCP, or reverse the transports,
using the same authorized identity. The server selects the retained reference;
do not supply a storage path, result reference or principal.

## Verify the result

Expect `receipt` and `value`. Check `receipt.operation_id` against your accepted
ID, then inspect `receipt.state`, versions and evidence before consuming `value`.
The value is the exact retained JSON object; a retrievable value alone does not
prove complete work. Compare it with the operation's result contract and, where
required, independent target observations. Retrieval should leave the target
value, version and effect count unchanged.

REST uses 202 for accepted/pending and 200 for terminal receipts. MCP marks
failed, partial and ambiguous outcomes with `is_error=true`. Read the receipt
state even when transport succeeds. An accepted/pending receipt may need later
inspection; missing content returns a rejection rather than a regenerated result.

## If it does not work

| Diagnostic | Next action |
| --- | --- |
| Authentication failure | Obtain the deployment-issued credential for the intended identity |
| `access_denied` or `receipt_missing` | Check identity, operation ID, epoch and retention; hidden IDs also appear unavailable |
| `result_missing`, `result_inaccessible` or `result_unavailable` | Inspect the receipt and provider diagnostics; retrieval cannot recreate content |
| `service_unavailable` | Follow the safe diagnostic's recovery disposition |

Never replay an ambiguous command automatically to recover missing content.
Keep the existing operation ID and evidence for diagnosis.

## Next action

Use the [result readback reference](../result-readback.md) for exact diagnostics
and schemas, or [verify the kernel](Quickstart_How_to_verify_the_kernel.md) to
reproduce cross-transport readback with an independently observed synthetic target.
