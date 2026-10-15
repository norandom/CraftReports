"""Exact public preparation values and unchanged upstream wire contracts."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from test_prepare import compile_report
from test_prepare import definition as definition
from test_prepare import pack as pack
from test_prepare import snapshot as snapshot
from test_quality_evaluation import PREPARATION, _source_scope, observation  # pyright: ignore[reportPrivateUsage]
from test_themes import support as support
from test_themes import theme as theme

from craftreport.adapters import report_codecs as c
from craftreport.adapters import report_models as m
from craftreport.adapters import snapshot_models as s
from craftreport.adapters.canonical import WireFailure
from craftreport.adapters.snapshot_wire import finalize_snapshot, publication_codec, snapshot_codec
from craftreport.composition.reporting import is_compatible
from craftreport.contracts.identity import (
    CapabilityRequirement,
    CapabilityVersion,
    ExpectedVersion,
    OperationKey,
    ResourceRef,
)
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.values import JsonObject, JsonValue
from craftreport.data.requirements import FieldRequirement
from craftreport.data.values import Snapshot
from craftreport.policies.evaluate import evaluate
from craftreport.policies.values import (
    CheckId,
    ExternalStatement,
    ReleasePolicy,
)
from craftreport.reporting import definitions as d
from craftreport.reporting import ports as p
from craftreport.reporting.prepare import prepare, requirements_for
from craftreport.reporting.prepared import PreparedReport, ResolvedPack
from craftreport.themes.resolve import CapabilityStatus, ThemeFailure, resolve_theme
from craftreport.themes.values import ResolvedTheme, SemanticRole, StyleOverride, Theme, ValueFormat


def test_old_schemas_and_asset_bytes(definition: d.ReportDefinition) -> None:
    baseline = json.loads(Path(__file__).with_name("wire_schema_baseline.json").read_text())
    for cls in (
        s.FieldWire,
        s.DatasetWire,
        s.MetricWire,
        s.PublicationWire,
        s.SnapshotWire,
        m.DefinitionWire,
    ):
        assert cls.model_json_schema() == baseline[cls.__name__]
    assert c.encode_definition(definition).decode() == baseline["definition_bytes"]


def compiled(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> PreparedReport:
    original = compile_report(definition, snapshot, pack)
    return replace(original, content_digest=c.prepared_identifier(original))


def test_prepared_exact_roundtrip_and_digest(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    value = compiled(definition, snapshot, pack)
    codec = c.prepared_codec()
    wire = codec.encode(value)
    assert codec.decode(wire) == value
    assert (
        c.prepared_identifier(value)
        == sha256(
            json.dumps(
                {k: v for k, v in wire.items() if k != "content_digest"},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                default=dict,
            ).encode()
        ).hexdigest()
    )
    changed = dict(wire)
    changed["content_digest"] = "f" * 64
    with pytest.raises(WireFailure):
        codec.decode(changed)
    changed = dict(wire)
    changed["_identify"] = None
    with pytest.raises(WireFailure):
        codec.decode(changed)


def test_requests_and_result_scopes(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    value = compiled(definition, snapshot, pack)
    selection = p.PackSelection("public", "example", "1")
    request = p.PrepareRequest(pack=selection, definition=definition, snapshot=value.snapshot)
    codec = c.preparation_request_codec()
    assert codec.decode(codec.encode(request)) == request
    assert codec.limits.max_input_bytes == 65536 and codec.limits.max_output_bytes == 65536
    validation = p.ValidationResult(
        requirements_for(definition, value.resolved_parameters),
        value.resolved_parameters,
        value.definition,
        value.template,
        value.theme,
        value.pack,
        value.required_capabilities,
    )
    validation_codec = c.validation_result_codec()
    assert validation_codec.decode(validation_codec.encode(validation)) == validation
    assert c.requirements_schema()["additionalProperties"] is False
    assert c.pack_summary_schema()["additionalProperties"] is False
    original = _source_scope()
    target = ExpectedVersion(ResourceRef("document", "doc:one"), "2")
    current = replace(
        original, resource_versions=(*original.resource_versions, target), target=target
    )
    quality = evaluate(
        current,
        ReleasePolicy((), "Only preparation"),
        (
            *tuple(observation(original, k) for k in PREPARATION),
            observation(current, CheckId.LAYOUT_FIT),
        ),
        preparation_scope=original,
    )
    result = p.PreparationResult(value, quality)
    result_codec = c.preparation_result_codec()
    assert result_codec.decode(result_codec.encode(result)) == result
    assert all(f.scope == original for f in quality.findings[:3])
    assert quality.findings[3].scope == current
    assert result_codec.limits.max_output_bytes == 8388608
    assert c.validation_scope_identifier(value.release_policy) != c.validation_scope_identifier(
        replace(value.release_policy, scope_label="Changed")
    )
    assert c.validation_scope_identifier(value.release_policy) != c.validation_scope_identifier(
        replace(value.release_policy, required_checks=value.release_policy.required_checks[::-1])
    )


def test_input_rejections(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    value = compiled(definition, snapshot, pack)
    request = p.PrepareRequest(
        pack=p.PackSelection("public", "example", "1"), snapshot=value.snapshot
    )
    codec = c.preparation_request_codec()
    wire = dict(codec.encode(request))
    wire["execute"] = "forbidden"
    with pytest.raises(WireFailure):
        codec.decode(wire)
    oversized = {"padding": "x" * 65536}
    with pytest.raises(WireFailure) as error:
        codec.decode(oversized)
    assert error.value.limit == "max_input_bytes"
    nested: object = "leaf"
    for _ in range(33):
        nested = [nested]
    with pytest.raises(WireFailure) as error:
        codec.decode(cast(JsonObject, {"nested": nested}))
    assert error.value.limit == "max_nesting_depth"
    for version in (2**63 - 1, "latest", "0"):
        wire = dict(codec.encode(request))
        wire["snapshot"] = {**cast(JsonObject, wire["snapshot"]), "producer_version": version}
        with pytest.raises(WireFailure):
            codec.decode(wire)
    wire = dict(codec.encode(request))
    wire["parameters"] = [{"name": "x", "value": {"kind": "text", "value": "界" * 200}}]
    with pytest.raises(WireFailure):
        codec.decode(wire)


@pytest.mark.parametrize("preparation", (False, True))
def test_supplied_null_rejects_but_nonnull_and_resolved_null_roundtrip(
    preparation: bool, definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    codec = c.preparation_request_codec() if preparation else c.validation_request_codec()
    wire: JsonObject = {
        "pack": {"namespace": "public", "name": "example", "version": "1"},
        "parameters": [{"name": "title", "value": {"kind": "null", "value": None}}],
    }
    if preparation:
        wire["snapshot"] = {"feed_id": "feed", "producer_version": "1", "content_digest": "a" * 64}
    with pytest.raises(WireFailure):
        codec.decode(wire)
    wire["parameters"] = [{"name": "title", "value": {"kind": "text", "value": "=literal"}}]
    assert codec.decode(wire).parameters == (d.ParameterValue("title", "=literal"),)
    value = compiled(definition, snapshot, pack)
    result = p.ValidationResult(
        requirements_for(definition, value.resolved_parameters),
        (*value.resolved_parameters, ("absent", None)),
        value.definition,
        value.template,
        value.theme,
        value.pack,
        value.required_capabilities,
    )
    result_codec = c.validation_result_codec()
    assert result_codec.decode(result_codec.encode(result)) == result


def test_discovery_and_closed_schemas() -> None:
    request = c.discovery_request_codec()
    assert request.decode({}) == p.EmptyRequest()
    with pytest.raises(WireFailure):
        request.decode({"root": "private"})
    codec = c.discovery_result_codec()
    value = p.DiscoveryResult((p.PackSummary("public/example", "1", "Public", "public"),))
    assert codec.decode(codec.encode(value)) == value
    for factory in (
        c.prepared_codec,
        c.quality_codec,
        c.validation_request_codec,
        c.validation_result_codec,
        c.discovery_request_codec,
        c.discovery_result_codec,
        c.preparation_request_codec,
        c.preparation_result_codec,
    ):
        schema = json.loads(json.dumps(factory().schema(), default=dict))

        def walk(node: object) -> None:
            if isinstance(node, dict):
                fields = cast(dict[str, object], node)
                if fields.get("type") == "object":
                    assert fields["additionalProperties"] is False
                for child in fields.values():
                    walk(child)
            elif isinstance(node, list):
                for child in cast(list[object], node):
                    walk(child)

        walk(schema)
        assert "_identify" not in json.dumps(schema)


def test_presentation_and_support_boundaries(
    support: tuple[CapabilityStatus, ...], theme: Theme
) -> None:
    request = p.ValidateRequest(
        pack=p.PackSelection("public", "example", "1"),
        target_support=support,
        overrides=(StyleOverride(SemanticRole.INPUT, "size_pt", 12),),
    )
    codec = c.validation_request_codec()
    wire = codec.encode(request)
    assert type(codec.decode(wire).overrides[0].value) is float
    for value in (True, "12"):
        changed = json.loads(json.dumps(wire, default=dict))
        changed["overrides"][0]["value"] = value
        with pytest.raises(WireFailure):
            codec.decode(changed)
    changed = json.loads(json.dumps(wire, default=dict))
    changed["target_support"][0]["release"]["version"] = "other"
    with pytest.raises(WireFailure):
        codec.decode(changed)
    changed = json.loads(json.dumps(wire, default=dict))
    changed["target_support"][0]["properties"][0][0] = "execute"
    with pytest.raises(WireFailure):
        codec.decode(changed)
    malformed = (
        replace(support[0], capability=CapabilityVersion(support[0].capability.identity, "broken")),
        *support[1:],
    )
    normalized = codec.decode(codec.encode(replace(request, target_support=malformed)))
    failure = resolve_theme(theme, (), normalized.target_support, is_compatible=is_compatible)
    assert isinstance(failure, ThemeFailure) and failure.code == "incompatible_version"
    assert not is_compatible(
        CapabilityVersion("report.table", "1"), CapabilityRequirement("report.table", "broken")
    )


def test_exact_parameter_kinds_and_nested_constructor_rejections(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    original = compiled(definition, snapshot, pack)
    values = (
        ("date", date(2026, 1, 2)),
        ("datetime", datetime(2026, 1, 2, tzinfo=UTC)),
        ("bool", True),
        ("int64", -(2**63)),
        ("decimal", Decimal("1.23000000")),
        ("text", "=literal"),
        ("null", None),
    )
    value = replace(
        original, resolved_parameters=values, content_digest="", _identify=c.prepared_identifier
    )
    codec = c.prepared_codec()
    assert codec.decode(codec.encode(value)) == value
    for path, bad in (("rows", True), ("presentation", "12"), ("extra", "secret")):
        wire = json.loads(json.dumps(codec.encode(value), default=dict))
        if path == "rows":
            wire["tables"][0]["rows"][0][1] = bad
        elif path == "presentation":
            wire["presentation"]["styles"][0][1]["size_pt"] = bad
        else:
            wire["tables"][0]["columns"][0]["field"]["unknown"] = bad
        with pytest.raises(WireFailure):
            codec.decode(wire)


def maximal_snapshot() -> tuple[Snapshot, int]:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    best: tuple[Snapshot, int] | None = None
    for width in range(120, 160):
        raw: JsonObject = {
            "schema_version": "1",
            "feed_id": "feed",
            "producer_version": str(2**63 - 1),
            "datasets": [],
            "metrics": [
                {
                    "identity": "metric",
                    "unit": "USD",
                    "period": "2026",
                    "as_of": "2026-01-01T00:00:00Z",
                    "source_ref": "source",
                    "producer_id": "producer",
                    "method_version": "method",
                    "shape": "series",
                    "value_schema": {
                        "name": "amount",
                        "label": "L" * 4096,
                        "kind": "decimal",
                        "nullable": True,
                        "unit": "USD",
                        "precision": 38,
                        "scale": 8,
                    },
                    "labels": ['"\n界' * width + str(i) for i in range(1000)],
                    "values": [
                        "123456789012345678901234567890.12345678" if i % 2 else None
                        for i in range(1000)
                    ],
                    "external_evidence": ["supplied-" + "E" * 4000],
                }
            ],
        }
        try:
            normalized = publication_codec().decode(raw)
            value, _ = finalize_snapshot(normalized, now, now)
            encoded = snapshot_codec().encode(value)
            size = len(
                json.dumps(
                    encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=dict
                ).encode()
            )
            best = (value, size)
        except WireFailure:
            break
    assert best is not None and 1_040_000 < best[1] <= 1_048_576
    return best


def test_supported_maximum_result_independent_count(
    definition: d.ReportDefinition, pack: ResolvedPack, tmp_path: Path
) -> None:
    snapshot, source_size = maximal_snapshot()
    source = d.MetricRef("metric", "USD", ("decimal",), "series")
    parameters = (replace(definition.parameters[0], default="T" * 510),) + tuple(
        d.ParameterDefinition("p" + str(i) + "n" * 120, "text", False, "v" * 510) for i in range(15)
    )
    definition = replace(
        definition,
        parameters=parameters,
        release_policy=ReleasePolicy(tuple(CheckId), "P" * 510),
        compliance_statement=ExternalStatement(
            "C" * 31000,
            "S" * 510,
            "I" * 126,
            (EvidenceRef("supplied", "statement", "external", OperationKey("source.claim", "1")),),
        ),
        table=d.TableDefinition(
            "table",
            source,
            (
                d.ColumnSelection("label", SemanticRole.ROW_LABEL, ValueFormat("text")),
                d.ColumnSelection("value", SemanticRole.OUTPUT, ValueFormat("decimal", 8)),
            ),
        ),
        chart=d.LineChartDefinition(
            "chart",
            source,
            "label",
            (
                d.SeriesSelection(
                    "amount", "Amount", "value", SemanticRole.OUTPUT, ValueFormat("decimal", 8)
                ),
            ),
        ),
    )
    pin = replace(pack.definition_pin, content_digest=c.definition_identifier(definition))
    maximal_theme = replace(
        pack.theme,
        styles=tuple(
            (role, replace(style, font_family="F" * 126, size_pt=144.0))
            for role, style in pack.theme.styles
        ),
        chart=replace(pack.theme.chart, series_colors=("#123456",) * 32, line_width=20.0),
        grid=replace(pack.theme.grid, header_height=4096.0, column_width=4096.0),
        null_marker="N" * 126,
        empty_note="E" * 510,
        formats=tuple(
            ValueFormat(kind, date_pattern="D" * 126 if kind in ("date", "datetime") else None)
            for kind in ("text", "bool", "int64", "decimal", "date", "datetime")
        ),
    )
    maximal_theme = replace(
        maximal_theme,
        version_pin=replace(
            maximal_theme.version_pin, content_digest=c.theme_identifier(maximal_theme)
        ),
    )
    pack = replace(
        pack, definition=definition, definition_pin=pin, template=pin, theme=maximal_theme
    )
    presentation = resolve_theme(pack.theme, (), None)
    assert isinstance(presentation, ResolvedTheme)
    value = prepare(definition, (), snapshot, pack, presentation, c.prepared_identifier)
    assert isinstance(value, PreparedReport)
    scope = replace(
        _source_scope(),
        content_digest=value.content_digest,
        validation_scope_digest=c.validation_scope_identifier(value.release_policy),
    )
    base = evaluate(scope, ReleasePolicy((), "P" * 510), (), preparation_scope=scope)
    refs = tuple(
        EvidenceRef(
            "opaque-" + str(i) + "x" * 2400,
            "source-observation",
            "operation",
            OperationKey("reports.prepare", "1"),
            scope.resource_versions,
            "d" * 64,
        )
        for i in range(8)
    )
    findings = tuple(replace(f, evidence=refs, reason_code="observed") for f in base.findings)
    quality = replace(base, findings=findings)
    result = p.PreparationResult(value, quality)
    codec = c.preparation_result_codec()
    wire = codec.encode(result)
    encoded = json.dumps(
        wire, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=dict
    ).encode()
    prepared_wire = cast(JsonObject, wire["prepared"])
    sizes = {
        "source": source_size,
        "result": len(encoded),
        "tables": len(
            json.dumps(prepared_wire["tables"], ensure_ascii=False, default=dict).encode()
        ),
        "charts": len(
            json.dumps(prepared_wire["charts"], ensure_ascii=False, default=dict).encode()
        ),
        "provenance": len(
            json.dumps(
                prepared_wire["metric_provenance"], ensure_ascii=False, default=dict
            ).encode()
        ),
        "quality": len(json.dumps(wire["quality"], ensure_ascii=False, default=dict).encode()),
    }
    assert (
        len(value.metric_provenance) == 1
        and len(value.tables[0].rows) == 1000
        and len(value.charts[0].categories) == 1000
    )
    assert len(quality.findings) == 9 and all(len(f.evidence) == 8 for f in quality.findings)
    assert (
        sizes["provenance"] > 900000
        and sizes["tables"] > 900000
        and sizes["charts"] > 900000
        and sizes["quality"] > 150000
    )
    assert len(encoded) <= 6 * source_size + 524288 < 8388608
    assert codec.decode(wire) == result
    assert value.tables[0].rows[1][1] == Decimal("123456789012345678901234567890.12345678")
    assert value.metric_provenance[0].as_of == datetime(2026, 1, 1, tzinfo=UTC)
    request = p.PrepareRequest(
        pack=p.PackSelection("public", "example", "1"),
        definition=definition,
        snapshot=value.snapshot,
    )
    assert (
        len(
            json.dumps(
                c.preparation_request_codec().encode(request), ensure_ascii=False, default=dict
            ).encode()
        )
        < 65536
    )
    (tmp_path / "independent-size-count.json").write_text(json.dumps(sizes))


def test_combined_selection_maximum_and_source_display_labels(
    definition: d.ReportDefinition, pack: ResolvedPack, tmp_path: Path
) -> None:
    names = ("day", *("field" + str(i) + "n" * 118 for i in range(31)))
    fields: list[JsonValue] = [
        {
            "name": name,
            "label": "\x01" * 4096,
            "kind": "date" if i == 0 else "int64",
            "nullable": False,
        }
        for i, name in enumerate(names)
    ]
    raw: JsonObject = {
        "schema_version": "1",
        "feed_id": "feed",
        "producer_version": "1",
        "metrics": [],
        "datasets": [
            {
                "name": "input",
                "label": "Input",
                "fields": fields,
                "rows": [["2026-01-01", *(str(2**63 - 1) for _ in range(31))] for _ in range(100)],
                "keys": [],
                "source_ref": "source",
                "producer_id": "producer",
            }
        ],
    }
    now = datetime(2026, 1, 1, tzinfo=UTC)
    snapshot, _ = finalize_snapshot(publication_codec().decode(raw), now, now)
    source_size = len(
        json.dumps(
            snapshot_codec().encode(snapshot),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=dict,
        ).encode()
    )
    source = d.DatasetRef(
        "input",
        tuple(
            FieldRequirement(name, "date" if i == 0 else "int64", nullable=False)
            for i, name in enumerate(names)
        ),
    )
    definition = replace(
        definition,
        table=d.TableDefinition(
            "t" * 126,
            source,
            tuple(
                d.ColumnSelection(
                    name, SemanticRole.INPUT, ValueFormat("date" if i == 0 else "int64"), "D" * 510
                )
                for i, name in enumerate(names)
            ),
        ),
        chart=d.LineChartDefinition(
            "c" * 126,
            source,
            "day",
            tuple(
                d.SeriesSelection(
                    "s" + str(i) + "n" * 120,
                    "L" * 510,
                    name,
                    SemanticRole.OUTPUT,
                    ValueFormat("int64"),
                )
                for i, name in enumerate(names[1:])
            ),
        ),
    )
    pin = replace(pack.definition_pin, content_digest=c.definition_identifier(definition))
    pack = replace(pack, definition=definition, definition_pin=pin, template=pin)
    presentation = resolve_theme(pack.theme, (), None)
    assert isinstance(presentation, ResolvedTheme)
    value = prepare(definition, (), snapshot, pack, presentation, c.prepared_identifier)
    assert isinstance(value, PreparedReport)
    codec = c.prepared_codec()
    wire = codec.encode(value)
    output_size = len(
        json.dumps(
            wire, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=dict
        ).encode()
    )
    assert len(value.tables[0].columns) + len(value.charts[0].series) + 1 == 64
    assert all(
        column.field.label == "\x01" * 4096 and column.display_label == "D" * 510
        for column in value.tables[0].columns
    )
    assert source_size > 800000 and output_size <= 6 * source_size + 524288 < 8388608
    assert codec.decode(wire) == value
    (tmp_path / "selection-size-count.json").write_text(
        json.dumps({"source": source_size, "prepared": output_size, "selections": 64})
    )
