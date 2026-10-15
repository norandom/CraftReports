"""Own explicit deployment providers, activated capabilities and both interfaces."""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from socket import socket

import uvicorn
from fastapi import FastAPI
from mcp.server import Server
from mcp.server.transport_security import TransportSecuritySettings

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.transport_wire import TransportWireAdapter
from craftreport.adapters.validation import DecodedInvocationLimits
from craftreport.application import ports
from craftreport.application.admission import CommandAdmission
from craftreport.application.dispatch import Inspection, QueryDispatcher
from craftreport.application.execution import Execution
from craftreport.application.guards import InvocationGuards
from craftreport.application.verification import resolve_verification
from craftreport.composition.plugins import ActivationSnapshot, activate_snapshot
from craftreport.composition.settings import GuaranteeProviders, HostSettings
from craftreport.contracts import CapabilityView, Catalog
from craftreport.contracts.capabilities import CORE_CONTRACT_VERSION
from craftreport.interfaces.host import HostOriginMiddleware, McpFramingMiddleware
from craftreport.interfaces.http import rest_router
from craftreport.interfaces.mcp import mcp_server


@dataclass
class _Lifetime:
    execution: Execution
    ready: bool = False
    shutdown_attempted: bool = False
    failure: BaseException | None = None

    async def shutdown(self) -> None:
        self.ready = False
        self.shutdown_attempted = True
        if not await self.execution.shutdown():
            raise RuntimeError("Admitted execution did not close within shutdown grace")

    @asynccontextmanager
    async def sessions(self, server: Server[object]) -> AsyncGenerator[None]:
        try:
            async with server.session_manager.run():
                self.ready = True
                try:
                    yield
                finally:
                    await self.shutdown()
        except BaseException as exc:
            self.failure = exc
            raise
        finally:
            self.ready = False

    def check(self) -> None:
        if self.failure is not None:
            raise RuntimeError("Host lifespan failed") from self.failure


@dataclass(frozen=True, slots=True)
class BoundServer:
    """A server retaining the validated listener; caller owns closing that socket."""

    _server: uvicorn.Server
    _listener: socket
    settings: HostSettings
    _lifetime: _Lifetime

    def validate(self) -> None:
        actual = self._listener.getsockname()[0]
        self.settings.principal.validate_bind(actual)
        if actual != self.settings.bind_host:
            raise ValueError("Listener address differs from configured bind host")

    async def serve(self) -> None:
        self.validate()
        await self._server.serve(sockets=[self._listener])
        self._lifetime.check()
        if not self._server.started:
            raise RuntimeError("Host did not start")

    def request_shutdown(self) -> None:
        self._server.should_exit = True


@dataclass(frozen=True, slots=True)
class HostedApplication:
    app: FastAPI
    settings: HostSettings
    _lifetime: _Lifetime

    def server(self, listener: socket) -> BoundServer:
        server = BoundServer(
            uvicorn.Server(uvicorn.Config(self.app, host=self.settings.bind_host, lifespan="on")),
            listener,
            self.settings,
            self._lifetime,
        )
        server.validate()
        return server


def _views(snapshot: ActivationSnapshot, settings: HostSettings) -> tuple[CapabilityView, ...]:
    expectations = {item.identity.package: item for item in settings.verification}
    views: list[CapabilityView] = []
    for manifest in snapshot.manifests:
        expectation = expectations.get(manifest.package)
        if expectation is None or (
            expectation.identity.package_version != manifest.version
            or expectation.identity.implementation_digest != manifest.implementation_digest
            or expectation.identity.core_contract_version != CORE_CONTRACT_VERSION
        ):
            views.append(CapabilityView(manifest))
        else:
            identity = expectation.identity
            views.append(
                resolve_verification(
                    manifest,
                    expectation.record,
                    core_contract_version=identity.core_contract_version,
                    fixture_suite=identity.fixture_suite,
                    dependency_versions=identity.dependency_versions,
                )
            )
    return tuple(views)


def _execution(
    snapshot: ActivationSnapshot, services: GuaranteeProviders, settings: HostSettings
) -> Execution:
    access = settings.principal.access_policy
    reads = ports.ReadServices(services.evidence, services.capabilities, services.resources)
    commands = ports.CommandServices(reads, services.effects)
    guards = InvocationGuards(
        snapshot.registry, access, services.capabilities, services.health, DecodedInvocationLimits()
    )
    catalog = Catalog(
        snapshot.registry.describe(),
        _views(snapshot, settings),
        settings.deployment_epoch,
        settings.retention_profile,
        execution_limits=settings.execution,
    )
    inspection = Inspection(catalog, access, services.journal, services.results, services.evidence)
    queries = QueryDispatcher(guards, services.journal, reads, services.results, catalog)
    admission = CommandAdmission(guards, services.journal, services.guard, CanonicalFingerprint())
    limits = settings.execution
    return Execution(
        admission,
        queries,
        inspection,
        commands,
        services.handoffs,
        settings.installed_owners,
        limits.capacity,
        limits.response_seconds,
        limits.shutdown_seconds,
    )


def _app(settings: HostSettings, lifetime: _Lifetime) -> FastAPI:
    wire = TransportWireAdapter()
    server = mcp_server(lifetime.execution, settings.principal, wire)
    security = TransportSecuritySettings(
        allowed_hosts=list(settings.allowed_hosts), allowed_origins=list(settings.allowed_origins)
    )
    transport = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        max_request_body_size=settings.max_raw_bytes + 4096,
        transport_security=security,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with lifetime.sessions(server):
            yield

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(HostOriginMiddleware, settings=security)
    app.include_router(
        rest_router(
            lifetime.execution,
            settings.principal,
            lambda: lifetime.ready,
            settings.deployment_epoch,
            wire,
            max_raw_bytes=settings.max_raw_bytes,
        )
    )
    app.mount("/", McpFramingMiddleware(transport, settings.max_raw_bytes + 4096))
    return app


@asynccontextmanager
async def open_application(
    settings: HostSettings,
    providers: AbstractAsyncContextManager[GuaranteeProviders],
    *,
    on_activation: Callable[[ActivationSnapshot], AbstractAsyncContextManager[None]] | None = None,
) -> AsyncGenerator[HostedApplication]:
    """Keep the context open until the server lifespan and all clients have exited."""
    settings.principal.validate_bind(settings.bind_host)
    async with AsyncExitStack() as stack:
        services = await stack.enter_async_context(providers)
        snapshot = await stack.enter_async_context(activate_snapshot(settings.selections))
        if on_activation is not None:
            await stack.enter_async_context(on_activation(snapshot))
        if any(
            item.limits.max_input_bytes > settings.max_raw_bytes
            for item in snapshot.registry.describe()
        ):
            raise ValueError("Raw framing cap cannot undercut advertised decoded input limits")
        lifetime = _Lifetime(_execution(snapshot, services, settings))
        try:
            yield HostedApplication(_app(settings, lifetime), settings, lifetime)
            lifetime.check()
        finally:
            if not lifetime.shutdown_attempted:
                await lifetime.shutdown()
