"""REST ASGI adapter evidence; actual socket/MCP parity belongs downstream."""

import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI
from fixture_admission import AdmissionFixture
from fixture_controls import Checkpoint
from fixture_dispatch import ALICE, RESOURCE
from fixture_execution import ExecutionFixture, executor

from craftreport.adapters.transport_wire import TransportWireAdapter
from craftreport.application import ports
from craftreport.application.execution import Execution
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.contracts import OperationLimits
from craftreport.interfaces.http import rest_router
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary


def client(
    fixture: AdmissionFixture, *, max_raw_bytes: int = 1_048_576, owner: Execution | None = None
) -> httpx.AsyncClient:
    boundary, credentials = PrincipalBoundary.conformance(
        "127.0.0.1",
        "deployment",
        (AuthenticatedIdentity(ALICE.subject, ALICE.permitted_scopes),),
        fixture.access,
    )
    app = FastAPI()
    app.include_router(
        rest_router(
            owner or executor(fixture),
            boundary,
            lambda: True,
            "test-epoch",
            TransportWireAdapter(),
            max_raw_bytes=max_raw_bytes,
        )
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {credentials[0].token}"},
    )


def envelope(**changes: object) -> dict[str, object]:
    return {
        "operation": "fixture.write",
        "contract_version": "1",
        "payload": {},
        "correlation_id": "client-correlation",
        "retry_key": "retry",
        "expected_versions": [
            {"resource": {"kind": "fixture", "identity": "target"}, "version": "1"}
        ],
        **changes,
    }


@pytest.mark.anyio
async def test_rest_discovery_invocation_retry_inspection_and_independent_effect() -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        ready = await connection.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"ready": True, "deployment_epoch": "test-epoch"}
        catalog = await connection.get("/v1/catalog")
        assert catalog.status_code == 200
        assert catalog.headers["cache-control"] == "private, no-store"
        assert catalog.json()["transport_limits"] == {"max_raw_bytes": 1_048_576}
        result = await connection.post("/v1/invoke", json=envelope())
        assert result.status_code == 200
        receipt = result.json()
        assert receipt["state"] == "complete"
        retry = await connection.post("/v1/invoke", json=envelope())
        assert retry.content == result.content
        inspected = await connection.get(f"/v1/operations/{receipt['operation_id']}")
        assert inspected.content == result.content
        snapshot = await fixture.target.read(RESOURCE)
        assert isinstance(snapshot, ports.ResourceSnapshot)
        assert snapshot.content == {"value": "changed"}
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        b'{"payload":1,"payload":2}',
        b'{"payload":NaN}',
        b'{"payload":Infinity}',
        b"\xff",
        b"[]",
        b"{",
    ],
)
async def test_malformed_input_cannot_mutate(body: bytes) -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        result = await connection.post("/v1/invoke", content=body)
        assert result.status_code == 422
        assert result.json()["diagnostic"]["code"] == "invalid_input"
        assert result.json()["correlation_id"]
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_raw_cap_is_counted_in_utf8_bytes_and_cannot_mutate() -> None:
    fixture = AdmissionFixture()
    async with client(fixture, max_raw_bytes=10) as connection:
        result = await connection.post("/v1/invoke", content='{"x":"ééé"}'.encode())
        assert result.status_code == 413
        assert result.json()["diagnostic"]["location"] == ["max_raw_bytes"]
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_missing_credentials_and_generic_openapi_hide_private_schema() -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        connection.headers.clear()
        for path in ("/v1/catalog", "/v1/operations/private"):
            response = await connection.get(path)
            assert response.status_code == 401
            assert "private" not in response.text
        response = await connection.post("/v1/invoke", json=envelope())
        assert response.status_code == 401
        schema = await connection.get("/openapi.json")
        assert "fixture.write" not in schema.text
        assert '"$ref"' not in schema.text
        assert '"anyOf"' in schema.text
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_handler_exception_preserves_uncertain_effect_without_private_diagnostics() -> None:
    fixture = ExecutionFixture("exception")
    async with client(fixture) as connection:
        response = await connection.post("/v1/invoke", json=envelope())
        assert response.status_code == 200
        assert response.json()["state"] == "ambiguous"
        assert "credential-private" not in response.text
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_pending_capacity_conflict_and_unavailability_preserve_meaning() -> None:
    fixture = AdmissionFixture()
    fixture.target.before_effect = point = Checkpoint()
    owner = executor(fixture)
    owner.response_seconds = 0.1
    owner.capacity = 1
    async with client(fixture, owner=owner) as connection:
        task = asyncio.create_task(connection.post("/v1/invoke", json=envelope()))
        await point.wait_until_reached()
        pending = await task
        assert pending.status_code == 202
        assert pending.json()["state"] == "pending"
        retry = await connection.post("/v1/invoke", json=envelope())
        assert retry.content == pending.content, retry.text
        full = await connection.post("/v1/invoke", json=envelope(retry_key="other"))
        assert full.status_code == 429
        point.release()
        assert await owner.shutdown()
        completed = await connection.get(f"/v1/operations/{pending.json()['operation_id']}")
        assert completed.status_code == 200
        assert completed.json()["state"] == "complete"
        conflict = await connection.post("/v1/invoke", json=envelope(payload={"value": "other"}))
        assert conflict.status_code == 409
        fixture.access.available = False
        unavailable = await connection.get("/v1/catalog")
        assert unavailable.status_code == 503
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes",
    [
        {"payload": {"value": 123}},
        {"principal": "alice"},
        {"contract_version": 1},
        {"payload": {"value": 2**54}},
    ],
)
async def test_strict_shared_validation_and_correlation(changes: dict[str, object]) -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        response = await connection.post("/v1/invoke", json=envelope(**changes))
        assert response.status_code == 422
        assert response.json()["correlation_id"] == "client-correlation"
        assert "operation_id" not in response.json()
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_hidden_operations_and_foreign_receipts_do_not_disclose_content() -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        unknown = await connection.post("/v1/invoke", json=envelope(operation="private.secret"))
        assert unknown.status_code == 404
        hidden = await connection.get("/v1/operations/foreign-secret")
        assert hidden.status_code == 404
        assert "foreign-secret" not in hidden.text
        fixture.access.grants = ()
        denied = await connection.get("/v1/catalog")
        assert denied.status_code == 404
        assert "fixture" not in denied.text
        assert fixture.target.effect_count == 0


