"""Canonical wire equality and safety, independent of any transport SDK."""

import hashlib
from dataclasses import replace
from typing import cast

import pytest

from craftreport.adapters.canonical import (
    MAX_SAFE_INTEGER,
    NORMALIZATION_POLICY,
    WireFailure,
    bounded_object,
    canonical_bytes,
    fingerprint,
)
from craftreport.contracts import ExpectedVersion, JsonObject, OperationKey, ResourceRef
from craftreport.contracts.values import JsonValue


def test_canonical_key_order_and_utf8() -> None:
    assert canonical_bytes({"z": "é", "a": [2, 1]}) == b'{"a":[2,1],"z":"\xc3\xa9"}'
    assert canonical_bytes({"z": "é", "a": [2, 1]}) == canonical_bytes({"a": [2, 1], "z": "é"})
    assert canonical_bytes({"a": [2, 1]}) != canonical_bytes({"a": [1, 2]})
    assert canonical_bytes({"a": " x "}) != canonical_bytes({"a": "x"})


@pytest.mark.parametrize(
    "value",
    [
        MAX_SAFE_INTEGER + 1,
        -MAX_SAFE_INTEGER - 1,
        float("nan"),
        float("inf"),
        float("-inf"),
        "\ud800",
    ],
)
def test_unsafe_wire_values_rejected(value: JsonValue) -> None:
    with pytest.raises(WireFailure, match="invalid_input"):
        canonical_bytes({"nested": [value]})


def test_safe_number_edges_and_boolean_distinction() -> None:
    assert canonical_bytes({"n": MAX_SAFE_INTEGER}) == b'{"n":9007199254740991}'
    assert canonical_bytes({"n": -MAX_SAFE_INTEGER}) == b'{"n":-9007199254740991}'
    assert canonical_bytes({"n": True}) != canonical_bytes({"n": 1})
    assert canonical_bytes({"n": 1.25}) == b'{"n":1.25}'


def test_non_string_keys_rejected_without_coercion() -> None:
    invalid = cast(JsonObject, cast(object, {1: "secret"}))
    with pytest.raises(WireFailure, match="invalid_input"):
        canonical_bytes(invalid)


def test_exact_bytes_and_container_depth() -> None:
    value: JsonObject = {"a": [{"b": "é"}]}
    length = len(canonical_bytes(value))
    assert bounded_object(value, length, 3) == value
    with pytest.raises(WireFailure) as size:
        bounded_object(value, length - 1, 3)
    assert size.value.limit == "max_input_bytes"
    with pytest.raises(WireFailure) as depth:
        bounded_object(value, length, 2)
    assert depth.value.limit == "max_nesting_depth"
    assert bounded_object({}, 2, 1) == {}


def test_cyclic_or_extremely_deep_input_hits_limit_before_recursion() -> None:
    items: list[JsonValue] = []
    items.append(items)
    with pytest.raises(WireFailure) as error:
        canonical_bytes({"items": items})
    assert error.value.limit == "max_nesting_depth"


def test_fingerprint_pins_operation_resources_preconditions_and_policy() -> None:
    key = OperationKey("fixture.set", "1")
    resource = ResourceRef("grid", "a")
    pin = ExpectedVersion(resource, "9007199254740992")
    payload: JsonObject = {"count": 2, "amount": "1"}
    digest = fingerprint(key, payload, (resource,), (pin,))
    expected: JsonObject = {
        "normalization_policy": NORMALIZATION_POLICY,
        "operation": "fixture.set",
        "contract_version": "1",
        "payload": payload,
        "resources": [{"kind": "grid", "identity": "a"}],
        "expected_versions": [
            {"resource": {"kind": "grid", "identity": "a"}, "version": "9007199254740992"}
        ],
    }
    assert digest == hashlib.sha256(canonical_bytes(expected)).hexdigest()
    assert digest == fingerprint(key, {"amount": "1", "count": 2}, (resource,), (pin,))
    assert digest != fingerprint(key, payload, (resource,), (replace(pin, version="2"),))
    assert digest != fingerprint(replace(key, contract_version="2"), payload, (resource,), (pin,))
    assert digest != fingerprint(OperationKey("fixture.other", "1"), payload, (resource,), (pin,))
    assert digest != fingerprint(key, payload, (ResourceRef("grid", "b"),), (pin,))
    assert digest != fingerprint(key, {"count": 3, "amount": "1"}, (resource,), (pin,))
    with pytest.raises(ValueError, match="policy"):
        fingerprint(key, payload, (), (), policy="future")
