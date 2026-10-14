"""Payload embedding preserves schema resources and instance-valued annotations."""

from collections.abc import Mapping
from typing import Protocol, cast

import pytest
from jsonschema import Draft202012Validator

from craftreport.adapters.canonical import wire_value
from craftreport.adapters.schema_embedding import embed_payload_schema
from craftreport.adapters.transport_wire import envelope_schema
from craftreport.contracts import OperationKey
from craftreport.contracts.values import JsonObject, freeze_object


class _SchemaValidator(Protocol):
    def is_valid(self, instance: JsonObject) -> bool: ...


def test_recursive_local_references_are_embedded_without_mutation() -> None:
    schema: JsonObject = {
        "$defs": {"Node": {"properties": {"next": {"$ref": "#/$defs/Node"}}}},
        "properties": {"root": {"$ref": "#"}, "node": {"$ref": "#/$defs/Node"}},
    }
    expected: JsonObject = {
        "$defs": {"Node": {"properties": {"next": {"$ref": "#/properties/payload/$defs/Node"}}}},
        "properties": {
            "root": {"$ref": "#/properties/payload"},
            "node": {"$ref": "#/properties/payload/$defs/Node"},
        },
    }
    snapshot = freeze_object(schema)
    assert embed_payload_schema(schema) == expected
    assert freeze_object(schema) == snapshot
    assert embed_payload_schema(snapshot) == expected


@pytest.mark.parametrize("keyword", ["const", "default", "examples", "enum", "x-custom"])
def test_instance_data_is_copied_without_rewriting(keyword: str) -> None:
    literal = {"$ref": "#/$defs/X", "$id": "literal", "properties": {"$ref": "#"}}
    schema: JsonObject = {keyword: literal, "properties": {"$ref": {"$ref": "#"}}}
    result = embed_payload_schema(schema)
    assert result[keyword] == literal
    assert result[keyword] is not literal
    assert result["properties"] == {"$ref": {"$ref": "#/properties/payload"}}


@pytest.mark.parametrize("identity", ["https://example.test/schema", "child.json"])
def test_explicit_resource_scopes_keep_local_references(identity: str) -> None:
    child: JsonObject = {"$id": identity, "$ref": "#/$defs/X", "$defs": {"X": {"$ref": "#"}}}
    assert embed_payload_schema(child) == child
    result = embed_payload_schema({"$defs": {"Child": child}, "$ref": "#/$defs/Child"})
    assert result == {"$defs": {"Child": child}, "$ref": "#/properties/payload/$defs/Child"}


@pytest.mark.parametrize("keyword", ["$ref", "$dynamicRef", "$recursiveRef"])
def test_reference_forms_preserve_external_and_named_anchors(keyword: str) -> None:
    for reference in ["other.json#/$defs/X", "https://example.test/schema", "#node"]:
        assert embed_payload_schema({keyword: reference}) == {keyword: reference}
    assert embed_payload_schema({keyword: "#"}) == {keyword: "#/properties/payload"}


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf", "prefixItems", "items"])
def test_schema_arrays_and_frozen_sequences(keyword: str) -> None:
    schema = freeze_object({keyword: [{"$ref": "#"}, False]})
    assert embed_payload_schema(schema) == {keyword: [{"$ref": "#/properties/payload"}, False]}


@pytest.mark.parametrize(
    "keyword", ["not", "if", "then", "else", "contains", "additionalProperties"]
)
def test_single_schema_positions(keyword: str) -> None:
    assert embed_payload_schema({keyword: {"$ref": "#"}}) == {
        keyword: {"$ref": "#/properties/payload"}
    }


def test_legacy_dependencies_keep_property_name_arrays() -> None:
    schema: JsonObject = {"dependencies": {"a": ["$ref", "#"], "b": {"$ref": "#"}}}
    result = embed_payload_schema(schema)
    assert result == {"dependencies": {"a": ["$ref", "#"], "b": {"$ref": "#/properties/payload"}}}
    assert isinstance(result, Mapping)


def test_actual_envelope_resolves_recursive_payload_and_keeps_definition_scopes() -> None:
    payload: JsonObject = {
        "type": "object",
        "properties": {
            "value": {"$ref": "#/$defs/ResourceWire"},
            "children": {"type": "array", "items": {"$ref": "#"}},
        },
        "required": ["value"],
        "$defs": {"ResourceWire": {"type": "integer"}},
        "additionalProperties": False,
    }
    snapshot = freeze_object(payload)
    key = OperationKey("probe.schema", "1")
    original_envelope = envelope_schema(key)
    embedded = envelope_schema(key, payload)
    schema = wire_value(embedded, max_depth=None)
    assert isinstance(schema, Mapping)
    Draft202012Validator.check_schema(schema)
    validator = cast(_SchemaValidator, Draft202012Validator(schema))
    instance: JsonObject = {
        "operation": "probe.schema",
        "contract_version": "1",
        "correlation_id": "test",
        "payload": {"value": 1, "children": [{"value": 2, "children": [{"value": 3}]}]},
        "expected_versions": [{"resource": {"kind": "report", "identity": "one"}, "version": "1"}],
    }
    assert validator.is_valid(instance)
    assert not validator.is_valid({**instance, "payload": {"value": "wrong"}})
    assert not validator.is_valid(
        {**instance, "payload": {"value": 1, "children": [{"value": "wrong"}]}}
    )
    assert not validator.is_valid(
        {**instance, "expected_versions": [{"resource": 1, "version": "1"}]}
    )
    assert embedded["$defs"] == original_envelope["$defs"]
    assert freeze_object(payload) == snapshot
    assert envelope_schema(key, snapshot) == embedded
    assert envelope_schema(key) == original_envelope
