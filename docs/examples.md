# Run an example, then adapt the caller

These examples demonstrate the current operation kernel and give integrators
ordinary Python code to reuse. They call the public REST/MCP interfaces without
AI. They do not yet produce a report, update a browser chart or export XLSX.

For the reporting use case, start with [why use CraftReport](why-craftreport.md).
The intended value is a reusable reporting workflow; these examples establish
the shared automation behavior on which that workflow will depend.

## Choose your task

| Task | Executable | What it demonstrates |
| --- | --- | --- |
| Try the kernel without assembling a host | [Owned synthetic demo](../tests/kernel/run_examples_demo.py) | Installed host, real caller commands, cross-transport retry, retained results and independent target verification |
| Discover and invoke over HTTP | [REST caller](../scripts/examples/call_rest.py) | Authorized catalog, supplied invocation envelope and truthful outcome handling |
| Discover and invoke with ordinary MCP | [MCP caller](../scripts/examples/call_mcp.py) | Versioned tools, the same envelope and receipt semantics |
| Retrieve an accepted operation's result | [Result reader](../scripts/examples/read_result.py) | Authorized readback through REST or MCP without executing work again |

The caller recipes live in the typed, linted `scripts/examples/` tree. They use
public interfaces and contain no test-provider imports. The demo launcher owns
the test-only fixture setup and independent observations; it is not a production
server bundle or a client SDK.

## Run the owned demo

From the checkout root, use the locked CPython 3.12.10 / uv 0.13.0 environment:

```powershell
uv.exe sync --frozen --group dev
uv.exe run --frozen python tests/kernel/run_examples_demo.py
```

Use `uv` on Linux/WSL and its own environment. Fixture wheel builds and isolated
installation use the warmed dependency cache offline; complete the locked sync
first. No database, GridCraft process, private pack or AI service is required.

The launcher builds isolated installed wheels, starts its owned loopback host
and runs the Python caller entrypoints against a synthetic target:

1. Write a value through REST and observe the resulting target version.
2. Retry the same command through MCP and confirm the original operation identity
   and one effect, rather than another write.
3. Query through MCP and retrieve its retained result through REST and MCP.
4. Compare the returned content with an independent fixture observation.
5. Close the owned host and retain the run's output and cleanup evidence.

Require a zero exit from the complete demo and inspect the printed run directory.
The evidence concerns temporary synthetic state. It does not establish production
durability, financial accuracy, browser behavior or saved reporting artifacts.

## Use the callers with your host

An operator must supply the [assembled host](kernel-host.md), selected capabilities,
guarantee providers, authentication/access policy and endpoint. Supply
`CRAFTREPORT_URL` and `CRAFTREPORT_TOKEN` through the operator's environment or
credential mechanism. Use the kernel origin, not the GridCraft nginx preview.

Run discovery first, then prepare `invocation.json` in an ignored local directory
from the authorized operation's exact name, string version and payload schema.
Commands also require a retry key and the contract's current resource versions.
The [REST quickstart](quickstarts/Quickstart_How_to_invoke_an_operation_with_REST.md)
explains those inputs. The synthetic fixture is not enabled in every host.

```powershell
uv.exe run --frozen python -m scripts.examples.call_rest
uv.exe run --frozen python -m scripts.examples.call_mcp
uv.exe run --frozen python -m scripts.examples.call_rest --request artifacts/invocation.json
uv.exe run --frozen python -m scripts.examples.call_mcp --request artifacts/invocation.json
```

Submitting the same command file through both transports is a retry only when
its normalized content and retry key match. Do not submit changed content under
the same retry key. A query without a retry key is a separate invocation each time.

Replace `<accepted-operation-id>` below with the identity from your receipt:

```powershell
uv.exe run --frozen python -m scripts.examples.read_result --operation-id <accepted-operation-id> --transport rest
uv.exe run --frozen python -m scripts.examples.read_result --operation-id <accepted-operation-id> --transport mcp
```

Read the receipt state and structured diagnostics. Accepted/pending is not proof
of completion; failed, partial or ambiguous work requires the declared recovery
guidance. Missing retained content is not a reason to rerun a command. Inspect
the actual target or artifact when its contract requires independent proof.

## Adapt the code

Reuse the caller routines and their small shared wire/inspection helper with
your operation's input contract. Keep the authentication and endpoint supplied
by your deployment. Preserve bounded waiting, outcome inspection and stable
retry identity when integrating the code into an existing Python application.
The examples are verified with the repository's locked dependencies.

Use the [task quickstarts](quickstarts/index.md) for step-by-step instructions
and [result readback reference](result-readback.md) for exact diagnostics.
Caller contexts close their connections; they do not own or stop your server.
The synthetic demo owns and closes only the processes it starts.

## Future report examples

The [Kiro documentation rule](../.kiro/steering/documentation.md) now requires a
quickstart and executable adopter/demo example for each delivered user-facing
feature. Report examples will arrive with their implemented capabilities:
supplied data, templates, visible live refresh and snapshot-consistent XLSX.
A live example must show actual updates and controls in the selected workbook;
an export example must inspect and reopen the real output. See the
[roadmap](roadmap.md) for the remaining delivery gates.
