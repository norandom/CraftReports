"""Typed JSON, safe CLI output and inspection-only completion handling."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

JsonObject = dict[str, JsonValue]
Execute = Callable[[str, JsonObject], Awaitable[JsonObject]]
JSON_OBJECT = TypeAdapter(JsonObject)


class Receipt(BaseModel):
    model_config = ConfigDict(strict=True)
    operation_id: str = Field(min_length=1)
    state: Literal["accepted", "pending", "complete", "partial", "ambiguous", "failed"]
    result_ref: str | None
    result_availability: Literal["available", "missing", "inaccessible", "unavailable"]


class Readback(BaseModel):
    model_config = ConfigDict(strict=True)
    receipt: Receipt
    value: JsonObject


class ExampleFailure(Exception):
    def __init__(self, message: str, response: JsonObject | None = None) -> None:
        super().__init__(message)
        self.response = response


def configuration() -> tuple[str, str]:
    url = os.environ.get("CRAFTREPORT_URL", "").rstrip("/")
    token = os.environ.get("CRAFTREPORT_TOKEN", "")
    if not url or not token:
        raise ExampleFailure("Set CRAFTREPORT_URL and CRAFTREPORT_TOKEN in the environment")
    return url, token


def parse_object(content: str | bytes) -> JsonObject:
    return JSON_OBJECT.validate_json(content)


def require_operation(catalog: JsonObject, request: JsonObject) -> None:
    operations = catalog.get("operations")
    if not isinstance(operations, list):
        raise ExampleFailure("Catalog has no operation descriptors", catalog)
    expected = {
        "name": request.get("operation"),
        "contract_version": request.get("contract_version"),
    }
    if not any(isinstance(item, dict) and item.get("key") == expected for item in operations):
        raise ExampleFailure("Requested exact operation/version is not in the authorized catalog")


def receipt_from(response: JsonObject) -> Receipt:
    if "diagnostic" in response:
        raise ExampleFailure(
            "Server rejected the request; inspect diagnostic and recovery", response
        )
    return Receipt.model_validate(response)


async def complete(
    response: JsonObject, execute: Execute, *, attempts: int = 20, interval: float = 0.25
) -> JsonObject:
    original_id = receipt_from(response).operation_id
    for _ in range(attempts):
        receipt = receipt_from(response)
        if receipt.operation_id != original_id:
            raise ExampleFailure("Inspection returned a different operation identity", response)
        if receipt.state not in {"accepted", "pending"}:
            break
        await asyncio.sleep(interval)
        response = await execute("inspect", {"operation_id": original_id})
    receipt = receipt_from(response)
    if receipt.operation_id != original_id:
        raise ExampleFailure("Inspection returned a different operation identity", response)
    if receipt.state != "complete":
        raise ExampleFailure(
            "Operation is not complete; inspect retained state before recovery", response
        )
    if not receipt.result_ref or receipt.result_availability != "available":
        raise ExampleFailure("Complete receipt has no available retained result", response)
    return response


async def workflow(
    execute: Execute, request: JsonObject | None, identity: str | None
) -> JsonObject:
    if request is not None:
        return await complete(await execute("invoke", request), execute)
    assert identity is not None
    inspected = await complete(await execute("inspect", {"operation_id": identity}), execute)
    if receipt_from(inspected).operation_id != identity:
        raise ExampleFailure("Inspection returned a different operation identity", inspected)
    response = await execute("result", {"operation_id": identity})
    if "diagnostic" in response:
        raise ExampleFailure(
            "Retained result unavailable; inspect diagnostic and recovery", response
        )
    readback = Readback.model_validate(response)
    if readback.receipt.operation_id != identity:
        raise ExampleFailure("Readback returned a different operation identity", response)
    await complete(JSON_OBJECT.validate_python(response["receipt"]), execute, attempts=0)
    return response


def emit(value: object, *, error: bool = False) -> None:
    content = json.dumps(value, indent=2, ensure_ascii=True)
    token = os.environ.get("CRAFTREPORT_TOKEN", "")
    if token:
        content = content.replace(json.dumps(token)[1:-1], "[REDACTED]")
    print(content, file=sys.stderr if error else sys.stdout)


def cli(transport: str | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Invoke or read an authorized CraftReport operation"
    )
    if transport is None:
        parser.add_argument("--operation-id", required=True)
        parser.add_argument("--transport", choices=("rest", "mcp"), required=True)
    else:
        parser.add_argument("--request", type=Path)
    args = parser.parse_args()
    try:
        configuration()
        request = parse_object(args.request.read_bytes()) if transport and args.request else None
        selected = transport or args.transport
        if selected == "rest":
            from scripts.examples.call_rest import run
        else:
            from scripts.examples.call_mcp import run
        emit(asyncio.run(run(request, None if transport else args.operation_id)))
        return 0
    except ExampleFailure as error:
        emit({"error": str(error), "response": error.response}, error=True)
    except Exception as error:
        # Do not print transport exception strings, which may contain credentials/URLs.
        emit({"error": "Client failed", "category": type(error).__name__}, error=True)
    return 1
