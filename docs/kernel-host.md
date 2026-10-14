# Assemble a kernel host

Use `open_application(settings, provider_context)` to connect installed capabilities
to one guarded execution pipeline and both ordinary interfaces. The host owns
activation, MCP sessions and admitted work. Your deployment supplies guarantee
providers and authentication. There is no production provider bundle or installed
service launcher in this repository yet.

The assembly tests exercise REST and the official MCP client against the same ASGI
application, with independent synthetic target readback. Installed-wheel socket
conformance remains task 8. These tests establish neither durable recovery nor
Craft browser or exported-artifact behavior.

## Supply the deployment boundary

Import `HostSettings` and `GuaranteeProviders` from
`craftreport.composition.settings`. Supply an async context manager yielding the
providers below, with cleanup in its exit path. It must remain open while the host
runs, including execution shutdown.

| Provider | Required responsibility |
| --- | --- |
| `journal`, `guard` | Scoped retained admission/receipts and authoritative version fencing |
| `evidence`, `capabilities` | Evidence readback and current capability availability |
| `resources`, `effects` | Read-only resource snapshots and guarded effects |
| `results`, `handoffs` | Scoped retained result content and recorded execution ownership |
| `health` | Current allowlisted observations of required providers; missing probes are unavailable |

There are no default providers. Configure `PrincipalBoundary` with an authenticator
and access policy for production. Leaving either absent denies protected calls.
The same access policy feeds invocation and inspection. Generated conformance
credentials require the exact listener address `127.0.0.1`; `localhost`, `::1` and
`0.0.0.0` are rejected for that profile.

Set `deployment_epoch` and `retention_profile` to the supplied journal's actual
metadata. These values are explicit deployment assertions, not a persistence
promise inferred by the kernel. Pass selected `ConfiguredCapability` values from
`configure(...)`; factories still receive only their declared service bundles.
An absent verification expectation or stale record leaves support pending.
`VerificationExpectation` accepts the operator's exact `VerificationIdentity`
and optional recorded evidence.

`HostSettings.execution` is an immutable `ExecutionLimits` value. Its capacity,
response deadline and shutdown grace feed the execution owner and authorized
catalog from the same object. The defaults are 16, 5 seconds and 10 seconds.
Descriptor limits remain shared codec guarantees. `max_raw_bytes` bounds REST
framing and cannot undercut a selected operation's decoded byte limit. MCP receives
an additional 4096 bytes for JSON-RPC framing, and its bounded framing guard rejects
duplicate members and non-finite numbers before the SDK parser.

## Keep one listener and one ownership context

The following is a deployment integration pattern, not a standalone runnable
server: `settings` and `provider_context` must come from your deployment.

```python
from socket import AF_INET, SOCK_STREAM, socket

from craftreport.composition.app import open_application


async def run(settings, provider_context):
    with socket(AF_INET, SOCK_STREAM) as listener:
        listener.bind((settings.bind_host, 0))
        listener.listen()
        listener.setblocking(False)
        # Read listener.getsockname() here to report the actual endpoint.
        async with open_application(settings, provider_context) as host:
            server = host.server(listener)
            # The deployment's control handler calls server.request_shutdown().
            await server.serve()
```

Bind once and retain that socket. `host.server(listener)` validates its actual
address; `serve()` revalidates and uses that same socket. The caller closes the
socket. Configure allowed Host values to include the endpoint's port, or an
explicit SDK port pattern such as `127.0.0.1:*`. Origin values include the scheme;
no Origin header is required for ordinary non-browser clients. A mismatched Host
or supplied Origin is rejected on both interfaces, including readiness.

REST remains at `/v1/catalog`, `/v1/invoke` and `/v1/operations/{operation_id}`.
MCP remains at `/mcp`; the root mount follows the REST routes. No AI or notebook
service participates in startup or invocation. The top-level FastAPI lifespan
starts MCP sessions before reporting `/health/ready` as ready.

Stop the server gracefully before leaving `open_application`. Readiness clears,
execution shuts down while providers and capabilities remain alive, then sessions,
capabilities and providers close. Cancellation-resistant work causes failed
cleanup rather than a successful shutdown claim; remaining acquired contexts still
receive their exit calls. A deployment must treat any cleanup exception as failure.

## Verify the assembled path

```sh
uv run --frozen pytest tests/kernel/test_host.py tests/kernel/test_host_lifecycle.py tests/kernel/test_host_metadata.py -q
uv run --frozen python scripts/check.py --fast
```

Use `uv.exe` on the Windows development workstation. The focused cases cover
usable authorized discovery, shared REST/MCP retry identity and one observed effect,
missing guarantees, denied access, Host/Origin checks, readiness and cleanup failures.
If discovery works but these checks report no target effect or failed cleanup, the
host has not passed its assembly contract.
