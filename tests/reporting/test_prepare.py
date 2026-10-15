"""Exact supplied projections; public codec integration belongs to task 7."""

from dataclasses import asdict, fields, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import cast

import pytest

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.snapshot_wire import encode_scalar
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import JsonObject, JsonValue, require_immutable
from craftreport.data.requirements import FieldRequirement
from craftreport.data.values import Dataset, Field, ImportedMetric, Scalar, Snapshot
from craftreport.policies.values import CheckId, ReleasePolicy
from craftreport.reporting import definitions as d
from craftreport.reporting import prepare as p
from craftreport.reporting.prepared import PreparationFailure, PreparedReport, ResolvedPack
from craftreport.themes.resolve import resolve_theme
from craftreport.themes.values import (
    ChartStyle,
    GridStyle,
    PackPin,
    ResolvedTheme,
    SemanticRole,
    TextStyle,
    Theme,
    ValueFormat,
)


def identity(report: PreparedReport) -> str:
    # Test-only composition using existing canonical/scalar functions, not a public codec.
    def wire(value: object) -> JsonValue:
        if isinstance(value, Enum):
            return str(value.value)
        if isinstance(value, dict):
            return {k: wire(v) for k, v in cast(dict[str, object], value).items()}
        if isinstance(value, tuple):
            return tuple(wire(v) for v in cast(tuple[object, ...], value))
        if type(value) in (Decimal, date, datetime, int):
            return encode_scalar(cast(Scalar, value))
        return cast(JsonValue, value)

    content = asdict(report)
    del content["content_digest"]
    return sha256(canonical_bytes(cast(JsonObject, wire(content)))).hexdigest()


@pytest.fixture
def snapshot() -> Snapshot:
    schema = (
        Field("day", "Original day", "date", False),
        Field("amount", "Original USD", "decimal", True, "USD", 30, 8),
        Field("count", "Original count", "int64", False),
        Field("note", "Literal note", "text", False),
    )
    rows = (
        (date(2026, 1, 3), Decimal("-12.12345678"), 2**63 - 1, "=SUM(A1)"),
        (date(2026, 1, 1), None, 0, "+literal"),
        (date(2026, 1, 2), Decimal("0.00000000"), -(2**63), "@literal"),
    )
    dataset = Dataset("input", "Supplied", schema, rows, (), "source", "producer", "1")
    now = datetime(2026, 1, 3, tzinfo=UTC)
    return Snapshot("1", "feed", 1, "a" * 64, (dataset,), (), now, now, now, now)


@pytest.fixture
def definition() -> d.ReportDefinition:
    source = d.DatasetRef(
        "input",
        (
            FieldRequirement("day", "date", nullable=False),
            FieldRequirement("amount", "decimal", "USD"),
            FieldRequirement("count", "int64", nullable=False),
            FieldRequirement("note", "text", nullable=False),
        ),
    )
    return d.ReportDefinition(
        "1",
        "public/report",
        "1",
        d.ParameterRef("title"),
        (d.ParameterDefinition("title", "text", False, "Literal title"),),
        d.TableDefinition(
            "table",
            source,
            (
                d.ColumnSelection(
                    "note", SemanticRole.ROW_LABEL, ValueFormat("text"), "Display only"
                ),
                d.ColumnSelection("count", SemanticRole.INPUT, ValueFormat("int64")),
                d.ColumnSelection("amount", SemanticRole.OUTPUT, ValueFormat("decimal", 2)),
                d.ColumnSelection("day", SemanticRole.INPUT, ValueFormat("date")),
            ),
            null_text="missing",
        ),
        d.LineChartDefinition(
            "chart",
            source,
            "day",
            (
                d.SeriesSelection(
                    "count", "Count", "count", SemanticRole.INPUT, ValueFormat("int64")
                ),
                d.SeriesSelection(
                    "usd", "USD", "amount", SemanticRole.OUTPUT, ValueFormat("decimal")
                ),
            ),
        ),
        ReleasePolicy((CheckId.DEFINITION, CheckId.BINDINGS), "scope"),
    )


