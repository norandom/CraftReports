"""Pure parameter resolution and declared requirements; no app effects."""

from collections.abc import Callable
from dataclasses import replace

from craftreport.contracts.pins import VersionPin
from craftreport.data.requirements import (
    DatasetRequirement,
    FieldRequirement,
    InputRequirements,
    MetricRequirement,
    check_completeness,
)
from craftreport.data.values import Field, ImportedMetric, Scalar, Snapshot, SnapshotRef
from craftreport.reporting.definitions import (
    DatasetRef,
    DefinitionError,
    DefinitionIssue,
    LineChartDefinition,
    Location,
    MetricRef,
    ParameterRef,
    ParameterValue,
    ReportDefinition,
    TableDefinition,
    check_parameter,
    frozen,
    require,
    text,
)
from craftreport.reporting.prepared import (
    PreparationFailure,
    PreparedColumn,
    PreparedLineChart,
    PreparedReport,
    PreparedSeries,
    PreparedTable,
    ResolvedPack,
)
from craftreport.themes.values import ResolvedTheme


def _reference(
    value: str | ParameterRef, values: dict[str, Scalar], location: Location, maximum: int = 128
) -> str:
    resolved = values.get(value.name) if type(value) is ParameterRef else value
    require(type(resolved) is str, "required", location)
    assert type(resolved) is str
    text(resolved, location, maximum)
    return resolved


def resolve_parameters(
    definition: ReportDefinition, supplied: tuple[ParameterValue, ...]
) -> tuple[tuple[str, Scalar], ...]:
    frozen(supplied, ("parameters",))
    require(
        type(supplied) is tuple and all(type(p) is ParameterValue for p in supplied),
        "invalid_type",
        ("parameters",),
    )
    declared = {parameter.name: parameter for parameter in definition.parameters}
    selected: dict[str, Scalar] = {}
    for parameter in supplied:
        location = ("parameters", parameter.name)
        require(parameter.name in declared, "unsupported", location)
        require(parameter.name not in selected, "duplicate", location)
        selected[parameter.name] = parameter.value
    resolved: dict[str, Scalar] = {}
    for parameter in definition.parameters:
        value = selected.get(parameter.name, parameter.default)
        if parameter.name not in selected and value is None:
            require(not parameter.required, "required", ("parameters", parameter.name))
            continue
        resolved[parameter.name] = check_parameter(parameter, value)
    _reference(definition.title, resolved, ("title",), 512)
    for name, source in (("table", definition.table.source), ("chart", definition.chart.source)):
        _reference(
            source.name if isinstance(source, DatasetRef) else source.identity,
            resolved,
            (name, "source"),
        )
    return tuple(resolved.items())


def _merge_field(
    prior: FieldRequirement, incoming: FieldRequirement, location: Location
) -> FieldRequirement:
    require(
        prior.kind == incoming.kind
        and (prior.unit is None or incoming.unit is None or prior.unit == incoming.unit),
        "constraint_conflict",
        location,
    )
    return replace(
        prior, unit=prior.unit or incoming.unit, nullable=prior.nullable and incoming.nullable
    )


def _merge_metric(
    prior: MetricRequirement, incoming: MetricRequirement, location: Location
) -> MetricRequirement:
    require(
        (prior.unit is None or incoming.unit is None or prior.unit == incoming.unit)
        and (prior.shape is None or incoming.shape is None or prior.shape == incoming.shape),
        "constraint_conflict",
        location,
    )
    kinds = (
        tuple(kind for kind in prior.kinds if kind in incoming.kinds)
        if (prior.kinds and incoming.kinds)
        else prior.kinds or incoming.kinds
    )
    require(not (prior.kinds and incoming.kinds) or bool(kinds), "constraint_conflict", location)
    return replace(
        prior,
        unit=prior.unit or incoming.unit,
        kinds=kinds,
        shape=prior.shape or incoming.shape,
        nullable=prior.nullable and incoming.nullable,
    )


def requirements_for(
    definition: ReportDefinition, parameters: tuple[tuple[str, Scalar], ...]
) -> InputRequirements:
    values = dict(
        resolve_parameters(
            definition, tuple(ParameterValue(name, value) for name, value in parameters)
        )
    )
    datasets: dict[str, DatasetRequirement] = {}
    metrics: dict[str, MetricRequirement] = {}
    for name, source in (("table", definition.table.source), ("chart", definition.chart.source)):
        location = (name, "source")
        if isinstance(source, DatasetRef):
            identity = _reference(source.name, values, location)
            fields = (
                {field.name: field for field in datasets[identity].fields}
                if identity in datasets
                else {}
            )
            for field in source.fields:
                fields[field.name] = (
                    _merge_field(fields[field.name], field, (*location, "fields", field.name))
                    if field.name in fields
                    else field
                )
            datasets[identity] = DatasetRequirement(identity, tuple(fields.values()))
        else:
            identity = _reference(source.identity, values, location)
            incoming = MetricRequirement(
                identity, source.unit, source.kinds, source.shape, source.nullable
            )
            metrics[identity] = (
                _merge_metric(metrics[identity], incoming, location)
                if identity in metrics
                else incoming
            )
    return InputRequirements(tuple(datasets.values()), tuple(metrics.values()))