def set_limits(fixture: AdmissionFixture, limits: OperationLimits) -> None:
    bound = fixture.registry.resolve("fixture.write", "1")
    assert bound is not None
    descriptor = replace(bound.descriptor, limits=limits)
    registry = ImmutableOperationRegistry((replace(bound, descriptor=descriptor),))
    fixture.registry = registry
    fixture.guards = replace(fixture.guards, registry=registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    fixture.catalog = replace(fixture.catalog, operations=registry.describe())


@pytest.mark.anyio
@pytest.mark.parametrize(
    "limits,payload,location",
    [
        (OperationLimits(max_input_bytes=100), {}, "max_input_bytes"),
        (OperationLimits(max_nesting_depth=5), {"value": [[[["nested"]]]]}, "max_nesting_depth"),
    ],
)
async def test_advertised_descriptor_limits_apply_before_behavior(
    limits: OperationLimits, payload: dict[str, object], location: str
) -> None:
    fixture = AdmissionFixture()
    set_limits(fixture, limits)
    async with client(fixture) as connection:
        catalog = (await connection.get("/v1/catalog")).json()
        assert catalog["operations"][0]["limits"][location] == getattr(limits, location)
        response = await connection.post("/v1/invoke", json=envelope(payload=payload))
        assert response.status_code == 413
        assert response.json()["diagnostic"]["location"] == [location]
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_custom_large_decoded_limit_has_no_hidden_default_envelope_cap() -> None:
    fixture = AdmissionFixture()
    set_limits(fixture, OperationLimits(max_input_bytes=2_000_000))
    # Envelope metadata is large while the existing payload codec remains within its own cap.
    async with client(fixture, max_raw_bytes=2_100_000) as connection:
        response = await connection.post(
            "/v1/invoke", json=envelope(correlation_id="x" * 1_050_000)
        )
        assert response.status_code == 200
        assert response.json()["state"] == "complete"
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_documented_client_example_runs_against_real_execution() -> None:
    from collections.abc import Awaitable, Callable
    from pathlib import Path
    from typing import cast

    text = Path("docs/rest-client.md").read_text(encoding="utf-8")
    code = text.split("```python\n", 1)[1].split("```", 1)[0]
    namespace: dict[str, object] = {}
    exec(compile(code, "docs/rest-client.md", "exec"), namespace)
    example = cast(
        Callable[[httpx.AsyncClient], Awaitable[dict[str, object]]], namespace["write_and_inspect"]
    )
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        receipt = await example(connection)
        assert receipt["state"] == "complete"
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_streamed_raw_cap_does_not_trust_content_length() -> None:
    from collections.abc import AsyncIterator

    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"x":'
        yield b'"1234567890"}'

    fixture = AdmissionFixture()
    async with client(fixture, max_raw_bytes=10) as connection:
        response = await connection.post(
            "/v1/invoke", content=chunks(), headers={"Content-Length": "1"}
        )
        assert response.status_code == 413
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_oversized_output_is_truthful_terminal_failure_after_real_effect() -> None:
    fixture = AdmissionFixture()
    set_limits(fixture, OperationLimits(max_output_bytes=5))
    async with client(fixture) as connection:
        response = await connection.post("/v1/invoke", json=envelope())
        assert response.status_code == 200
        assert response.json()["state"] != "complete"
        assert response.json()["diagnostics"][0]["code"] == "result_invalid"
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_query_uses_same_facade_without_business_mutation() -> None:
    fixture = AdmissionFixture()
    registry = ImmutableOperationRegistry((fixture.binding.bind(),))
    fixture.registry = registry
    fixture.guards = replace(fixture.guards, registry=registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    fixture.access.operation_scopes[fixture.binding.descriptor.key] = "read"
    async with client(fixture) as connection:
        response = await connection.post(
            "/v1/invoke",
            json=envelope(
                operation="fixture.read",
                payload={"target": "target"},
                retry_key=None,
                expected_versions=[],
            ),
        )
        assert response.status_code == 200
        assert response.json()["state"] == "complete"
        assert fixture.calls == 1
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_surrogate_correlation_rejection_is_serializable_and_safe() -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        response = await connection.post(
            "/v1/invoke",
            content=(
                b'{"operation":"fixture.write","contract_version":"1",'
                b'"payload":{},"correlation_id":"\\ud800"}'
            ),
        )
        assert response.status_code == 422
        assert response.json()["correlation_id"]
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes,location",
    [
        ({"contract_version": 1}, ["contract_version"]),
        ({"contract_version": "01"}, ["contract_version"]),
        ({"operation": "private/secret"}, ["operation"]),
        ({"payload": list[object]()}, ["payload"]),
        ({"retry_key": ""}, ["retry_key"]),
        ({"retry_key": "   "}, ["retry_key"]),
        ({"credential-secret": "private-value"}, ["field"]),
        ({"expected_versions": "private-value"}, ["expected_versions"]),
        (
            {"expected_versions": [{"resource": list[object](), "version": "1"}]},
            ["expected_versions", 0, "resource"],
        ),
        (
            {
                "expected_versions": [
                    {"resource": {"kind": "fixture", "identity": 123}, "version": "1"}
                ]
            },
            ["expected_versions", 0, "resource", "identity"],
        ),
        (
            {
                "expected_versions": [
                    {"resource": {"kind": "fixture", "identity": "target"}, "version": 1}
                ]
            },
            ["expected_versions", 0, "version"],
        ),
        (
            {
                "expected_versions": [
                    {
                        "resource": {
                            "kind": "fixture",
                            "identity": "target",
                            "credential-secret": "private-value",
                        },
                        "version": "1",
                    }
                ]
            },
            ["expected_versions", 0, "resource", "field"],
        ),
    ],
)
async def test_invalid_envelope_locations_are_public_and_preserve_correlation(
    changes: dict[str, object], location: list[str | int]
) -> None:
    fixture = AdmissionFixture()
    async with client(fixture) as connection:
        response = await connection.post("/v1/invoke", json=envelope(**changes))
        assert response.status_code == 422
        value = response.json()
        assert value["diagnostic"]["location"] == location
        assert value["correlation_id"] == "client-correlation"
        assert "operation_id" not in value
        assert "credential-secret" not in response.text
        assert "private-value" not in response.text
        assert "private/secret" not in response.text
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_duplicate_expected_resources_have_public_envelope_location() -> None:
    fixture = AdmissionFixture()
    pin = {"resource": {"kind": "fixture", "identity": "target"}, "version": "1"}
    async with client(fixture) as connection:
        response = await connection.post("/v1/invoke", json=envelope(expected_versions=[pin, pin]))
        assert response.status_code == 422
        assert response.json()["diagnostic"]["location"] == ["expected_versions"]
        assert response.json()["correlation_id"] == "client-correlation"
        assert "operation_id" not in response.json()
        assert fixture.target.effect_count == 0
