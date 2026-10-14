# Choose a task quickstart

Choose the result you need, then follow its prerequisites and verification steps.
The kernel currently runs synthetic verification; the separate GridCraft preview
opens the official browser application. A production reporting service, live
report refresh and inspected XLSX reporting artifacts remain future delivery work.

| I want to... | Guide | What I can verify |
| --- | --- | --- |
| Open the spreadsheet app | [Preview GridCraft](Quickstart_How_to_preview_GridCraft.md) | The selected browser page renders and responds to input |
| Evaluate the installed kernel | [Verify the kernel](Quickstart_How_to_verify_the_kernel.md) | Locked checks and isolated synthetic REST/MCP journeys |
| Call an enabled operation over HTTP | [Invoke with REST](Quickstart_How_to_invoke_an_operation_with_REST.md) | Discovery, receipt and the operation's declared effect |
| Call an enabled operation with an ordinary MCP client | [Invoke with MCP](Quickstart_How_to_invoke_an_operation_with_MCP.md) | Versioned tool discovery and shared receipt semantics |
| Read a retained value without replaying work | [Retrieve an operation result](Quickstart_How_to_retrieve_an_operation_result.md) | Authorized receipt and exact retained value |

REST, MCP and result guides require an operator-assembled host. For a reproducible
evaluation without assembling one, start with kernel verification. AI is optional
and none of these tasks needs an AI service.

For authors, use the [guide template](_template.md) and the
[documentation workflow](../../.kiro/steering/documentation.md). Add task guides
when their capabilities ship; plan their names and verification in the spec.
