"""Embed standard JSON Schema payloads without traversing instance-valued data."""

from collections.abc import Mapping
from typing import cast

from craftreport.contracts.values import JsonObject, JsonValue

_PAYLOAD_ROOT = "#/properties/payload"
_SCHEMA_MAPS = frozenset(
    {"$defs", "definitions", "properties", "patternProperties", "dependentSchemas"}
)
_SCHEMA_ARRAYS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_VALUES = frozenset(
    {
        "additionalProperties",
        "unevaluatedProperties",
        "propertyNames",
        "contains",
        "additionalItems",
        "unevaluatedItems",
        "not",
        "if",
        "then",
        "else",
        "contentSchema",
    }
)


def _copy(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


def _reference(value: JsonValue, scoped: bool) -> JsonValue:
    if not scoped and isinstance(value, str):
        if value == "#":
            return _PAYLOAD_ROOT
        if value.startswith("#/"):
            return _PAYLOAD_ROOT + value[1:]
    return _copy(value)


def _children(value: JsonValue, scoped: bool) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _schema(item, scoped) for key, item in value.items()}
    return _copy(value)


def _sequence(value: JsonValue, scoped: bool) -> JsonValue:
    if isinstance(value, (list, tuple)):
        return [_schema(item, scoped) for item in value]
    return _schema(value, scoped)


def _keyword(key: str, value: JsonValue, scoped: bool) -> JsonValue:
    if key in {"$ref", "$dynamicRef", "$recursiveRef"}:
        return _reference(value, scoped)
    if key in _SCHEMA_MAPS or key == "dependencies":
        return _children(value, scoped)
    if key in _SCHEMA_ARRAYS or key == "items":
        return _sequence(value, scoped)
    if key in _SCHEMA_VALUES:
        return _schema(value, scoped)
    return _copy(value)


def _schema(value: JsonValue, scoped: bool) -> JsonValue:
    if not isinstance(value, Mapping):
        return _copy(value)
    identity = value.get("$id")
    scoped = scoped or (isinstance(identity, str) and bool(identity))
    return {key: _keyword(key, item, scoped) for key, item in value.items()}


def embed_payload_schema(schema: JsonObject) -> JsonObject:
    """Copy a payload schema for envelope.properties.payload.

    Rebase document-local JSON pointers outside explicit $id resources. Named
    anchors and external references remain intact. Standard schema keywords
    through draft 2020-12 are traversed; custom vocabulary values are opaque.
    """
    result = _schema(schema, False)
    assert isinstance(result, Mapping)
    return result


def close_schema(schema: JsonObject) -> JsonObject:
    """Declare runtime extra-field rejection on borrowed dataclass schemas."""
    result = cast(dict[str, JsonValue], _copy(schema))

    def close(value: JsonValue) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["additionalProperties"] = False
            for child in value.values():
                close(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                close(child)

    close(result)
    return result
