"""Production asset boundaries preserve exact values and reject extensions."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest
from pydantic import ValidationError
from test_prepare import definition as definition
from test_themes import theme as theme

from craftreport.adapters import report_codecs as c
from craftreport.adapters.canonical import WireFailure
from craftreport.contracts.values import JsonObject
from craftreport.data.values import Scalar
from craftreport.reporting import definitions as d
from craftreport.themes.values import Theme


def raw(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode()


@pytest.mark.parametrize(
    "value,kind",
    [
        (2**63 - 1, "int64"),
        (-(2**63), "int64"),
        (Decimal("12345678901234567890.1234567800"), "decimal"),
        (date(2026, 1, 3), "date"),
        (datetime(2026, 1, 3, tzinfo=UTC), "datetime"),
        (True, "bool"),
        ("=literal + @text", "text"),
    ],
)
def test_exact_parameters(definition: d.ReportDefinition, value: Scalar, kind: str) -> None:
    from craftreport.data.values import ScalarKind

    parameter = d.ParameterDefinition("exact", cast(ScalarKind, kind), False, value)
    expected = replace(definition, parameters=(*definition.parameters, parameter))
    encoded = c.encode_definition(expected)
    decoded = c.decode_definition(encoded)
    assert decoded == expected
    assert type(decoded.parameters[-1].default) is type(value)
    if isinstance(value, Decimal):
        assert str(decoded.parameters[-1].default) == str(value)


def test_nested_unknowns_and_constructors(definition: d.ReportDefinition) -> None:
    for path in [
        (),
        ("table",),
        ("table", "source"),
        ("table", "source", "fields", 0),
        ("table", "columns", 0, "format"),
        ("chart", "series", 0),
        ("release_policy",),
        ("parameters", 0),
        ("parameters", 0, "default"),
    ]:
        content = json.loads(c.encode_definition(definition))
        node = content
        for key in path:
            node = node[key]
        node["execute"] = "private sentinel"
        with pytest.raises(WireFailure, match="invalid_asset") as failure:
            c.decode_definition(raw(content))
        assert "sentinel" not in str(failure.value)
    content = json.loads(c.encode_definition(definition))
    content["table"]["columns"][0]["field"] = "missing"
    with pytest.raises(WireFailure):
        c.decode_definition(raw(content))


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "int64", "value": 9223372036854775807},
        {"kind": "decimal", "value": 1.5},
        {"kind": "bool", "value": "true"},
        {"kind": "date", "value": "2026-99-99"},
        {"kind": "null", "value": None},
    ],
)
def test_wrong_tags(definition: d.ReportDefinition, payload: JsonObject) -> None:
    content = json.loads(c.encode_definition(definition))
    content["parameters"][0]["default"] = payload
    with pytest.raises(WireFailure):
        c.decode_definition(raw(content))


def test_default_normalization_and_semantic_identity(definition: d.ReportDefinition) -> None:
    from craftreport.reporting.prepare import resolve_parameters

    content = json.loads(c.encode_definition(definition))
    parameter = content["parameters"][0]
    assert "minimum" not in parameter and "maximum" not in parameter
    parameter.pop("choices")
    decoded = c.decode_definition(raw(content))
    assert decoded == definition
    assert c.definition_identifier(decoded) == c.definition_identifier(definition)
    assert c.definition_identifier(replace(definition, title="changed")) != c.definition_identifier(
        definition
    )
    parameter.pop("default")
    absent = c.decode_definition(raw(content))
    assert absent.parameters[0].default is None
    with pytest.raises(d.DefinitionError):
        resolve_parameters(absent, ())
    parameter["default"] = None
    with pytest.raises(WireFailure):
        c.decode_definition(raw(content))
    parameter["default"] = {"kind": "null", "value": None}
    with pytest.raises(WireFailure):
        c.decode_definition(raw(content))


@pytest.mark.parametrize(
    "change",
    [
        {"choices": [{"kind": "null", "value": None}]},
        {"minimum": {"kind": "decimal", "value": "1.0"}},
        {"default": {"kind": "text", "value": "x"}, "choices": [{"kind": "text", "value": "y"}]},
    ],
)
def test_parameter_semantic_failures(definition: d.ReportDefinition, change: JsonObject) -> None:
    content = json.loads(c.encode_definition(definition))
    content["parameters"][0].update(change)
    with pytest.raises(WireFailure):
        c.decode_definition(raw(content))


def test_theme_json_library_policy_and_self_pin(theme: Theme) -> None:
    pinned = replace(
        theme, version_pin=replace(theme.version_pin, content_digest=c.theme_identifier(theme))
    )
    encoded = c.encode_theme(pinned)
    assert c.decode_theme(encoded) == pinned
    assert c.theme_identifier(
        replace(pinned, version_pin=replace(pinned.version_pin, version="2"))
    ) != c.theme_identifier(pinned)
    assert c.theme_identifier(
        replace(pinned, version_pin=replace(pinned.version_pin, content_digest="f" * 64))
    ) == c.theme_identifier(pinned)
    content = json.loads(encoded)
    assert isinstance(content["styles"], list)
    content["styles"][0][1]["size_pt"] = 12
    with pytest.raises(WireFailure):
        c.decode_theme(raw(content))
    for value in [True, "12", 0, 145]:
        content["styles"][0][1]["size_pt"] = value
        with pytest.raises(ValidationError):
            c.THEME.validate_json(raw(content), strict=True, extra="forbid")
        with pytest.raises(WireFailure):
            c.decode_theme(raw(content))
    for value in [12, 12.0]:
        content["styles"][0][1]["size_pt"] = value
        normalized = c.THEME.validate_json(raw(content), strict=True, extra="forbid")
        assert type(normalized.styles[0][1].size_pt) is float
        normalized = replace(
            normalized,
            version_pin=replace(
                normalized.version_pin, content_digest=c.theme_identifier(normalized)
            ),
        )
        assert c.decode_theme(c.encode_theme(normalized)) == normalized
    for path in [(), ("version_pin",), ("styles", 0, 1), ("formats", 0), ("chart",), ("grid",)]:
        content = json.loads(encoded)
        node = content
        for key in path:
            node = node[key]
        node["execute"] = "sentinel"
        with pytest.raises(WireFailure):
            c.decode_theme(raw(content))


def test_recursive_schema_closure() -> None:
    def check(value: object) -> None:
        if isinstance(value, dict):
            node = cast(dict[str, object], value)
            for key, child in node.items():
                if key == "type" and child == "object":
                    assert node.get("additionalProperties") is False
                check(child)
        elif isinstance(value, list):
            for child in cast(list[object], value):
                check(child)

    for name in ("definition", "theme", "manifest"):
        check(c.asset_schema(name))
    parameter_schema = json.loads(json.dumps(c.asset_schema("definition")))["$defs"][
        "ParameterDeclarationWire"
    ]
    assert "default" not in parameter_schema["properties"]["default"]
    assert "anyOf" not in parameter_schema["properties"]["default"]


def test_bounds(definition: d.ReportDefinition) -> None:
    for payload in (
        b" " * 65537,
        b'{"x":' * 33 + b"0" + b"}" * 33,
        b'{"schema_version":"1","schema_version":"1"}',
    ):
        with pytest.raises(WireFailure):
            c.decode_definition(payload)
    oversized = d.ParameterDefinition("large", "text", False, choices=("x" * 100,) * 1000)
    with pytest.raises(WireFailure):
        c.encode_definition(replace(definition, parameters=(*definition.parameters, oversized)))
