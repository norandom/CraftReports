# REST client contract

The REST router exposes `GET /health/ready`, `GET /v1/catalog`,
`POST /v1/invoke` and `GET /v1/operations/{operation_id}`. The
[host assembly](kernel-host.md) supplies lifecycle and both interfaces.
The [installed harness](development.md#run-the-installed-harness) checks REST
catalog discovery over loopback; full conformance remains pending for tasks
8.2 through 8.4.
Readiness reports activation readiness and deployment epoch only.

Send a deployment-issued bearer credential. Identity, scope and authorization
come from the trusted boundary; body fields and AI-origin markers grant no access.
Discovery and operation responses use `Cache-Control: private, no-store`.
Generic OpenAPI contains only the envelope and outcome contracts; discover
private operation schemas through the authorized catalog.

Catalog operation descriptors advertise decoded whole-envelope byte, nesting
and output limits. `transport_limits.max_raw_bytes` separately bounds the actual
UTF-8 request bytes, including whitespace. Configure that framing cap high enough
for the intended operation limits. Shared codecs and guards enforce descriptor
limits; REST does not replace them. Duplicate keys, non-finite numbers, unsafe
integers, invalid UTF-8 and unknown envelope fields are rejected before behavior.
Versions and decimal quantities use their operation-declared string representation.
The assembled catalog also advertises `execution_limits` with the configured
`capacity`, `response_seconds` and `shutdown_seconds` used by its execution owner.

The following executable example uses an `httpx.AsyncClient` configured with
`base_url` and an `Authorization: Bearer ...` header. Its synthetic `fixture.write`
operation must be enabled and visible in the catalog. Replace this operation,
resource and version with values from your deployment's authorized contract.
The kernel does not ship a client SDK or require AI.

```python
async def write_and_inspect(client):
    catalog_response = await client.get("/v1/catalog")
    catalog_response.raise_for_status()
    response = await client.post("/v1/invoke", json={
        "operation": "fixture.write",
        "contract_version": "1",
        "payload": {"value": "changed"},
        "correlation_id": "example-request",
        "retry_key": "example-write-1",
        "expected_versions": [{
            "resource": {"kind": "fixture", "identity": "target"},
            "version": "1",
        }],
    })
    response.raise_for_status()
    receipt = response.json()
    inspection = await client.get("/v1/operations/" + receipt["operation_id"])
    inspection.raise_for_status()
    return inspection.json()
```

A 202 response means accepted/pending work; inspect its operation identity again.
A terminal receipt uses 200 and its `state` distinguishes complete, failed,
partial and ambiguous. Never infer successful effects from the HTTP status alone.
Equivalent retained retries reuse the original identity. Do not change content
under a retry key or automatically retry an ambiguous effect.

Rejections carry `correlation_id` and a structured `diagnostic`, without an
accepted operation identity. HTTP classifications are 401 authentication,
404 hidden/unknown content, 403 explicitly visible denial, 422 invalid input,
413 limits, 409 conflicts, 429 capacity and 503 unavailable guarantees. Existing
facade diagnostic codes remain unchanged in the body. Unknown rejection codes
are conservatively unavailable. Provider exceptions never expose their raw text.
Current synthetic retention is temporary; inspect deployment epoch and retention
profile rather than assuming restart durability. Runtime capacity/wait/shutdown
configuration discovery is completed with host composition.
