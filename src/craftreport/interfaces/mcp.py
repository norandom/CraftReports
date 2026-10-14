"""Registry-driven MCP adaptation; composition owns transport and lifespan."""

import json
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from mcp import types
from mcp.server import Server, ServerRequestContext
from mcp.shared.exceptions import MCPError
from starlette.requests import Request

from craftreport.application.dispatch_ports import WireFailure
from craftreport.application.ports import CatalogRejected, Facade
from craftreport.application.transport import TransportWire
from craftreport.contracts import (
    Diagnostic,
    InvocationResult,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    Principal,
    RecoveryDisposition,
    Rejection,
)
from craftreport.interfaces.principal import AuthenticationRejected, PrincipalBoundary

_CATALOG = "craftreport.catalog.v1"
_INSPECT = "craftreport.inspect.v1"


def _reject(code: str, correlation: str, location: tuple[str | int, ...] = ()) -> Rejection:
    return Rejection(
        correlation,
        Diagnostic(
            OperationKey("craftreport.invoke", "1"),
            "transport",
            code,
            RecoveryDisposition.RETRY
            if code == "unavailable"
            else RecoveryDisposition.CORRECT_REQUEST,
            location,
        ),
    )


def _correlation(value: JsonObject) -> str:
    supplied = value.get("correlation_id")
    if isinstance(supplied, str) and supplied.strip():
        try:
            supplied.encode("utf-8")
            return supplied
        except UnicodeError:
            pass
    return str(uuid4())


def _plain(wire: TransportWire, value: JsonObject) -> dict[str, object]:
    # SDK JSON objects require mutable dict/list values, not frozen contract containers.
    return cast(dict[str, object], json.loads(wire.canonical_bytes(value)))


@dataclass(frozen=True, slots=True)
class _Mcp:
    facade: Facade
    principal: PrincipalBoundary
    wire: TransportWire

    async def caller(self, ctx: ServerRequestContext[object]) -> Principal:
        request: object = ctx.request
        if not isinstance(request, Request):
            raise AuthenticationRejected()
        return await self.principal.resolve(cast(Request, ctx.request))

    def content(self, value: JsonObject, error: bool = False) -> types.CallToolResult:
        encoded = self.wire.canonical_bytes(value).decode("utf-8")
        return types.CallToolResult(
            structured_content=_plain(self.wire, value),
            content=[types.TextContent(type="text", text=encoded)],
            is_error=error,
        )

    def result(self, value: InvocationResult) -> types.CallToolResult:
        try:
            return self.content(
                self.wire.encode_invocation_result(value), self.wire.result_is_error(value)
            )
        except Exception:
            unavailable = _reject("unavailable", value.correlation_id)
            return self.content(self.wire.encode_invocation_result(unavailable), True)

    async def execute(
        self, invocation: Awaitable[InvocationResult], correlation: str
    ) -> types.CallToolResult:
        try:
            return self.result(await invocation)
        except Exception:
            return self.result(_reject("unavailable", correlation))

    def tool(self, descriptor: OperationDescriptor) -> types.Tool:
        key = descriptor.key
        return types.Tool(
            name=f"{key.name}.v{key.contract_version}",
            description=f"{descriptor.kind.value}: {key.name}, contract {key.contract_version}.",
            input_schema=_plain(self.wire, self.wire.envelope_schema(key, descriptor.input_schema)),
            output_schema=_plain(self.wire, self.wire.invocation_result_schema()),
        )

    def builtins(self) -> list[types.Tool]:
        return [
            types.Tool(
                name=_CATALOG,
                description="Inspect the authorized operation catalog.",
                input_schema={"type": "object", "properties": {}, "additionalProperties": False},
                output_schema={"type": "object"},
            ),
            types.Tool(
                name=_INSPECT,
                description="Inspect an authorized retained receipt.",
                input_schema={
                    "type": "object",
                    "properties": {"operation_id": {"type": "string", "minLength": 1}},
                    "required": ["operation_id"],
                    "additionalProperties": False,
                },
                output_schema=_plain(self.wire, self.wire.invocation_result_schema()),
            ),
        ]

    async def list_tools(
        self, ctx: ServerRequestContext[object], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        try:
            principal = await self.caller(ctx)
            catalog = await self.facade.catalog(principal)
            if params is not None and params.cursor is not None:
                raise MCPError(types.INVALID_PARAMS, "Unsupported cursor")
            tools = self.builtins() + [self.tool(item) for item in catalog.operations]
            return types.ListToolsResult(tools=sorted(tools, key=lambda tool: tool.name))
        except AuthenticationRejected:
            raise MCPError(types.INVALID_REQUEST, "Authentication required") from None
        except CatalogRejected as error:
            raise MCPError(types.INVALID_REQUEST, error.rejection.diagnostic.code) from None
        except MCPError:
            raise
        except Exception:
            raise MCPError(types.INTERNAL_ERROR, "Discovery unavailable") from None

    async def invoke(
        self, principal: Principal, name: str, arguments: JsonObject
    ) -> types.CallToolResult:
        if name == _INSPECT:
            identity = arguments.get("operation_id")
            if (
                set(arguments) != {"operation_id"}
                or not isinstance(identity, str)
                or not identity.strip()
            ):
                raise WireFailure("invalid_input", location=("operation_id",))
            return await self.execute(
                self.facade.inspect(principal, identity), _correlation(arguments)
            )
        catalog = await self.facade.catalog(principal)
        if name == _CATALOG:
            if arguments:
                raise WireFailure("invalid_input", location=("field",))
            try:
                return self.content(self.wire.encode_catalog(catalog))
            except Exception:
                return self.result(_reject("unavailable", _correlation(arguments)))
        mapping = {
            f"{item.key.name}.v{item.key.contract_version}": item for item in catalog.operations
        }
        descriptor = mapping.get(name)
        if descriptor is None:
            raise MCPError(types.INVALID_PARAMS, "Unknown or inaccessible tool")
        envelope = self.wire.decode_envelope(arguments, descriptor.limits)
        if envelope.operation != descriptor.key:
            field = (
                "operation"
                if envelope.operation.name != descriptor.key.name
                else "contract_version"
            )
            raise WireFailure("invalid_input", location=(field,))
        return await self.execute(self.facade.invoke(principal, envelope), envelope.correlation_id)

    async def call_tool(
        self, ctx: ServerRequestContext[object], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        arguments: JsonObject = params.arguments or {}
        correlation = _correlation(arguments)
        try:
            principal = await self.caller(ctx)
            return await self.invoke(principal, params.name, arguments)
        except AuthenticationRejected:
            return self.result(_reject("unauthenticated", correlation))
        except CatalogRejected as error:
            return self.result(error.rejection)
        except WireFailure as error:
            location = (error.limit,) if error.limit else error.location
            return self.result(_reject(error.code, correlation, location))
        except MCPError:
            raise
        except Exception:
            return self.result(_reject("unavailable", correlation))


def mcp_server(facade: Facade, principal: PrincipalBoundary, wire: TransportWire) -> Server[object]:
    """Create the ordinary MCP boundary; the host configures framing and lifespan."""
    adapter = _Mcp(facade, principal, wire)
    return Server(
        "CraftReport",
        version="1.0.0",
        on_list_tools=adapter.list_tools,
        on_call_tool=adapter.call_tool,
    )