def validate_template(
    definition: ReportDefinition, template: VersionPin, identify: Callable[[ReportDefinition], str]
) -> ReportDefinition:
    """Verify selected bytes using the injected existing canonical identity."""
    require(
        (definition.report_id, definition.version) == (template.identity, template.version)
        and identify(definition) == template.content_digest,
        "template_mismatch",
        ("template",),
    )
    return definition


type SourceColumns = dict[str, tuple[Field, tuple[Scalar, ...]]]


def _source_columns(
    source: DatasetRef | MetricRef,
    parameters: dict[str, Scalar],
    snapshot: Snapshot,
) -> tuple[SourceColumns, ImportedMetric | None]:
    if isinstance(source, DatasetRef):
        name = _reference(source.name, parameters, ("source",))
        dataset = next(d for d in snapshot.datasets if d.name == name)
        return {
            field.name: (field, tuple(row[i] for row in dataset.rows))
            for i, field in enumerate(dataset.fields)
        }, None
    name = _reference(source.identity, parameters, ("source",))
    metric = next(m for m in snapshot.metrics if m.identity == name)
    labels = (metric.identity,) if metric.shape == "scalar" else metric.labels
    return {
        "label": (Field("label", "Label", "text", False), labels),
        "value": (metric.value_schema, metric.values),
    }, metric


def _table(table: TableDefinition, columns: SourceColumns, theme: ResolvedTheme) -> PreparedTable:
    selected = tuple(columns[c.field] for c in table.columns)
    rows = tuple(zip(*(values for _, values in selected), strict=True))
    return PreparedTable(
        table.identity,
        tuple(
            PreparedColumn(
                field,
                selection.display_label if selection.display_label is not None else field.label,
                selection.role,
                selection.format,
            )
            for selection, (field, _) in zip(table.columns, selected, strict=True)
        ),
        rows,
        None if rows else theme.empty_note,
        table.null_text,
        table.long_labels,
    )


def _chart(chart: LineChartDefinition, columns: SourceColumns) -> PreparedLineChart:
    category, values = columns[chart.category_field]
    series = tuple(
        PreparedSeries(
            s.identity, s.label, columns[s.field][0], columns[s.field][1], s.role, s.format
        )
        for s in chart.series
    )
    return PreparedLineChart(chart.identity, category, values, series, chart.null_behavior)


def prepare(
    definition: ReportDefinition,
    parameters: tuple[ParameterValue, ...],
    snapshot: Snapshot,
    pack: ResolvedPack,
    theme: ResolvedTheme,
    identify: Callable[[PreparedReport], str],
) -> PreparedReport | PreparationFailure:
    if definition != pack.definition:
        return PreparationFailure(
            "invalid_definition", (DefinitionIssue(("definition",), "template_mismatch"),)
        )
    if theme.version_pin != pack.theme.version_pin:
        return PreparationFailure(
            "invalid_definition", (DefinitionIssue(("theme",), "template_mismatch"),)
        )
    try:
        resolved = resolve_parameters(definition, parameters)
    except DefinitionError as error:
        return PreparationFailure("invalid_parameter", (error.issue,))
    try:
        requirements = requirements_for(definition, resolved)
    except DefinitionError as error:
        return PreparationFailure("invalid_definition", (error.issue,))
    issues = check_completeness(snapshot, requirements)
    if issues:
        return PreparationFailure("incomplete_binding", issues)
    table_columns, table_metric = _source_columns(definition.table.source, dict(resolved), snapshot)
    chart_columns, chart_metric = _source_columns(definition.chart.source, dict(resolved), snapshot)
    metrics = {m.identity: m for m in (table_metric, chart_metric) if m is not None}
    report = PreparedReport(
        "1",
        definition.report_id,
        _reference(definition.title, dict(resolved), ("title",), 512),
        pack.definition_pin,
        pack.template,
        theme.version_pin,
        pack.pin,
        SnapshotRef(snapshot.feed_id, snapshot.producer_version, snapshot.content_digest),
        resolved,
        (_table(definition.table, table_columns, theme),),
        (_chart(definition.chart, chart_columns),),
        theme,
        definition.required_capabilities,
        tuple(metrics.values()),
        definition.compliance_statement,
        definition.release_policy,
        "",
        _identify=identify,
    )
    return report
