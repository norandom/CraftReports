"""Guarded REST adaptation; application composition owns the host lifecycle."""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

from fastapi import APIRouter
from starlette.requests import Request
from starlette.responses import Response

from craftreport.application.dispatch_ports import WireFailure
from craftreport.application.ports import CatalogRejected, Facade
from craftreport.application.transport import TransportWire
from craftreport.contracts import (
    Diagnostic,
    InvocationResult,
    JsonObject,
    OperationKey,
    OperationLimits,
    RecoveryDisposition,
    Rejection,
)
from craftreport.contracts.values import JsonValue, require_positive, require_text
from craftreport.interfaces.principal import AuthenticationRejected, PrincipalBoundary


def _response(wire: TransportWire, value: JsonObject, status: int = 200) -> Response:
    return Response(
        wire.canonical_bytes(value),
        status_code=status,
        media_type="application/json",
        headers={"Cache-Control": "private, no-store"},
    )


def _result(wire: TransportWire, value: InvocationResult) -> Response:
    return _response(wire, wire.encode_invocation_result(value), wire.canonical_status(value))


def _inline_schema(schema: JsonObject) -> JsonObject:
    """Embed self-contained models without dangling document-root OpenAPI refs."""
    definitions = schema.get("$defs", {})
    assert isinstance(definitions, Mapping)

    def visit(value: JsonValue) -> JsonValue:
        if isinstance(value, Mapping):
            reference = value.get("$ref")
            if isinstance(reference, str):
                return visit(definitions[reference.removeprefix("#/$defs/")])
            return {key: visit(item) for key, item in value.items() if key != "$defs"}
        if isinstance(value, (list, tuple)):
            return [visit(item) for item in value]
        return value

    return cast(JsonObject, visit(schema))


