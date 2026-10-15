"""Completeness is declared per binding, independently of accepted publication."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast

import pytest

from craftreport.data.requirements import (
    BindingIssue,
    DatasetRequirement,
    FieldRequirement,
    InputRequirements,
    MetricRequirement,
    check_completeness,
)
from craftreport.data.values import Dataset, Field, ImportedMetric, ScalarKind, Snapshot


@pytest.fixture
def snapshot() -> Snapshot:
    stamp = datetime(2026, 10, 15, tzinfo=UTC)
    dataset = Dataset(
        "positions",
        "Positions",
        (
            Field("day", "Day", "text", False),
            Field("amount", "Amount", "decimal", True, "USD", 8, 2),
        ),
        (("Monday", Decimal("12.30")), ("Tuesday", None)),
        (),
        "source:positions",
        "producer",
        "v1",
    )
    metric = ImportedMetric(
        "return",
        "%",
        "2026-Q3",
        None,
        "source:return",
        "producer",
        "method-v1",
        "series",
        Field("value", "Return", "decimal", True, "%", 8, 2),
        ("second", "first"),
        (Decimal("0.00"), None),
        ("claim:external",),
    )
    return Snapshot("1", "feed", 1, "a" * 64, (dataset,), (metric,), None, None, stamp, stamp)


def test_one_accepted_snapshot_has_independent_binding_completeness(snapshot: Snapshot) -> None:
    complete = InputRequirements(
        (DatasetRequirement("positions", (FieldRequirement("amount", "decimal", "USD"),)),),
        (MetricRequirement("return", "%", ("int64", "decimal"), "series"),),
    )
    incomplete = InputRequirements(
        (DatasetRequirement("positions", (FieldRequirement("missing", "text"),)),),
        (MetricRequirement("missing"),),
    )
    original = replace(snapshot)
    assert check_completeness(snapshot, complete) == ()
    assert check_completeness(snapshot, incomplete) == (
        BindingIssue(("datasets", "positions", "fields", "missing"), "missing_field"),
        BindingIssue(("metrics", "missing"), "missing_metric"),
    )
    assert snapshot == original
    assert snapshot.datasets[0].rows[0][1] == Decimal("12.30")
    assert snapshot.metrics[0].labels == ("second", "first")


def test_missing_sources_do_not_invent_nested_issues(snapshot: Snapshot) -> None:
    requirements = InputRequirements(
        (DatasetRequirement("absent", (FieldRequirement("absent", "text"),)),),
        (MetricRequirement("absent"),),
    )
    assert check_completeness(snapshot, requirements) == (
        BindingIssue(("datasets", "absent"), "missing_dataset"),
        BindingIssue(("metrics", "absent"), "missing_metric"),
    )


def test_all_incompatibilities_have_precise_source_locations(snapshot: Snapshot) -> None:
    requirements = InputRequirements(
        (DatasetRequirement("positions", (FieldRequirement("amount", "int64", "EUR", False),)),),
        (MetricRequirement("return", "USD", ("bool",), "scalar", False),),
    )
    assert check_completeness(snapshot, requirements) == (
        BindingIssue(("datasets", "positions", "fields", "amount", "kind"), "incompatible_type"),
        BindingIssue(("datasets", "positions", "fields", "amount", "unit"), "incompatible_unit"),
        BindingIssue(("datasets", "positions", "fields", "amount", "nullable"), "nullability"),
        BindingIssue(("datasets", "positions", "rows", 1, "amount"), "nullability"),
        BindingIssue(("metrics", "return", "value_schema", "kind"), "incompatible_type"),
        BindingIssue(("metrics", "return", "unit"), "incompatible_unit"),
        BindingIssue(("metrics", "return", "shape"), "incompatible_shape"),
        BindingIssue(("metrics", "return", "value_schema", "nullable"), "nullability"),
        BindingIssue(("metrics", "return", "values", 1), "nullability"),
    )


@pytest.mark.parametrize("empty", [False, True])
def test_nonnull_requires_declaration_even_without_null_samples(
    snapshot: Snapshot, empty: bool
) -> None:
    dataset = replace(snapshot.datasets[0], rows=() if empty else (("Monday", Decimal("1.00")),))
    metric = replace(
        snapshot.metrics[0],
        labels=() if empty else ("first",),
        values=() if empty else (Decimal("1.00"),),
    )
    requirements = InputRequirements(
        (
            DatasetRequirement(
                "positions", (FieldRequirement("amount", "decimal", nullable=False),)
            ),
        ),
        (MetricRequirement("return", nullable=False),),
    )
    assert check_completeness(
        replace(snapshot, datasets=(dataset,), metrics=(metric,)), requirements
    ) == (
        BindingIssue(("datasets", "positions", "fields", "amount", "nullable"), "nullability"),
        BindingIssue(("metrics", "return", "value_schema", "nullable"), "nullability"),
    )


def test_nonnullable_sources_and_values_satisfy_required_nonnull(snapshot: Snapshot) -> None:
    dataset = replace(
        snapshot.datasets[0],
        fields=(
            snapshot.datasets[0].fields[0],
            replace(snapshot.datasets[0].fields[1], nullable=False),
        ),
        rows=(("Monday", Decimal("1.00")),),
    )
    metric = replace(
        snapshot.metrics[0],
        value_schema=replace(snapshot.metrics[0].value_schema, nullable=False),
        labels=("first",),
        values=(Decimal("1.00"),),
    )
    requirements = InputRequirements(
        (
            DatasetRequirement(
                "positions", (FieldRequirement("amount", "decimal", nullable=False),)
            ),
        ),
        (MetricRequirement("return", nullable=False),),
    )
    assert (
        check_completeness(replace(snapshot, datasets=(dataset,), metrics=(metric,)), requirements)
        == ()
    )


@pytest.mark.parametrize("kind,value", [("text", "=literal"), ("bool", True), ("int64", 4)])
def test_unrestricted_metrics_accept_declared_scalar_kind(
    snapshot: Snapshot,
    kind: ScalarKind,
    value: str | bool | int,
) -> None:
    metric = replace(
        snapshot.metrics[0],
        value_schema=Field("value", "Value", kind, False),
        shape="scalar",
        labels=(),
        values=(value,),
    )
    requirements = InputRequirements((), (MetricRequirement("return"),))
    assert check_completeness(replace(snapshot, metrics=(metric,)), requirements) == ()


@pytest.mark.parametrize(
    "shape,kind,expected",
    [
        (
            "scalar",
            "decimal",
            (BindingIssue(("metrics", "return", "shape"), "incompatible_shape"),),
        ),
        (
            "series",
            "text",
            (BindingIssue(("metrics", "return", "value_schema", "kind"), "incompatible_type"),),
        ),
        ("series", "int64", ()),
        ("series", "decimal", ()),
    ],
)
def test_metric_chart_requires_explicit_numeric_series_even_when_empty(
    snapshot: Snapshot,
    shape: Literal["scalar", "series"],
    kind: ScalarKind,
    expected: tuple[BindingIssue, ...],
) -> None:
    schema = Field(
        "value",
        "Value",
        kind,
        False,
        precision=8 if kind == "decimal" else None,
        scale=2 if kind == "decimal" else None,
    )
    metric = replace(
        snapshot.metrics[0],
        value_schema=schema,
        shape=shape,
        labels=(),
        values=(Decimal("1.00"),) if shape == "scalar" else (),
    )
    requirements = InputRequirements(
        (), (MetricRequirement("return", kinds=("int64", "decimal"), shape="series"),)
    )
    assert check_completeness(replace(snapshot, metrics=(metric,)), requirements) == expected


def test_dataset_chart_uses_declared_exact_kind_and_preserves_null_gaps(snapshot: Snapshot) -> None:
    requirements = InputRequirements(
        (
            DatasetRequirement(
                "positions",
                (
                    FieldRequirement("day", "date", nullable=False),
                    FieldRequirement("amount", "decimal", "USD"),
                ),
            ),
        ),
        (),
    )
    assert check_completeness(snapshot, requirements) == (
        BindingIssue(("datasets", "positions", "fields", "day", "kind"), "incompatible_type"),
    )
    text_category = replace(requirements.datasets[0].fields[0], kind="text")
    corrected = InputRequirements(
        (
            DatasetRequirement(
                "positions",
                (
                    text_category,
                    requirements.datasets[0].fields[1],
                ),
            ),
        ),
        (),
    )
    assert check_completeness(snapshot, corrected) == ()


def test_empty_requirements_need_nothing(snapshot: Snapshot) -> None:
    assert check_completeness(snapshot, InputRequirements((), ())) == ()


def test_requirement_values_are_recursively_immutable() -> None:
    field = FieldRequirement("amount", "decimal", "USD", False)
    dataset = DatasetRequirement("positions", (field,))
    metric = MetricRequirement("return", kinds=("decimal",))
    requirements = InputRequirements((dataset,), (metric,))
    for value, name, replacement in (
        (field, "name", "changed"),
        (dataset, "fields", ()),
        (metric, "kinds", ()),
        (requirements, "datasets", ()),
        (BindingIssue(("metrics", "return"), "missing_metric"), "code", "missing_dataset"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, name, replacement)


@pytest.mark.parametrize("case", ["fields", "datasets", "metrics", "kinds", "location"])
def test_mutable_containers_are_rejected(case: str) -> None:
    with pytest.raises(ValueError):
        if case == "fields":
            DatasetRequirement("positions", cast("tuple[FieldRequirement, ...]", []))
        elif case == "datasets":
            InputRequirements(cast("tuple[DatasetRequirement, ...]", []), ())
        elif case == "metrics":
            InputRequirements((), cast("tuple[MetricRequirement, ...]", []))
        elif case == "kinds":
            MetricRequirement("return", kinds=cast("tuple[ScalarKind, ...]", []))
        else:
            BindingIssue(cast("tuple[str | int, ...]", []), "missing_field")


@pytest.mark.parametrize("kind", ["float", "", 1, True])
def test_invalid_kinds_cannot_turn_into_unrestricted_constraints(kind: object) -> None:
    with pytest.raises(ValueError):
        FieldRequirement("amount", cast(ScalarKind, kind))
    with pytest.raises(ValueError):
        MetricRequirement("return", kinds=(cast(ScalarKind, kind),))


@pytest.mark.parametrize("identity", ["", "  ", 1, None])
def test_requirements_need_explicit_source_identities(identity: object) -> None:
    with pytest.raises(ValueError):
        FieldRequirement(cast(str, identity), "text")
    with pytest.raises(ValueError):
        DatasetRequirement(cast(str, identity), ())
    with pytest.raises(ValueError):
        MetricRequirement(cast(str, identity))


@pytest.mark.parametrize("unit", ["", "  ", 4])
def test_units_are_explicit_nonempty_text(unit: object) -> None:
    with pytest.raises(ValueError):
        FieldRequirement("amount", "int64", cast(str, unit))
    with pytest.raises(ValueError):
        MetricRequirement("return", cast(str, unit))


@pytest.mark.parametrize("nullable", [0, 1, "false", None])
def test_nonboolean_nullability_is_rejected(nullable: object) -> None:
    with pytest.raises(ValueError):
        FieldRequirement("amount", "int64", nullable=cast(bool, nullable))
    with pytest.raises(ValueError):
        MetricRequirement("return", nullable=cast(bool, nullable))


@pytest.mark.parametrize("shape", ["table", "", 1])
def test_metric_shape_is_closed(shape: object) -> None:
    with pytest.raises(ValueError):
        MetricRequirement("return", shape=cast("Literal['scalar', 'series']", shape))


def test_nested_values_require_the_agreed_types() -> None:
    with pytest.raises(ValueError):
        DatasetRequirement("positions", cast("tuple[FieldRequirement, ...]", (object(),)))
    with pytest.raises(ValueError):
        InputRequirements(cast("tuple[DatasetRequirement, ...]", (object(),)), ())
    with pytest.raises(ValueError):
        InputRequirements((), cast("tuple[MetricRequirement, ...]", (object(),)))
