"""Bounded production asset codecs and explicit semantic hash projections."""

import json
from dataclasses import fields
from hashlib import sha256
from typing import Literal, cast

from pydantic import TypeAdapter

from craftreport.adapters.canonical import WireFailure, bounded_object, canonical_bytes
from craftreport.adapters.report_models import (
    DefinitionWire,
    PackManifest,
    ParameterDeclarationWire,
)
from craftreport.adapters.snapshot_models import ParameterWire
from craftreport.adapters.snapshot_wire import decode_parameter, encode_parameter
from craftreport.contracts.values import JsonObject, JsonValue
from craftreport.data.values import Scalar
from craftreport.reporting.definitions import ParameterDefinition, ReportDefinition
from craftreport.themes.values import Theme

DEFINITION = TypeAdapter(DefinitionWire)
THEME = TypeAdapter(Theme)
MANIFEST = TypeAdapter(PackManifest)


def _pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate field")
    return result


def _decode[T](data: bytes, adapter: TypeAdapter[T], maximum: int) -> T:
    try:
        if len(data) > maximum:
            raise ValueError("Asset size")
        content = cast(JsonObject, json.loads(data, object_pairs_hook=_pairs))
        normalized = canonical_bytes(bounded_object(content, maximum))
        return adapter.validate_json(normalized, strict=True, extra="forbid")
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise WireFailure("invalid_asset") from None


def decode_manifest(data: bytes) -> PackManifest:
    return _decode(data, MANIFEST, 65536)


def _parameter(wire: ParameterDeclarationWire) -> ParameterDefinition:
    def scalar(value: ParameterWire | None) -> Scalar:
        if value is None:
            return None
        if value.kind != wire.kind:
            raise WireFailure("invalid_asset")
        return decode_parameter(cast(JsonObject, value.model_dump(mode="json")))

    return ParameterDefinition(
        wire.name,
        wire.kind,
        wire.required,
        scalar(wire.default),
        tuple(scalar(v) for v in wire.choices),
        scalar(wire.minimum),
        scalar(wire.maximum),
    )


def decode_definition(data: bytes) -> ReportDefinition:
    try:
        wire = _decode(data, DEFINITION, 65536)
        return ReportDefinition(
            wire.schema_version,
            wire.report_id,
            wire.version,
            wire.title,
            tuple(_parameter(p) for p in wire.parameters),
            wire.table,
            wire.chart,
            wire.release_policy,
            wire.compliance_statement,
        )
    except (ValueError, TypeError, ArithmeticError):
        raise WireFailure("invalid_asset") from None


def encode_definition(value: ReportDefinition) -> bytes:
    parameters: list[ParameterDeclarationWire] = []
    for parameter in value.parameters:
        raw: dict[str, object] = {
            "name": parameter.name,
            "kind": parameter.kind,
            "required": parameter.required,
            "choices": tuple(dict(encode_parameter(v)) for v in parameter.choices),
        }
        raw.update(
            {
                name: dict(encode_parameter(v))
                for name in ("default", "minimum", "maximum")
                if (v := cast(Scalar, getattr(parameter, name))) is not None
            }
        )
        parameters.append(ParameterDeclarationWire.model_validate(raw))
    content = {
        field.name: getattr(value, field.name)
        for field in fields(value)
        if field.name != "parameters"
    }
    wire = DefinitionWire.model_validate({**content, "parameters": tuple(parameters)})
    return canonical_bytes(
        bounded_object(cast(JsonObject, wire.model_dump(mode="json", exclude_none=True)), 65536)
    )


def definition_identifier(value: ReportDefinition) -> str:
    return sha256(encode_definition(value)).hexdigest()


def _theme_object(value: Theme) -> JsonObject:
    # JSON mode normalizes permitted integer presentation sizes to floats.
    normalized = THEME.validate_json(THEME.dump_json(value), strict=True, extra="forbid")
    return cast(JsonObject, THEME.dump_python(normalized, mode="json"))


def theme_identifier(value: Theme) -> str:
    content = dict(_theme_object(value))
    pin = dict(cast(JsonObject, content["version_pin"]))
    del pin["content_digest"]
    return sha256(canonical_bytes({**content, "version_pin": pin})).hexdigest()


def encode_theme(value: Theme) -> bytes:
    return canonical_bytes(bounded_object(_theme_object(value), 32768))


def decode_theme(data: bytes) -> Theme:
    value = _decode(data, THEME, 32768)
    if value.version_pin.content_digest != theme_identifier(value):
        raise WireFailure("invalid_asset")
    return value


def asset_schema(name: Literal["definition", "theme", "manifest"]) -> JsonObject:
    schema = {"definition": DEFINITION, "theme": THEME, "manifest": MANIFEST}[name].json_schema()

    def close(value: object) -> None:
        if isinstance(value, dict):
            node = cast(dict[str, object], value)
            if node.get("type") == "object":
                node["additionalProperties"] = False
            for child in node.values():
                close(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                close(child)

    close(schema)
    return cast(JsonObject, schema)
