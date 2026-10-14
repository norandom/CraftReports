# Quickstart: how to invoke an operation with REST

Discover an enabled operation, send its versioned envelope and inspect its
receipt. Use ordinary HTTP; an AI service and client SDK are unnecessary.

## Before you start

An operator must supply a running [assembled host](../kernel-host.md), configured
capabilities and guarantee providers, authentication/access policy, endpoint and
bearer credential. The kernel has no default production provider bundle. The
[verification harness](Quickstart_How_to_verify_the_kernel.md) starts temporary
hosts and shuts them down; it does not supply a server for these interactive steps.

In PowerShell, obtain `CRAFTREPORT_URL` and `CRAFTREPORT_TOKEN` environment values
from your operator's credential mechanism. Use the actual kernel origin, not the
GridCraft preview URL. Keep credentials out of files and transcripts.

## Discover and invoke

1. Read readiness and the authorized catalog:

   ```powershell
   $kernelUrl = $env:CRAFTREPORT_URL.TrimEnd('/')
   $kernelHeaders = @{ Authorization = "Bearer $env:CRAFTREPORT_TOKEN" }
   Invoke-RestMethod "$kernelUrl/health/ready" -Headers $kernelHeaders
   $kernelCatalog = Invoke-RestMethod "$kernelUrl/v1/catalog" -Headers $kernelHeaders
   $kernelCatalog.operations | ConvertTo-Json -Depth 100
   ```

2. Choose an advertised `key.name` and `key.contract_version`. Prepare
   `invocation.json` with its payload schema and a unique correlation reference.
   Commands also need a retry key and the required current resource versions.
   This query example applies only when the installed synthetic capability's
   `synthetic.read` contract is enabled for this caller:

   ```json
   {
     "operation": "synthetic.read",
     "contract_version": "1",
     "payload": {"resource": "target-1"},
     "correlation_id": "quickstart-read-1"
   }
   ```

   Replace the example with your catalog contract. Do not guess a command's
   resource version. The [REST reference](../rest-client.md) describes command
   envelopes, limits and retained retries.

3. Submit the file and inspect the accepted identity:

   ```powershell
   $kernelReceipt = Invoke-RestMethod "$kernelUrl/v1/invoke" -Method Post `
     -Headers $kernelHeaders -ContentType 'application/json; charset=utf-8' `
     -InFile ./invocation.json
   $kernelReceipt | ConvertTo-Json -Depth 100
   if ($kernelReceipt.operation_id) {
     $kernelOperationId = [Uri]::EscapeDataString($kernelReceipt.operation_id)
     Invoke-RestMethod "$kernelUrl/v1/operations/$kernelOperationId" -Headers $kernelHeaders
   }
   ```

## Verify the result

Accepted/pending receipts require later inspection of the same operation ID.
For terminal receipts, read `state` and evidence: HTTP 200 can contain complete,
failed, partial or ambiguous work. For a command, independently observe the
identified target and version required by its contract. For a query,
[retrieve its retained value](Quickstart_How_to_retrieve_an_operation_result.md).

Equivalent retries must preserve normalized content and the original retry key.
Never automatically replay an ambiguous effect. Readiness establishes activation
readiness and epoch, not the completion of your operation.

## If it does not work

| Observation | Next action |
| --- | --- |
| HTTP error before an accepted ID | Inspect the response's structured diagnostic and correlation reference; PowerShell raises an exception for these statuses |
| 401 or hidden/unknown operation | Check the operator-issued credential and current authorized catalog |
| 409 conflict | Check the retry content and required versions; do not silently change content under a retry key |
| 429 or 503 | Follow the diagnostic's recovery disposition and inspect capacity/provider availability |

## Next action

[Retrieve the retained result](Quickstart_How_to_retrieve_an_operation_result.md)
or use [MCP](Quickstart_How_to_invoke_an_operation_with_MCP.md) with the same
authorized contract. Temporary synthetic storage provides no restart durability.
