"""Closed report failure alternatives and bounded retained details."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from typing import cast, get_args

import pytest
from test_prepare import definition as definition
from test_prepare import snapshot as snapshot

from craftreport.adapters import report_codecs as c
from craftreport.adapters import report_models as m
from craftreport.adapters.canonical import WireFailure, canonical_bytes
from craftreport.contracts.outcomes import RecoveryDisposition as R
from craftreport.contracts.values import JsonObject, JsonValue
from craftreport.data.requirements import (
    BindingCode,
    BindingIssue,
    FieldRequirement,
    check_completeness,
)
from craftreport.data.values import Field, Snapshot
from craftreport.reporting import ports as p
from craftreport.reporting.definitions import (
    DatasetRef,
    DefinitionCode,
    DefinitionIssue,
    ReportDefinition,
)
from craftreport.reporting.prepare import requirements_for
from craftreport.themes.resolve import ThemeCode, ThemeFailure

type ResultCodec = (
    c.ReportResultCodec[p.ValidationResult, m.ValidationWire]
    | c.ReportResultCodec[p.PreparationResult, m.PreparationWire]
)


@pytest.fixture(params=[c.validation_result_codec, c.preparation_result_codec])
def codec(request: pytest.FixtureRequest) -> ResultCodec:
    return cast(Callable[[], ResultCodec], request.param)()


def failure(issues: tuple[p.ReportIssue, ...] = ()) -> p.ReportFailure:
    return p.ReportFailure.from_issues("prepared", "invalid_definition", R.CORRECT_REQUEST, issues)


@pytest.mark.parametrize("count", [0, 1, 64, 65, 10000])
def test_bounded_ordered_roundtrip(codec: ResultCodec, count: int) -> None:
    issues = tuple(DefinitionIssue(("parameters", str(i)), "required") for i in range(count))
    value = failure(issues)
    assert value.issues == issues[:64]
    assert value.total_issue_count == count
    assert value.omitted_issue_count == max(0, count - 64)
    wire = codec.encode(value)
    result = codec.decode(wire)
    assert result == value
    assert isinstance(result, p.ReportFailure)
    assert canonical_bytes(codec.encode(result)) == canonical_bytes(wire)
    assert len(canonical_bytes(wire)) <= 263168
    with pytest.raises(FrozenInstanceError):
        setattr(value, "stage", "quality_evaluated")


@pytest.mark.parametrize(
    "issue",
    [
        DefinitionIssue(("parameters", "private-name"), "required"),
        BindingIssue(("datasets", "private-name", "rows", 2147483647), "nullability"),
        ThemeFailure("unsupported_mapping", ("support", "gridcraft")),
    ],
)
def test_disjoint_typed_issues(codec: ResultCodec, issue: p.ReportIssue) -> None:
    result = codec.decode(codec.encode(failure((issue,))))
    assert isinstance(result, p.ReportFailure)
    assert result.issues == (issue,)
    assert type(result.issues[0]) is type(issue)
    vocabularies = [set(get_args(t.__value__)) for t in (DefinitionCode, BindingCode, ThemeCode)]
    assert all(not a & b for index, a in enumerate(vocabularies) for b in vocabularies[index + 1 :])


@pytest.mark.parametrize(
    "changes",
    [
        {"stage": "saved"},
        {"code": "release_blocked"},
        {"recovery": "retry"},
        {"recovery": "inspect"},
        {"unexpected": 1},
        {"total_issue_count": True},
        {"total_issue_count": -1},
        {"total_issue_count": 2147483648},
        {"total_issue_count": 1},
        {"omitted_issue_count": 1},
        {"omitted_issue_count": False},
        {"issues": [{"code": "secret", "location": ()}]},
        {"issues": [{"code": "required", "location": (), "extra": "x"}], "total_issue_count": 1},
    ],
)
def test_reject_invalid_failure(codec: ResultCodec, changes: dict[str, JsonValue]) -> None:
    wire = dict(codec.encode(failure()))
    wire["failure"] = {**cast(JsonObject, wire["failure"]), **changes}
    with pytest.raises(WireFailure):
        codec.decode(wire)


@pytest.mark.parametrize(
    "location",
    [(True,), (-1,), (2147483648,), ("x" * 127,), ("é" * 64,), ("\\" * 64,), tuple(range(9))],
)
def test_reject_location_overflow(codec: ResultCodec, location: tuple[str | int, ...]) -> None:
    wire = dict(codec.encode(failure()))
    wire["failure"] = {
        **cast(JsonObject, wire["failure"]),
        "issues": [{"code": "required", "location": location}],
        "total_issue_count": 1,
    }
    with pytest.raises(WireFailure):
        codec.decode(wire)
    with pytest.raises(ValueError):
        failure((DefinitionIssue(location, "required"),))


def test_maximum_locations_and_counts(codec: ResultCodec) -> None:
    location = ("é" * 63,) * 8
    issues = tuple(DefinitionIssue(location, "required") for _ in range(64))
    value = p.ReportFailure(
        "quality_evaluated",
        "invalid_definition",
        R.CORRECT_REQUEST,
        issues,
        2147483647,
        2147483647 - 64,
    )
    wire = codec.encode(value)
    assert codec.decode(wire) == value
    assert len(canonical_bytes(wire)) < 263168
    for issue in cast(tuple[JsonObject, ...], cast(JsonObject, wire["failure"])["issues"]):
        assert len(canonical_bytes(issue)) <= 4096
    for included, total, omitted in [(63, 64, 1), (64, 63, 0), (65, 65, 0)]:
        invalid = dict(wire)
        details: list[JsonValue] = [{"code": "required", "location": ()}] * included
        invalid["failure"] = {
            **cast(JsonObject, wire["failure"]),
            "issues": details,
            "total_issue_count": total,
            "omitted_issue_count": omitted,
        }
        with pytest.raises(WireFailure):
            codec.decode(invalid)


def test_mixed_unknown_and_large_envelopes(codec: ResultCodec) -> None:
    wire = codec.encode(failure())
    for invalid in (
        {**wire, "prepared": dict[str, JsonValue]()},
        {**wire, "unknown": 0},
        {"failure": {"padding": "x" * 263168}},
    ):
        with pytest.raises(WireFailure):
            codec.decode(invalid)
    assert codec.limits.max_output_bytes in (1048576, 8388608)


@pytest.mark.parametrize(
    "code,recovery",
    [
        ("pack_missing", R.CORRECT_REQUEST),
        ("input_unavailable", R.RETRY),
        ("input_unavailable", R.CORRECT_REQUEST),
        ("compatibility_unavailable", R.RETRY),
    ],
)
def test_exact_recovery_rules(codec: ResultCodec, code: p.ReportCode, recovery: R) -> None:
    value = p.ReportFailure.from_issues("prepared", code, recovery)
    assert codec.decode(codec.encode(value)) == value
    wrong = R.CORRECT_REQUEST if code == "compatibility_unavailable" else R.INSPECT
    with pytest.raises(ValueError):
        p.ReportFailure.from_issues("prepared", code, wrong)


def test_schema_refs_and_closed_objects(codec: ResultCodec) -> None:
    schema = codec.schema()
    assert len(cast(list[JsonValue], schema["anyOf"])) == 2
    definitions = cast(JsonObject, schema["$defs"])
    assert "ReportFailure" in definitions and "FailureWire" in definitions

    def visit(value: JsonValue) -> None:
        if isinstance(value, dict):
            if "$ref" in value:
                assert cast(str, value["$ref"]).removeprefix("#/$defs/") in definitions
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
            for child in value.values():
                visit(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                visit(child)

    visit(schema)


def test_real_producer_preserves_selected_names_and_order(
    codec: ResultCodec, definition: ReportDefinition, snapshot: Snapshot
) -> None:
    name = "é" * 63
    source = DatasetRef(
        name,
        (
            FieldRequirement("day", "int64", nullable=False),
            FieldRequirement(name, "int64", nullable=False),
        ),
    )
    table = replace(
        definition.table, source=source, columns=(replace(definition.table.columns[1], field=name),)
    )
    chart = replace(
        definition.chart,
        source=source,
        category_field="day",
        series=(replace(definition.chart.series[0], field=name),),
    )
    selected = replace(definition, table=table, chart=chart)
    dataset = replace(
        snapshot.datasets[0],
        name=name,
        fields=(Field("day", "Day", "int64", False), Field(name, "Label", "int64", True)),
        rows=((0, None),) * 100,
    )
    unused = replace(dataset, name="unused" * 50)
    supplied = replace(snapshot, datasets=(dataset, unused))
    issues = check_completeness(supplied, requirements_for(selected, ()))
    assert len(issues) == 101
    assert issues[0].location == ("datasets", name, "fields", name, "nullable")
    assert issues[64].location == ("datasets", name, "rows", 63, name)
    value = p.ReportFailure.from_issues("prepared", "incomplete_binding", R.CORRECT_REQUEST, issues)
    assert value.issues == issues[:64] and value.omitted_issue_count == 37
    assert codec.decode(codec.encode(value)) == value
