"""Assembled ordinary interfaces share actual guarded effects and owned lifetimes."""

import httpx2
import pytest
from fixture_host import HostFixture
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from test_transport_parity import envelope

from craftreport.composition.app import open_application


@pytest.mark.anyio
async def test_composed_discovery_effect_retry_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = HostFixture(monkeypatch)
    async with open_application(fixture.settings, fixture.providers()) as host:
        async with host.app.router.lifespan_context(host.app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
                headers={"Authorization": f"Bearer {fixture.token}"},
            ) as http:
                catalog = await http.get("/v1/catalog")
                assert catalog.status_code == 200
                assert catalog.json()["capabilities"][0]["verification"] == "pending"
                assert catalog.json()["execution_limits"]["capacity"] == 16
                async with Client(
                    streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http)
                ) as client:
                    assert "fixture.write.v1" in [
                        item.name for item in (await client.list_tools()).tools
                    ]
                    mcp_catalog = await client.call_tool("craftreport.catalog.v1", {})
                    rest_catalog = catalog.json()
                    rest_catalog.pop("transport_limits")
                    assert mcp_catalog.structured_content == rest_catalog
                    result = await client.call_tool("fixture.write.v1", envelope())
                    assert result.structured_content is not None
                    retry = await http.post("/v1/invoke", json=envelope())
                    assert retry.json()["operation_id"] == result.structured_content["operation_id"]
                    assert fixture.fixture.target.effect_count == 1
    assert fixture.events == ["providers-open", "plugin-open", "plugin-close", "providers-close"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "missing", ["access", "journal", "guard", "evidence", "results", "capabilities", "resources"]
)
async def test_missing_guarantee_blocks_effect(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    fixture = HostFixture(monkeypatch)
    fixture.fixture.health.probes.pop(missing)
    # Explicit evidence dependency makes its health mandatory before behavior.
    from dataclasses import replace

    from craftreport.application.registry import ImmutableOperationRegistry

    bound = fixture.bindings()[0]
    bound = replace(bound, descriptor=replace(bound.descriptor, required_services=("evidence",)))
    fixture.fixture.registry = ImmutableOperationRegistry((bound,))
    fixture.manifest = replace(fixture.manifest, operations=fixture.fixture.registry.describe())
    async with open_application(fixture.settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
                headers={"Authorization": f"Bearer {fixture.token}"},
            ) as http,
        ):
            result = await http.post("/v1/invoke", json=envelope())
            assert result.json()["diagnostic"]["code"] == "service_unavailable"
            assert fixture.fixture.target.effect_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/v1/catalog", "/mcp", "/health/ready"])
@pytest.mark.parametrize(
    "headers,status", [({"Host": "evil.example"}, 421), ({"Origin": "https://evil.example"}, 403)]
)
async def test_shared_host_origin_policy(
    monkeypatch: pytest.MonkeyPatch, path: str, headers: dict[str, str], status: int
) -> None:
    fixture = HostFixture(monkeypatch)
    async with open_application(fixture.settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
            ) as http,
        ):
            assert (await http.get(path, headers=headers)).status_code == status


@pytest.mark.anyio
async def test_default_principal_denies_both_protocols(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from craftreport.interfaces.principal import PrincipalBoundary

    fixture = HostFixture(monkeypatch)
    settings = replace(fixture.settings, principal=PrincipalBoundary("deployment"))
    async with open_application(settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
                headers={"Authorization": f"Bearer {fixture.token}"},
            ) as http,
        ):
            assert (await http.get("/v1/catalog")).status_code == 401
            async with Client(
                streamable_http_client("http://127.0.0.1:8000/mcp", http_client=http)
            ) as client:
                with pytest.raises(MCPError, match="Authentication required"):
                    await client.list_tools()
            assert fixture.fixture.target.effect_count == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "duplicate",
    [
        '"operation":"secret","operation":"fixture.write"',
        '"payload":{"value":"secret","value":"changed"}',
    ],
)
@pytest.mark.parametrize("authenticated", [True, False])
async def test_mcp_duplicate_framing_has_no_effect(
    monkeypatch: pytest.MonkeyPatch, duplicate: str, authenticated: bool
) -> None:
    fixture = HostFixture(monkeypatch)
    body = (
        '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fixture.write.v1","arguments":{'
        + duplicate
        + "}}}"
    )
    async with open_application(fixture.settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
            ) as http,
        ):
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }
            if authenticated:
                headers["Authorization"] = f"Bearer {fixture.token}"
            result = await http.post("/mcp", content=body, headers=headers)
            assert result.status_code == 400
            assert result.json()["error"]["message"] == "Invalid JSON framing"
            assert "secret" not in result.text
            assert fixture.fixture.target.effect_count == 0


@pytest.mark.anyio
async def test_supplied_policy_and_unavailable_handoff_prevent_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    from craftreport.interfaces.principal import DenyAccess

    fixture = HostFixture(monkeypatch)
    settings = replace(
        fixture.settings, principal=replace(fixture.settings.principal, policy=DenyAccess())
    )
    async with open_application(settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
                headers={"Authorization": f"Bearer {fixture.token}"},
            ) as http,
        ):
            assert (await http.get("/v1/catalog")).status_code == 404
            assert (await http.post("/v1/invoke", json=envelope())).status_code == 404
    fixture.handoffs.available = False
    async with open_application(fixture.settings, fixture.providers()) as host:
        async with (
            host.app.router.lifespan_context(host.app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=host.app),
                base_url="http://127.0.0.1:8000",
                headers={"Authorization": f"Bearer {fixture.token}"},
            ) as http,
        ):
            result = await http.post("/v1/invoke", json=envelope())
            assert result.json()["diagnostic"]["code"] == "service_unavailable"
    assert fixture.fixture.target.effect_count == 0
