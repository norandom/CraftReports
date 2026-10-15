"""Typed reusable report contracts; raw JSON validation belongs to adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast

import pytest

from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.data.requirements import FieldRequirement, MetricRequirement
from craftreport.data.values import Scalar, ScalarKind
from craftreport.policies.values import CheckId, ReleasePolicy
from craftreport.reporting import definitions as d
from craftreport.reporting import prepare as p
from craftreport.themes.values import SemanticRole, ValueFormat


@pytest.fixture
def definition() -> d.ReportDefinition:
    source = d.DatasetRef(
        d.ParameterRef("feed"),
        (
            FieldRequirement("period", "text", nullable=False),
            FieldRequirement("amount", "decimal", "USD"),
        ),
    )
    return d.ReportDefinition(
        "1",
        "public/positions",
        "1.0.0",
        d.ParameterRef("title"),
        (
            d.ParameterDefinition("title", "text", True),
            d.ParameterDefinition("feed", "text", False, "positions"),
        ),
        d.TableDefinition(
            "holdings",
            source,
            (
                d.ColumnSelection("period", SemanticRole.ROW_LABEL, ValueFormat("text")),
                d.ColumnSelection(
                    "amount", SemanticRole.EXTERNAL_RESULT, ValueFormat("decimal", 2)
                ),
            ),
        ),
        d.LineChartDefinition(
            "history",
            source,
            "period",
            (
                d.SeriesSelection(
                    "amount",
                    "Supplied amount",
                    "amount",
                    SemanticRole.EXTERNAL_RESULT,
                    ValueFormat("decimal", 2),
                ),
            ),
        ),
        ReleasePolicy((CheckId.DEFINITION, CheckId.BINDINGS), "Report only"),
    )


def issue(
    error: pytest.ExceptionInfo[d.DefinitionError], code: str, location: tuple[str | int, ...]
) -> None:
    assert error.value.issue.code == code
    assert error.value.issue.location == location


def test_public_typed_definition_resolves_order_and_upstream_requirements(
    definition: d.ReportDefinition,
) -> None:
    values = p.resolve_parameters(definition, (d.ParameterValue("title", "Supplied holdings"),))
    assert values == (("title", "Supplied holdings"), ("feed", "positions"))
    requirements = p.requirements_for(definition, values)
    assert len(requirements.datasets) == 1
    assert requirements.datasets[0].name == "positions"
    assert requirements.datasets[0].fields == cast(d.DatasetRef, definition.table.source).fields
    assert requirements.metrics == ()
    require_immutable(definition)
    with pytest.raises(FrozenInstanceError):
        setattr(definition, "title", "Changed")
    assert {item.identity for item in definition.required_capabilities} == {
        "report.table",
        "report.line_chart",
        "report.semantic_style",
    }


def test_parameters_report_missing_wrong_type_choice_and_unknown_locations(
    definition: d.ReportDefinition,
) -> None:
    with pytest.raises(d.DefinitionError) as error:
        p.resolve_parameters(definition, ())
    issue(error, "required", ("parameters", "title"))
    with pytest.raises(d.DefinitionError) as error:
        p.resolve_parameters(definition, (d.ParameterValue("title", 12),))
    issue(error, "invalid_type", ("parameters", "title"))
    with pytest.raises(d.DefinitionError) as error:
        p.resolve_parameters(definition, (d.ParameterValue("sql", "SELECT"),))
    issue(error, "unsupported", ("parameters", "sql"))
    with pytest.raises(d.DefinitionError) as error:
        p.resolve_parameters(
            definition, (d.ParameterValue("title", "A"), d.ParameterValue("title", "B"))
        )
    issue(error, "duplicate", ("parameters", "title"))


@pytest.mark.parametrize(
    "kind,minimum,maximum,valid,invalid",
    [
        ("int64", 1, 3, 3, 4),
        ("decimal", Decimal("-1.2300"), Decimal("2.0000"), Decimal("-1.2300"), Decimal("-1.24")),
        ("date", date(2026, 1, 1), date(2026, 1, 3), date(2026, 1, 1), date(2025, 1, 1)),
        (
            "datetime",
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
            datetime(2027, 1, 1, tzinfo=UTC),
        ),
    ],
)
def test_inclusive_parameter_ranges(
    kind: str, minimum: Scalar, maximum: Scalar, valid: Scalar, invalid: Scalar
) -> None:
    parameter = d.ParameterDefinition(
        "value", cast(ScalarKind, kind), True, valid, (), minimum, maximum
    )
    assert d.check_parameter(parameter, valid) is valid
    with pytest.raises(d.DefinitionError) as error:
        d.check_parameter(parameter, invalid)
    issue(error, "range", ("parameters", "value"))
    with pytest.raises(d.DefinitionError):
        replace(parameter, minimum=maximum, maximum=minimum)


def test_parameter_defaults_choices_and_exact_scalar_types() -> None:
    parameter = d.ParameterDefinition("method", "text", False, "producer", ("producer", "other"))
    with pytest.raises(d.DefinitionError):
        replace(parameter, default="unknown")
    for kind, value in (
        ("int64", True),
        ("decimal", 1.25),
        ("date", datetime(2026, 1, 1)),
        ("decimal", Decimal("NaN")),
        ("int64", 2**63),
    ):
        with pytest.raises(d.DefinitionError):
            d.ParameterDefinition("value", cast(ScalarKind, kind), False, cast(Scalar, value))
    with pytest.raises(d.DefinitionError):
        d.ParameterDefinition("switch", "bool", True, None, (), False, True)


def test_references_must_exist_and_be_text(definition: d.ReportDefinition) -> None:
    with pytest.raises(d.DefinitionError) as error:
        replace(definition, title=d.ParameterRef("missing"))
    issue(error, "reference", ("title",))
    with pytest.raises(d.DefinitionError):
        replace(
            definition,
            parameters=(d.ParameterDefinition("title", "int64", True), definition.parameters[1]),
        )


def test_changed_parameters_change_declared_binding_without_mutating_definition(
    definition: d.ReportDefinition,
) -> None:
    first = p.requirements_for(definition, (("title", "First"), ("feed", "positions")))
    second = p.requirements_for(definition, (("title", "Second"), ("feed", "replacement")))
    assert first.datasets[0].name == "positions"
    assert second.datasets[0].name == "replacement"
    assert isinstance(definition.table.source, d.DatasetRef)
    assert definition.table.source.name == d.ParameterRef("feed")
    with pytest.raises(d.DefinitionError) as error:
        p.resolve_parameters(
            definition, (d.ParameterValue("title", "A"), d.ParameterValue("feed", "x" * 127))
        )
    issue(error, "limit", ("table", "source"))
    optional = replace(
        definition,
        parameters=definition.parameters + (d.ParameterDefinition("optional_note", "text", False),),
    )
    assert p.resolve_parameters(optional, (d.ParameterValue("title", "A"),)) == (
        ("title", "A"),
        ("feed", "positions"),
    )


def test_table_and_chart_reject_duplicate_unsupported_or_unbound_selections(
    definition: d.ReportDefinition,
) -> None:
    with pytest.raises(d.DefinitionError):
        replace(definition.table, columns=definition.table.columns * 2)
    with pytest.raises(d.DefinitionError):
        replace(definition.table, columns=(replace(definition.table.columns[0], field="missing"),))
    with pytest.raises(d.DefinitionError):
        replace(definition.chart, series=definition.chart.series * 2)
    with pytest.raises(d.DefinitionError):
        replace(definition.chart, category_field="amount")
    with pytest.raises(d.DefinitionError):
        replace(definition.table, empty_behavior=cast(d.EmptyBehavior, "drop_headers"))
    with pytest.raises(TypeError, match="sql"):
        cast(Callable[..., d.TableDefinition], d.TableDefinition)(
            **{
                "identity": "table",
                "source": definition.table.source,
                "columns": definition.table.columns,
                "sql": "SELECT",
            }
        )


def test_chart_source_requires_nonnullable_category_and_numeric_series(
    definition: d.ReportDefinition,
) -> None:
    for fields in (
        (FieldRequirement("period", "text"), FieldRequirement("amount", "decimal", "USD")),
        (FieldRequirement("period", "text", nullable=False), FieldRequirement("amount", "text")),
    ):
        with pytest.raises(d.DefinitionError):
            replace(definition.chart, source=d.DatasetRef("positions", fields))
    for metric in (
        d.MetricRef("return", "%", ("decimal",), "scalar"),
        d.MetricRef("return", "%", ("text",), "series"),
        d.MetricRef("return", "%", (), "series"),
    ):
        with pytest.raises(d.DefinitionError):
            replace(
                definition.chart,
                source=metric,
                category_field="label",
                series=(replace(definition.chart.series[0], field="value"),),
            )


def test_metric_chart_requirements_are_explicit_before_snapshot_selection(
    definition: d.ReportDefinition,
) -> None:
    metric = d.MetricRef("return", "%", ("int64", "decimal"), "series", False)
    chart = replace(
        definition.chart,
        source=metric,
        category_field="label",
        series=(replace(definition.chart.series[0], field="value"),),
    )
    changed = replace(definition, chart=chart)
    requirements = p.requirements_for(changed, (("title", "A"), ("feed", "positions")))
    assert requirements.metrics[0].shape == "series"
    assert requirements.metrics[0].kinds == ("int64", "decimal")
    assert requirements.metrics[0].nullable is False


def test_repeated_requirements_intersect_and_conflicts_reject(
    definition: d.ReportDefinition,
) -> None:
    source = cast(d.DatasetRef, definition.chart.source)
    strict = replace(source, fields=(source.fields[0], replace(source.fields[1], nullable=False)))
    changed = replace(definition, chart=replace(definition.chart, source=strict))
    requirements = p.requirements_for(changed, (("title", "A"), ("feed", "positions")))
    assert requirements.datasets[0].fields[1].nullable is False
    incompatible = replace(strict, fields=(strict.fields[0], replace(strict.fields[1], unit="EUR")))
    changed = replace(definition, chart=replace(definition.chart, source=incompatible))
    with pytest.raises(d.DefinitionError) as error:
        p.requirements_for(changed, (("title", "A"), ("feed", "positions")))
    assert error.value.issue.code == "constraint_conflict"


def test_template_digest_and_identity_cannot_override_pack_structure(
    definition: d.ReportDefinition,
) -> None:
    pin = VersionPin(definition.report_id, definition.version, "a" * 64)
    assert p.validate_template(definition, pin, lambda value: "a" * 64) is definition
    for selected in (
        replace(pin, identity="different"),
        replace(pin, version="2"),
        replace(pin, content_digest="b" * 64),
    ):
        with pytest.raises(d.DefinitionError) as error:
            p.validate_template(definition, selected, lambda value: "a" * 64)
        issue(error, "template_mismatch", ("template",))


def test_declaration_size_bounds_and_immutability(definition: d.ReportDefinition) -> None:
    assert replace(definition, report_id="界" * 42).report_id == "界" * 42
    for changes in (
        {"report_id": "界" * 43},
        {"version": '"' * 64},
        {"title": "x" * 511},
        {"parameters": definition.parameters * 9},
    ):
        with pytest.raises(d.DefinitionError):
            replace(definition, **changes)
    with pytest.raises(d.DefinitionError):
        replace(definition, parameters=cast(tuple[d.ParameterDefinition, ...], []))
    with pytest.raises(d.DefinitionError):
        d.ParameterDefinition("message", "text", False, "界" * 171)


def test_whole_series_metadata_respects_one_kibibyte() -> None:
    with pytest.raises(d.DefinitionError) as error:
        d.SeriesSelection(
            "i" * 126,
            "l" * 510,
            "f" * 126,
            SemanticRole.EXTERNAL_RESULT,
            ValueFormat("datetime", date_pattern="p" * 126),
        )
    assert error.value.issue.code == "limit"


def test_scalar_text_parameter_can_be_empty_without_being_an_identifier() -> None:
    parameter = d.ParameterDefinition("optional_note", "text", False, "", ("", "literal"))
    assert d.check_parameter(parameter, "") == ""
    assert d.ParameterDefinition("note", "text", False, "界" * 170).default == "界" * 170


def test_combined_selection_and_parameter_limits_accept_exact_boundary(
    definition: d.ReportDefinition,
) -> None:
    fields = (
        FieldRequirement("period", "text", nullable=False),
        *(FieldRequirement(f"f{index}", "int64") for index in range(61)),
    )
    source = d.DatasetRef("positions", fields)
    columns = tuple(
        d.ColumnSelection(f"f{index}", SemanticRole.EXTERNAL_RESULT, ValueFormat("int64"))
        for index in range(61)
    )
    chart = d.LineChartDefinition(
        "chart",
        source,
        "period",
        tuple(
            d.SeriesSelection(
                f"s{index}",
                "Supplied",
                f"f{index}",
                SemanticRole.EXTERNAL_RESULT,
                ValueFormat("int64"),
            )
            for index in range(3)
        ),
    )
    accepted = replace(
        definition,
        table=d.TableDefinition("table", source, columns[:60]),
        chart=chart,
        parameters=definition.parameters
        + tuple(d.ParameterDefinition(f"p{index}", "int64", False, 0) for index in range(14)),
        title="x" * 510,
    )
    assert len(accepted.parameters) == 16
    with pytest.raises(d.DefinitionError):
        replace(accepted, table=replace(accepted.table, columns=columns))
    with pytest.raises(d.DefinitionError):
        replace(
            accepted,
            parameters=accepted.parameters + (d.ParameterDefinition("extra", "bool", False),),
        )


def test_metric_requirements_intersect_types_shape_unit_and_nullability(
    definition: d.ReportDefinition,
) -> None:
    table = d.TableDefinition(
        "table",
        d.MetricRef("returns", None, ("decimal", "int64")),
        (d.ColumnSelection("value", SemanticRole.EXTERNAL_RESULT, ValueFormat("decimal", 2)),),
    )
    source = d.MetricRef("returns", "%", ("decimal",), "series", False)
    chart = replace(
        definition.chart,
        source=source,
        category_field="label",
        series=(replace(definition.chart.series[0], field="value"),),
    )
    changed = replace(definition, table=table, chart=chart)
    requirements = p.requirements_for(changed, (("title", "A"), ("feed", "positions")))
    assert requirements.datasets == ()
    assert requirements.metrics == (
        MetricRequirement("returns", "%", ("decimal",), "series", False),
    )
    for incompatible in (
        replace(table.source, kinds=("text",)),
        replace(table.source, unit="USD"),
        replace(table.source, shape="scalar"),
    ):
        with pytest.raises(d.DefinitionError) as error:
            p.requirements_for(
                replace(changed, table=replace(table, source=incompatible)),
                (("title", "A"), ("feed", "positions")),
            )
        assert error.value.issue.code == "constraint_conflict"
