"""Versioned Python-service canonical wire profile (not RFC canonical JSON)."""

import hashlib
import json
import math
from collections.abc import Mapping

from craftreport.application.dispatch_ports import WireFailure as WireFailure
from craftreport.contracts import ExpectedVersion, JsonObject, OperationKey, ResourceRef
from craftreport.contracts.values import JsonValue

NORMALIZATION_POLICY = "craftreport-json-v1"
MAX_SAFE_INTEGER = 2**53 - 1


def wire_value(value: JsonValue, max_depth: int | None = 32, depth: int = 0) -> JsonValue:
    if isinstance(value, (Mapping, list, tuple)):
        if max_depth is not None and depth >= max_depth:
            raise WireFailure("limit_exceeded", limit="max_nesting_depth")
        if isinstance(value, Mapping):
            if any(type(key) is not str for key in value):
                raise WireFailure("invalid_input")
            return {key: wire_value(item, max_depth, depth + 1) for key, item in value.items()}
        return [wire_value(item, max_depth, depth + 1) for item in value]
    if type(value) is int and abs(value) > MAX_SAFE_INTEGER:
        raise WireFailure("invalid_input")
    if type(value) is float and not math.isfinite(value):
        raise WireFailure("invalid_input")
    if value is not None and type(value) not in (bool, int, float, str):
        raise WireFailure("invalid_input")
    return value


def canonical_bytes(value: JsonObject, max_depth: int | None = 32) -> bytes:
    try:
        normalized = wire_value(value, max_depth)
        return json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (UnicodeError, TypeError, ValueError) as error:
        if isinstance(error, WireFailure):
            raise
        raise WireFailure("invalid_input") from None


def bounded_object(value: JsonObject, max_bytes: int, max_depth: int = 32) -> JsonObject:
    if len(canonical_bytes(value, max_depth)) > max_bytes:
        raise WireFailure("limit_exceeded", limit="max_input_bytes")
    normalized = wire_value(value, max_depth)
    if not isinstance(normalized, Mapping):
        raise WireFailure("invalid_input")
    return normalized


def fingerprint(
    operation: OperationKey,
    normalized_payload: JsonObject,
    resources: tuple[ResourceRef, ...],
    expected_versions: tuple[ExpectedVersion, ...],
    *,
    policy: str = NORMALIZATION_POLICY,
) -> str:
    if policy != NORMALIZATION_POLICY:
        raise ValueError("Unsupported normalization policy")
    content: JsonObject = {
        "normalization_policy": policy,
        "operation": operation.name,
        "contract_version": operation.contract_version,
        "payload": normalized_payload,
        "resources": [{"kind": ref.kind, "identity": ref.identity} for ref in resources],
        "expected_versions": [
            {
                "resource": {"kind": pin.resource.kind, "identity": pin.resource.identity},
                "version": pin.version,
            }
            for pin in expected_versions
        ],
    }
    # Payloads are already validated and normalized, including contract defaults.
    # The hashing wrapper must not impose a second depth budget on that content.
    return hashlib.sha256(canonical_bytes(content, max_depth=None)).hexdigest()
