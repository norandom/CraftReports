"""Official ordinary MCP client over ASGI, with real guarded execution."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx2
import pytest
from fixture_admission import AdmissionFixture
from fixture_dispatch import ALICE, RESOURCE
from fixture_execution import executor
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from test_transport_parity import envelope

from craftreport.adapters.transport_wire import TransportWireAdapter
from craftreport.application import ports
from craftreport.application.execution import Execution
from craftreport.contracts import Principal
from craftreport.interfaces.mcp import mcp_server
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary


@asynccontextmanager
async def connection(
    fixture: AdmissionFixture,
    owner: Execution | None = None,
    *,
    identity: Principal = ALICE,
    token: str | None = None,
    wire: TransportWireAdapter | None = None,
) -> AsyncGenerator[Client]:
    fixture.catalog = replace(fixture.catalog, operations=fixture.registry.describe())
    boundary, credentials = PrincipalBoundary.conformance(
        "127.0.0.1",
        "deployment",
        (AuthenticatedIdentity(identity.subject, identity.permitted_scopes),),
        fixture.access,
    )
    server = mcp_server(owner or executor(fixture), boundary, wire or TransportWireAdapter())
    app = server.streamable_http_app(json_response=True, stateless_http=True)
    async with (
        server.session_manager.run(),
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers={"Authorization": f"Bearer {credentials[0].token if token is None else token}"},
        ) as http,
    ):
        async with Client(
            streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http)
        ) as client:
            yield client


@pytest.mark.anyio
async def test_discovery_call_inspection_and_independent_effect() -> None:
    fixture = AdmissionFixture()
    async with connection(fixture) as client:
        tools = (await client.list_tools()).tools
        assert [tool.name for tool in tools] == [
            "craftreport.catalog.v1",
            "craftreport.inspect.v1",
            "craftreport.result.v1",
            "fixture.write.v1",
        ]
        result = await client.call_tool("fixture.write.v1", envelope())
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["state"] == "complete"
        assert isinstance(result.content[0], TextContent)
        assert (
            result.content[0].text
            == TransportWireAdapter().canonical_bytes(result.structured_content).decode()
        )
        inspected = await client.call_tool(
            "craftreport.inspect.v1",
            {"operation_id": result.structured_content["operation_id"]},
        )
        assert inspected.structured_content == result.structured_content
        snapshot = await fixture.target.read(RESOURCE)
        assert isinstance(snapshot, ports.ResourceSnapshot)
        assert snapshot.content == {"value": "changed"}
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes,code,location",
    [
        ({"contract_version": "2"}, "invalid_input", ["contract_version"]),
        ({"operation": "fixture.read"}, "invalid_input", ["operation"]),
        ({"payload": {"value": 123}}, "invalid_input", ["value"]),
        ({"principal": "alice"}, "invalid_input", ["field"]),
        ({"contract_version": 1}, "invalid_input", ["contract_version"]),
    ],
)
async def test_exact_mapping_and_validation_have_no_effect(
    changes: dict[str, object], code: str, location: list[str]
) -> None:
    fixture = AdmissionFixture()
    async with connection(fixture) as client:
        result = await client.call_tool("fixture.write.v1", envelope(**changes))
        assert result.is_error
        assert result.structured_content is not None
        diagnostic = result.structured_content["diagnostic"]
        assert diagnostic["code"] == code
        assert diagnostic["location"] == location
        assert result.structured_content["correlation_id"] == "client-correlation"
        assert "operation_id" not in result.structured_content
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_unknown_tools_are_protocol_errors_and_permission_changes_hide_tools() -> None:
    from mcp.shared.exceptions import MCPError

    fixture = AdmissionFixture()
    async with connection(fixture) as client:
        await client.list_tools()
        with pytest.raises(MCPError):
            await client.call_tool("private.secret.v1", envelope())
        fixture.access.operation_scopes.clear()
        listed = await client.list_tools(cache_mode="refresh")
        assert all(tool.name != "fixture.write.v1" for tool in listed.tools)
        with pytest.raises(MCPError):
            await client.call_tool("fixture.write.v1", envelope())
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_catalog_payload_and_schema_metadata_match_registered_contracts() -> None:
    fixture = AdmissionFixture()
    async with connection(fixture) as client:
        listed = (await client.list_tools()).tools
        tool = next(tool for tool in listed if tool.name == "fixture.write.v1")
        properties = tool.input_schema["properties"]
        assert properties["operation"]["const"] == "fixture.write"
        assert properties["contract_version"]["const"] == "1"
        assert properties["payload"]["properties"]["value"]["type"] == "string"
        assert tool.output_schema is not None and tool.output_schema["type"] == "object"
        result = await client.call_tool("craftreport.catalog.v1", {})
        assert result.structured_content is not None
        operation = result.structured_content["operations"][0]
        assert operation["kind"] == "command"
        assert operation["limits"]["max_input_bytes"] == 1_048_576
        assert fixture.target.effect_count == 0
        assert not fixture.journal.owners


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["exception", "missing", "unavailable"])
async def test_noncomplete_results_are_business_errors_after_real_effect(mode: str) -> None:
    from fixture_execution import ExecutionFixture

    fixture = ExecutionFixture(mode)
    async with connection(fixture) as client:
        result = await client.call_tool("fixture.write.v1", envelope())
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["state"] in ("failed", "partial", "ambiguous")
        assert "credential-private" not in str(result)
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_pending_is_not_error_and_retained_retry_does_not_repeat_effect() -> None:
    import asyncio

    from fixture_controls import Checkpoint

    fixture = AdmissionFixture()
    fixture.target.before_effect = point = Checkpoint()
    fixture.catalog = replace(fixture.catalog, operations=fixture.registry.describe())
    owner = executor(fixture)
    owner.response_seconds = 0.1
    async with connection(fixture, owner) as client:
        task = asyncio.create_task(client.call_tool("fixture.write.v1", envelope()))
        await point.wait_until_reached()
        pending = await task
        assert not pending.is_error
        assert pending.structured_content is not None
        assert pending.structured_content["state"] == "pending"
        retry = await client.call_tool("fixture.write.v1", envelope())
        assert retry.structured_content == pending.structured_content
        point.release()
        assert await owner.shutdown()
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_missing_http_identity_fails_closed_without_effect() -> None:
    from mcp.shared.exceptions import MCPError

    fixture = AdmissionFixture()
    boundary = PrincipalBoundary("deployment")
    server = mcp_server(executor(fixture), boundary, TransportWireAdapter())
    async with Client(server) as client:
        with pytest.raises(MCPError, match="Authentication required"):
            await client.list_tools()
        result = await client.call_tool("fixture.write.v1", envelope())
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "unauthenticated"
    assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_foreign_receipt_and_invalid_credentials_do_not_disclose_content() -> None:
    from mcp.shared.exceptions import MCPError

    fixture = AdmissionFixture()
    async with connection(fixture) as alice:
        result = await alice.call_tool("fixture.write.v1", envelope())
        assert result.structured_content is not None
        operation_id = result.structured_content["operation_id"]
    async with connection(fixture, identity=fixture.bob) as bob:
        result = await bob.call_tool("craftreport.inspect.v1", {"operation_id": operation_id})
        assert result.is_error
        assert result.structured_content is not None
        assert "operation_id" not in result.structured_content
        assert operation_id not in str(result)
    async with connection(fixture, token="invalid") as stranger:
        with pytest.raises(MCPError, match="Authentication required"):
            await stranger.list_tools()
    assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_limits_match_discovery_and_apply_before_execution() -> None:
    from test_transport_parity import set_limits

    from craftreport.contracts import OperationLimits

    fixture = AdmissionFixture()
    set_limits(fixture, OperationLimits(max_input_bytes=100))
    async with connection(fixture) as client:
        result = await client.call_tool("fixture.write.v1", envelope())
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["diagnostic"]["location"] == ["max_input_bytes"]
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_query_uses_shared_facade_without_mutation() -> None:
    from craftreport.application.registry import ImmutableOperationRegistry

    fixture = AdmissionFixture()
    registry = ImmutableOperationRegistry((fixture.binding.bind(),))
    fixture.registry = registry
    fixture.guards = replace(fixture.guards, registry=registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    fixture.access.operation_scopes[fixture.binding.descriptor.key] = "read"
    async with connection(fixture) as client:
        result = await client.call_tool(
            "fixture.read.v1",
            envelope(
                operation="fixture.read",
                payload={"target": "target"},
                retry_key=None,
                expected_versions=[],
            ),
        )
        assert not result.is_error
        assert result.structured_content is not None
        assert result.structured_content["state"] == "complete"
        assert fixture.calls == 1
        assert fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_documented_mcp_example_runs_against_real_execution() -> None:
    from collections.abc import Awaitable, Callable
    from pathlib import Path
    from typing import cast

    source = Path("docs/mcp-client.md").read_text(encoding="utf-8")
    code = source.split("```python\n", 1)[1].split("```", 1)[0]
    namespace: dict[str, object] = {}
    exec(compile(code, "docs/mcp-client.md", "exec"), namespace)
    example = cast(Callable[[Client], Awaitable[dict[str, object]]], namespace["write_and_inspect"])
    fixture = AdmissionFixture()
    async with connection(fixture) as client:
        result = await example(client)
        assert result["state"] == "complete"
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_post_effect_serialization_failure_is_unavailable_and_receipt_remains() -> None:
    from craftreport.application.dispatch_ports import WireFailure
    from craftreport.contracts import InvocationResult, JsonObject, Receipt

    class BrokenReceiptWire(TransportWireAdapter):
        def encode_invocation_result(self, result: InvocationResult) -> JsonObject:
            if isinstance(result, Receipt):
                raise WireFailure("invalid_input")
            return super().encode_invocation_result(result)

    fixture = AdmissionFixture()
    async with connection(fixture, wire=BrokenReceiptWire()) as client:
        result = await client.call_tool("fixture.write.v1", envelope())
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "unavailable"
        assert fixture.target.effect_count == 1
    async with connection(fixture) as client:
        retry = await client.call_tool("fixture.write.v1", envelope())
        assert not retry.is_error
        assert retry.structured_content is not None
        assert retry.structured_content["state"] == "complete"
        assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_depth_and_output_limits_preserve_no_effect_and_truthful_effect() -> None:
    from test_transport_parity import set_limits

    from craftreport.contracts import OperationLimits

    fixture = AdmissionFixture()
    set_limits(fixture, OperationLimits(max_nesting_depth=5))
    async with connection(fixture) as client:
        result = await client.call_tool(
            "fixture.write.v1", envelope(payload={"value": [[[["x"]]]]})
        )
        assert result.structured_content is not None
        assert result.structured_content["diagnostic"]["location"] == ["max_nesting_depth"]
        assert fixture.target.effect_count == 0
    set_limits(fixture, OperationLimits(max_output_bytes=5))
    async with connection(fixture) as client:
        result = await client.call_tool("fixture.write.v1", envelope())
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["state"] != "complete"
        assert result.structured_content["diagnostics"][0]["code"] == "result_invalid"
        assert fixture.target.effect_count == 1