def _reject(
    wire: TransportWire, code: str, correlation: str, *, location: tuple[str | int, ...] = ()
) -> Response:
    recovery = (
        RecoveryDisposition.RETRY if code == "unavailable" else RecoveryDisposition.CORRECT_REQUEST
    )
    return _result(
        wire,
        Rejection(
            correlation,
            Diagnostic(
                OperationKey("craftreport.invoke", "1"), "transport", code, recovery, location
            ),
        ),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WireFailure("invalid_input")
        result[key] = value
    return result


def _nonfinite(value: str) -> object:
    raise WireFailure("invalid_input")


async def _body(request: Request, maximum: int) -> JsonObject:
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > maximum:
            raise WireFailure("limit_exceeded", limit="max_raw_bytes")
        content.extend(chunk)
    try:
        value: object = json.loads(
            content.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_nonfinite
        )
        if not isinstance(value, dict):
            raise WireFailure("invalid_input")
        return cast(JsonObject, value)
    except (ValueError, UnicodeError, RecursionError):
        raise WireFailure("invalid_input") from None


def _correlation(value: JsonObject, fallback: str) -> str:
    supplied = value.get("correlation_id")
    if not isinstance(supplied, str) or not supplied.strip():
        return fallback
    try:
        supplied.encode("utf-8")
        return supplied
    except UnicodeError:
        return fallback


@dataclass(frozen=True, slots=True)
class _Rest:
    facade: Facade
    principal: PrincipalBoundary
    readiness: Callable[[], bool]
    deployment_epoch: str
    max_raw_bytes: int
    wire: TransportWire

    async def ready(self, request: Request) -> Response:
        try:
            ready = self.readiness()
        except Exception:
            ready = False
        return _response(
            self.wire,
            {"ready": ready, "deployment_epoch": self.deployment_epoch},
            200 if ready else 503,
        )

    async def catalog(self, request: Request) -> Response:
        correlation = str(uuid4())
        try:
            principal = await self.principal.resolve(request)
            catalog = self.wire.encode_catalog(await self.facade.catalog(principal))
            return _response(
                self.wire, {**catalog, "transport_limits": {"max_raw_bytes": self.max_raw_bytes}}
            )
        except AuthenticationRejected:
            return _reject(self.wire, "unauthenticated", correlation)
        except CatalogRejected as error:
            return _result(self.wire, error.rejection)
        except Exception:
            return _reject(self.wire, "unavailable", correlation)

    async def invoke(self, request: Request) -> Response:
        correlation = str(uuid4())
        try:
            principal = await self.principal.resolve(request)
            value = await _body(request, self.max_raw_bytes)
            correlation = _correlation(value, correlation)
            # Raw framing bounds parsing. Descriptor limits in shared guards remain
            # authoritative; the ingress decoder must not impose default lower caps.
            limits = OperationLimits(self.max_raw_bytes, self.max_raw_bytes, self.max_raw_bytes)
            envelope = self.wire.decode_envelope(value, limits)
        except AuthenticationRejected:
            return _reject(self.wire, "unauthenticated", correlation)
        except WireFailure as error:
            location = (error.limit,) if error.limit else error.location
            return _reject(self.wire, error.code, correlation, location=location)
        except Exception:
            return _reject(self.wire, "unavailable", correlation)
        try:
            return _result(self.wire, await self.facade.invoke(principal, envelope))
        except Exception:
            return _reject(self.wire, "unavailable", correlation)

    async def read_result(self, request: Request) -> Response:
        correlation = str(uuid4())
        try:
            principal = await self.principal.resolve(request)
            value = await self.facade.read_result(principal, request.path_params["operation_id"])
            return _response(
                self.wire,
                self.wire.encode_result_readback(value),
                self.wire.canonical_status(value),
            )
        except AuthenticationRejected:
            return _reject(self.wire, "unauthenticated", correlation)
        except Exception:
            return _reject(self.wire, "unavailable", correlation)

    async def inspect(self, request: Request) -> Response:
        correlation = str(uuid4())
        try:
            principal = await self.principal.resolve(request)
            return _result(
                self.wire, await self.facade.inspect(principal, request.path_params["operation_id"])
            )
        except AuthenticationRejected:
            return _reject(self.wire, "unauthenticated", correlation)
        except Exception:
            return _reject(self.wire, "unavailable", correlation)


def rest_router(
    facade: Facade,
    principal: PrincipalBoundary,
    readiness: Callable[[], bool],
    deployment_epoch: str,
    wire: TransportWire,
    *,
    max_raw_bytes: int = 1_048_576,
) -> APIRouter:
    """Expose the shared facade; host bind checks and lifespan belong to composition.

    max_raw_bytes bounds transport framing, independently of advertised per-operation
    decoded input/depth/output limits, which the shared dispatcher enforces.
    """
    require_text(deployment_epoch, "deployment_epoch")
    require_positive(max_raw_bytes, "max_raw_bytes")
    adapter = _Rest(facade, principal, readiness, deployment_epoch, max_raw_bytes, wire)
    router = APIRouter()
    router.add_api_route("/health/ready", adapter.ready, methods=["GET"])
    router.add_api_route("/v1/catalog", adapter.catalog, methods=["GET"])
    router.add_api_route("/v1/operations/{operation_id}", adapter.inspect, methods=["GET"])
    router.add_api_route(
        "/v1/operations/{operation_id}/result",
        adapter.read_result,
        methods=["GET"],
        openapi_extra={
            "responses": {
                "200": {
                    "description": "Authorized retained result and current receipt",
                    "content": {
                        "application/json": {
                            "schema": _inline_schema(wire.result_readback_schema())
                        }
                    },
                }
            }
        },
    )
    router.add_api_route(
        "/v1/invoke",
        adapter.invoke,
        methods=["POST"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": _inline_schema(wire.envelope_schema())}},
            },
            "responses": {
                str(status): {
                    "description": "Canonical invocation outcome",
                    "content": {
                        "application/json": {
                            "schema": _inline_schema(wire.invocation_result_schema())
                        }
                    },
                }
                for status in (200, 202, 401, 403, 404, 409, 413, 422, 429, 503)
            },
        },
    )
    return router
