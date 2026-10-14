"""Host lifetime failures remain failures and still unwind acquired resources."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from socket import AF_INET, SOCK_STREAM, socket

import httpx2
import pytest
from fixture_host import HostFixture
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from craftreport.application.execution import Execution
from craftreport.composition.app import open_application
from craftreport.contracts.capabilities import ExecutionLimits


@pytest.mark.anyio
@pytest.mark.parametrize(
    "phase", ["activation", "plugin-close", "assembly", "sessions", "execution"]
)
async def test_startup_and_cleanup_failures_unwind(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    fixture = HostFixture(monkeypatch)
    if phase == "activation":
        fixture.fail_open = True
    if phase == "plugin-close":
        fixture.fail_close = True
    if phase == "assembly":
        fixture.settings = replace(fixture.settings, max_raw_bytes=1)
    if phase == "sessions":

        @asynccontextmanager
        async def fail_sessions(self: StreamableHTTPSessionManager) -> AsyncGenerator[None]:
            raise RuntimeError("session-failure")
            yield

        monkeypatch.setattr(StreamableHTTPSessionManager, "run", fail_sessions)
    if phase == "execution":

        async def fail_shutdown(self: Execution) -> bool:
            assert fixture.events == ["providers-open", "plugin-open"]
            return False

        monkeypatch.setattr(Execution, "shutdown", fail_shutdown)
    with pytest.raises((ValueError, RuntimeError, ExceptionGroup)):
        async with open_application(fixture.settings, fixture.providers()) as host:
            async with host.app.router.lifespan_context(host.app):
                pass
    assert fixture.events[-1] == "providers-close"
    if phase != "activation":
        assert fixture.events[-2] == "plugin-close"


@pytest.mark.anyio
async def test_readiness_lifetime_and_runtime_limit_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = HostFixture(monkeypatch)
    limits = ExecutionLimits(3, 0.2, 0.4)
    settings = replace(fixture.settings, execution=limits)
    observed: list[Execution] = []
    original = Execution.__post_init__

    def observe(self: Execution) -> None:
        original(self)
        observed.append(self)

    monkeypatch.setattr(Execution, "__post_init__", observe)
    async with open_application(settings, fixture.providers()) as host:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=host.app),
            base_url="http://127.0.0.1:8000",
            headers={"Authorization": f"Bearer {fixture.token}"},
        ) as http:
            assert (await http.get("/health/ready")).status_code == 503
            async with host.app.router.lifespan_context(host.app):
                assert (await http.get("/health/ready")).status_code == 200
                catalog = (await http.get("/v1/catalog")).json()
                assert catalog["execution_limits"] == {
                    "capacity": 3,
                    "response_seconds": 0.2,
                    "shutdown_seconds": 0.4,
                }
                assert (
                    observed[0].capacity,
                    observed[0].response_seconds,
                    observed[0].shutdown_seconds,
                ) == (3, 0.2, 0.4)
            assert (await http.get("/health/ready")).status_code == 503


@pytest.mark.anyio
async def test_listener_validates_actual_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = HostFixture(monkeypatch)
    async with open_application(fixture.settings, fixture.providers()) as host:
        with socket(AF_INET, SOCK_STREAM) as listener:
            listener.bind(("0.0.0.0", 0))
            with pytest.raises(ValueError, match="127.0.0.1"):
                host.server(listener)
        with socket(AF_INET, SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            server = host.server(listener)
            server.validate()
            server.request_shutdown()


@pytest.mark.parametrize("host", ["localhost", "::1", "0.0.0.0"])
def test_conformance_settings_reject_other_hosts(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    fixture = HostFixture(monkeypatch)
    with pytest.raises(ValueError, match="127.0.0.1"):
        replace(fixture.settings, bind_host=host)


@pytest.mark.anyio
async def test_cancellation_resistant_execution_reports_failed_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    from fixture_execution import ExecutionFixture
    from test_transport_parity import envelope

    fixture = HostFixture(monkeypatch)
    execution_fixture = ExecutionFixture("resist")
    fixture.fixture = execution_fixture
    fixture.manifest = replace(fixture.manifest, operations=execution_fixture.registry.describe())
    settings = replace(fixture.settings, execution=ExecutionLimits(1, 0.02, 0.03))
    try:
        with pytest.raises(ExceptionGroup, match="TaskGroup"):
            async with open_application(settings, fixture.providers()) as host:
                async with (
                    host.app.router.lifespan_context(host.app),
                    httpx2.AsyncClient(
                        transport=httpx2.ASGITransport(app=host.app),
                        base_url="http://127.0.0.1:8000",
                        headers={"Authorization": f"Bearer {fixture.token}"},
                    ) as http,
                ):
                    response = await http.post("/v1/invoke", json=envelope())
                    assert response.json()["state"] == "pending"
                    assert execution_fixture.target.effect_count == 1
        assert fixture.events[-2:] == ["plugin-close", "providers-close"]
    finally:
        execution_fixture.finish.set()
        await asyncio.sleep(0.02)


@pytest.mark.anyio
async def test_swallowed_asgi_failure_is_still_host_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = HostFixture(monkeypatch)

    async def fail_shutdown(self: Execution) -> bool:
        return False

    monkeypatch.setattr(Execution, "shutdown", fail_shutdown)
    with pytest.raises(RuntimeError, match="Host lifespan failed"):
        async with open_application(fixture.settings, fixture.providers()) as host:
            try:
                async with host.app.router.lifespan_context(host.app):
                    pass
            except ExceptionGroup:
                # Uvicorn logs ASGI lifespan errors rather than re-raising them.
                pass
    assert fixture.events[-2:] == ["plugin-close", "providers-close"]