@pytest.fixture
def pack(definition: d.ReportDefinition) -> ResolvedPack:
    style = TextStyle("Arial", 11, False, False, "#000000", None, "left", True)
    theme = Theme(
        VersionPin("house", "1", "b" * 64),
        tuple((role, style) for role in SemanticRole),
        (ValueFormat("decimal"),),
        ChartStyle(("#112233",), 1, True, True),
        GridStyle(True, 20, 100),
    )
    pin = VersionPin(definition.report_id, definition.version, "c" * 64)
    return ResolvedPack(
        PackPin(VersionPin("public/pack", "1", "d" * 64), "Public", "public"),
        definition,
        pin,
        pin,
        theme,
    )


def compile_report(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> PreparedReport:
    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    result = p.prepare(definition, (), snapshot, pack, theme, identity)
    assert isinstance(result, PreparedReport)
    return result


def test_exact_two_snapshots(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    first = compile_report(definition, snapshot, pack)
    assert first.tables[0].rows == (
        ("=SUM(A1)", 2**63 - 1, Decimal("-12.12345678"), date(2026, 1, 3)),
        ("+literal", 0, None, date(2026, 1, 1)),
        ("@literal", -(2**63), Decimal("0.00000000"), date(2026, 1, 2)),
    )
    assert first.charts[0].categories == (date(2026, 1, 3), date(2026, 1, 1), date(2026, 1, 2))
    assert first.charts[0].series[0].values == (2**63 - 1, 0, -(2**63))
    assert first.charts[0].series[1].values == (Decimal("-12.12345678"), None, Decimal("0E-8"))
    assert first.charts[0].category_schema == snapshot.datasets[0].fields[0]
    assert first.tables[0].columns[0].field.label == "Literal note"
    assert first.tables[0].columns[0].display_label == "Display only"
    assert first.tables[0].null_text == "missing"
    assert first.tables[0].long_labels == "wrap"
    assert first.title == "Literal title"
    assert first.resolved_parameters == (("title", "Literal title"),)
    second_data = replace(
        snapshot.datasets[0], rows=((date(2026, 2, 1), Decimal("9E-8"), 7, "-text"),)
    )
    second = compile_report(
        definition,
        replace(snapshot, producer_version=2, content_digest="e" * 64, datasets=(second_data,)),
        pack,
    )
    assert second.tables[0].rows == (("-text", 7, Decimal("9E-8"), date(2026, 2, 1)),)
    assert second.charts[0].series[1].values == (Decimal("9E-8"),)
    assert second.content_digest != first.content_digest
    assert second.definition == first.definition == pack.definition_pin
    assert second.template == first.template == pack.template
    assert second.pack == pack.pin
    require_immutable(first)
    assert type(first.tables[0].rows[0][1]) is int
    assert type(first.tables[0].rows[0][2]) is Decimal
    assert first.tables[0].rows[0][2].as_tuple().exponent == -8
    assert type(first.tables[0].rows[0][3]) is date


def test_identity_and_theme_only(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    first = compile_report(definition, snapshot, pack)
    assert compile_report(definition, snapshot, pack) == first
    later = datetime(2027, 1, 1, tzinfo=UTC)
    assert (
        compile_report(definition, replace(snapshot, received_at=later, accepted_at=later), pack)
        == first
    )
    new_theme = replace(pack.theme, version_pin=VersionPin("other", "2", "f" * 64))
    changed = compile_report(definition, snapshot, replace(pack, theme=new_theme))
    assert (changed.tables, changed.charts, changed.metric_provenance) == (
        first.tables,
        first.charts,
        first.metric_provenance,
    )
    assert changed.content_digest != first.content_digest
    assert not {"target", "run", "quality", "accepted_at"} & {f.name for f in fields(first)}
    with pytest.raises(ValueError):
        replace(first, content_digest="")
    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    for bad in ("", "invalid", "A" * 64):
        with pytest.raises(ValueError):
            p.prepare(definition, (), snapshot, pack, theme, lambda _: bad)


def test_empty_and_failures(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    empty = compile_report(
        definition, replace(snapshot, datasets=(replace(snapshot.datasets[0], rows=()),)), pack
    )
    assert len(empty.tables[0].columns) == 4
    assert empty.tables[0].rows == ()
    assert empty.tables[0].empty_note == "No data"
    assert empty.charts[0].categories == ()
    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    missing = p.prepare(definition, (), replace(snapshot, datasets=()), pack, theme, identity)
    assert isinstance(missing, PreparationFailure)
    assert missing.code == "incomplete_binding"
    assert missing.issues[0].code == "missing_dataset"
    invalid = p.prepare(
        definition, (d.ParameterValue("title", 42),), snapshot, pack, theme, identity
    )
    assert isinstance(invalid, PreparationFailure)
    assert invalid.code == "invalid_parameter"
    mismatch = p.prepare(replace(definition, title="Changed"), (), snapshot, pack, theme, identity)
    assert isinstance(mismatch, PreparationFailure)
    assert mismatch.code == "invalid_definition"


def test_metric_provenance_and_scalar_rejection(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    metric = ImportedMetric(
        "metric",
        "USD",
        "2026",
        None,
        "source",
        "producer",
        "method-v1",
        "series",
        Field("producer_name", "Actual label", "decimal", True, "USD", 30, 8),
        ("=literal", "earlier"),
        (Decimal("-1.00000000"), None),
        ("external-evidence",),
    )
    source = d.MetricRef("metric", "USD", ("decimal",), "series")
    definition = replace(
        definition,
        table=d.TableDefinition(
            "table",
            source,
            (
                d.ColumnSelection("label", SemanticRole.ROW_LABEL, ValueFormat("text")),
                d.ColumnSelection("value", SemanticRole.OUTPUT, ValueFormat("decimal")),
            ),
        ),
        chart=d.LineChartDefinition(
            "chart",
            source,
            "label",
            (
                d.SeriesSelection(
                    "value", "Metric", "value", SemanticRole.OUTPUT, ValueFormat("decimal")
                ),
            ),
        ),
    )
    pack = replace(pack, definition=definition)
    snapshot = replace(snapshot, metrics=(metric,))
    result = compile_report(definition, snapshot, pack)
    assert result.tables[0].rows == (("=literal", Decimal("-1.00000000")), ("earlier", None))
    assert result.charts[0].categories == ("=literal", "earlier")
    assert result.charts[0].series[0].field == metric.value_schema
    assert result.tables[0].columns[1].field == metric.value_schema
    assert result.metric_provenance == (metric,)
    scalar = replace(metric, shape="scalar", labels=(), values=(Decimal("1.00000000"),))
    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    failed = p.prepare(definition, (), replace(snapshot, metrics=(scalar,)), pack, theme, identity)
    assert isinstance(failed, PreparationFailure)
    assert failed.issues[0].code == "incompatible_shape"


def test_scalar_metric_table_and_empty_series(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    metric = ImportedMetric(
        "scalar",
        "USD",
        "2026",
        None,
        "source",
        "producer",
        "v1",
        "scalar",
        Field("original", "Producer label", "int64", False, "USD"),
        (),
        (2**63 - 1,),
        ("evidence",),
    )
    table = d.TableDefinition(
        "metric",
        d.MetricRef("scalar", "USD", ("int64",), "scalar"),
        (
            d.ColumnSelection("label", SemanticRole.ROW_LABEL, ValueFormat("text")),
            d.ColumnSelection("value", SemanticRole.INPUT, ValueFormat("int64")),
        ),
    )
    definition = replace(definition, table=table)
    result = compile_report(
        definition, replace(snapshot, metrics=(metric,)), replace(pack, definition=definition)
    )
    assert result.tables[0].rows == (("scalar", 2**63 - 1),)
    assert result.tables[0].columns[1].field == metric.value_schema
    assert result.metric_provenance == (metric,)
    metric = replace(metric, shape="series", labels=(), values=())
    source = d.MetricRef("scalar", "USD", ("int64",), "series")
    definition = replace(
        definition,
        table=replace(table, source=source),
        chart=d.LineChartDefinition(
            "empty",
            source,
            "label",
            (d.SeriesSelection("v", "Value", "value", SemanticRole.INPUT, ValueFormat("int64")),),
        ),
    )
    result = compile_report(
        definition, replace(snapshot, metrics=(metric,)), replace(pack, definition=definition)
    )
    assert result.tables[0].rows == result.charts[0].categories == ()
    assert result.tables[0].empty_note == "No data"
    assert result.charts[0].series[0].values == ()


def test_missing_and_incompatible_sources(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    dataset = snapshot.datasets[0]
    altered = replace(
        dataset,
        fields=tuple(replace(f, unit="EUR") if f.name == "amount" else f for f in dataset.fields),
    )
    result = p.prepare(
        definition, (), replace(snapshot, datasets=(altered,)), pack, theme, identity
    )
    assert isinstance(result, PreparationFailure)
    assert result.issues[0].code == "incompatible_unit"
    assert result.issues[0].location == ("datasets", "input", "fields", "amount", "unit")
    mismatch = p.prepare(
        definition,
        (),
        snapshot,
        pack,
        replace(theme, version_pin=VersionPin("other", "1", "f" * 64)),
        identity,
    )
    assert isinstance(mismatch, PreparationFailure)
    assert mismatch.issues[0].location == ("theme",)
    with pytest.raises(d.DefinitionError):
        replace(pack, template=VersionPin("different", "1", "a" * 64))


def test_identifier_and_changed_parameters(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    calls: list[str] = []

    def identify(report: PreparedReport) -> str:
        calls.append(report.content_digest)
        return identity(report)

    theme = resolve_theme(pack.theme, (), None)
    assert isinstance(theme, ResolvedTheme)
    result = p.prepare(definition, (), snapshot, pack, theme, identify)
    assert isinstance(result, PreparedReport)
    assert calls == [""]
    changed = p.prepare(
        definition,
        (d.ParameterValue("title", "=Literal title"),),
        snapshot,
        pack,
        theme,
        identity,
    )
    assert isinstance(changed, PreparedReport)
    assert changed.title == "=Literal title"
    assert changed.content_digest != result.content_digest
    assert changed.tables == result.tables
    assert result.content_digest == identity(result)


def test_retained_invariants(
    definition: d.ReportDefinition, snapshot: Snapshot, pack: ResolvedPack
) -> None:
    result = compile_report(definition, snapshot, pack)
    with pytest.raises(ValueError):
        replace(result.tables[0], rows=((1,),))
    with pytest.raises(ValueError):
        replace(result.charts[0], categories=())
    with pytest.raises(ValueError):
        replace(result.tables[0], rows=((1, 2, 3, 4),))
    with pytest.raises((ValueError, TypeError)):
        replace(result, tables=cast(tuple[object, ...], []))
    with pytest.raises(ValueError):
        replace(result, resolved_parameters=cast(tuple[object, ...], (("x", 1.2),)))
    with pytest.raises(ValueError):
        replace(definition.table, columns=(definition.table.columns[0],) * 2)
    with pytest.raises(ValueError):
        replace(definition.chart, series=(definition.chart.series[0],) * 2)
    long_note = "=literal " + "x" * 1000
    dataset = replace(snapshot.datasets[0], rows=((date(2026, 1, 1), None, 0, long_note),))
    projected = compile_report(definition, replace(snapshot, datasets=(dataset,)), pack)
    assert projected.tables[0].rows[0][0] == long_note
    assert projected.tables[0].long_labels == "wrap"
    escaped_label = "\x01" * 4096
    dataset = replace(
        dataset,
        fields=tuple(
            replace(field, label=escaped_label) if field.name == "count" else field
            for field in dataset.fields
        ),
    )
    projected = compile_report(definition, replace(snapshot, datasets=(dataset,)), pack)
    assert projected.tables[0].columns[1].display_label == escaped_label
