"""Pure parameter resolution and declared requirements; no app effects."""

from collections.abc import Callable
from dataclasses import replace

from craftreport.contracts.pins import VersionPin
from craftreport.data.requirements import (
    DatasetRequirement,
    FieldRequirement,
    InputRequirements,
    MetricRequirement,
)
from craftreport.data.values import Scalar
from craftreport.reporting.definitions import (
    DatasetRef,
    Location,
    ParameterRef,
    ParameterValue,
    ReportDefinition,
    check_parameter,
    frozen,
    require,
    text,
)


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
