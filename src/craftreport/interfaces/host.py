"""Explicit Host/Origin policy shared by REST and MCP."""

import json

from mcp.server.transport_security import TransportSecurityMiddleware, TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class HostOriginMiddleware:
    def __init__(self, app: ASGIApp, settings: TransportSecuritySettings) -> None:
        self.app = app
        self.security = TransportSecurityMiddleware(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            request = Request(scope)
            if (
                len(request.headers.getlist("host")) != 1
                or len(request.headers.getlist("origin")) > 1
            ):
                await Response("Invalid transport headers", status_code=400)(scope, receive, send)
                return
            # is_post=False deliberately checks only Host/Origin, not MCP framing.
            rejected = await self.security.validate_request(request, is_post=False)
            if rejected is not None:
                await rejected(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise ValueError("Duplicate JSON member")
        values[key] = value
    return values


def _invalid_number(value: str) -> object:
    raise ValueError("Non-finite JSON number")


class McpFramingMiddleware:
    """Reject ambiguous JSON framing before the SDK's last-member-wins parser."""

    def __init__(self, app: ASGIApp, max_body_bytes: int) -> None:
        self.app = app
        self.maximum = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self.maximum:
                await Response("Request body too large", status_code=413)(scope, receive, send)
                return
            body.extend(chunk)
        try:
            json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_constant=_invalid_number,
            )
        except (ValueError, UnicodeError, RecursionError):
            await JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Invalid JSON framing"},
                },
                status_code=400,
            )(scope, receive, send)
            return
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
