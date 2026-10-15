"""Declared per-binding requirements over accepted producer snapshots."""

from dataclasses import dataclass
from typing import Literal, get_args

from craftreport.data.values import Dataset, ImportedMetric, ScalarKind, Snapshot

type BindingCode = Literal[
    "missing_dataset",
    "missing_field",
    "missing_metric",
    "incompatible_type",
    "incompatible_unit",
    "incompatible_shape",
    "nullability",
]


@dataclass(frozen=True, slots=True)
class FieldRequirement:
    name: str
    kind: ScalarKind
    unit: str | None = None
    nullable: bool = True

    def __post_init__(self) -> None:
        _validate_constraint(self.name, self.unit, self.nullable)
        if type(self.kind) is not str or self.kind not in get_args(ScalarKind.__value__):
            raise ValueError("field requirement needs a declared scalar kind")


@dataclass(frozen=True, slots=True)
class DatasetRequirement:
    name: str
    fields: tuple[FieldRequirement, ...]

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name.strip():
            raise ValueError("dataset requirement needs a name")
        if type(self.fields) is not tuple or any(
            type(f) is not FieldRequirement for f in self.fields
        ):
            raise ValueError("fields must be a tuple of FieldRequirement values")


@dataclass(frozen=True, slots=True)
class MetricRequirement:
    identity: str
    unit: str | None = None
    kinds: tuple[ScalarKind, ...] = ()
    shape: Literal["scalar", "series"] | None = None
    nullable: bool = True

    def __post_init__(self) -> None:
        _validate_constraint(self.identity, self.unit, self.nullable)
        if type(self.kinds) is not tuple or any(
            type(kind) is not str or kind not in get_args(ScalarKind.__value__)
            for kind in self.kinds
        ):
            raise ValueError("metric kinds must be a tuple of declared scalar kinds")
        if self.shape is not None and (
            type(self.shape) is not str or self.shape not in ("scalar", "series")
        ):
            raise ValueError("metric shape must be scalar, series or None")


@dataclass(frozen=True, slots=True)
class InputRequirements:
    datasets: tuple[DatasetRequirement, ...]
    metrics: tuple[MetricRequirement, ...]

    def __post_init__(self) -> None:
        if type(self.datasets) is not tuple or any(
            type(value) is not DatasetRequirement for value in self.datasets
        ):
            raise ValueError("datasets must be a tuple of DatasetRequirement values")
        if type(self.metrics) is not tuple or any(
            type(value) is not MetricRequirement for value in self.metrics
        ):
            raise ValueError("metrics must be a tuple of MetricRequirement values")


@dataclass(frozen=True, slots=True)
class BindingIssue:
    location: tuple[str | int, ...]
    code: BindingCode

    def __post_init__(self) -> None:
        if type(self.location) is not tuple or any(
            type(part) not in (str, int) for part in self.location
        ):
            raise ValueError("issue location must be a tuple of text or integer components")
        if type(self.code) is not str or self.code not in get_args(BindingCode.__value__):
            raise ValueError("unknown binding issue code")


def _validate_constraint(identity: str, unit: str | None, nullable: bool) -> None:
    if type(identity) is not str or not identity.strip():
        raise ValueError("input requirement needs an identity")
    if unit is not None and (type(unit) is not str or not unit.strip()):
        raise ValueError("required unit must be nonempty text or None")
    if type(nullable) is not bool:
        raise ValueError("required nullability must be a boolean")


def _field_issues(dataset: Dataset, requirement: FieldRequirement) -> list[BindingIssue]:
    location = ("datasets", dataset.name, "fields", requirement.name)
    indexed_field = next(
        (
            (index, field)
            for index, field in enumerate(dataset.fields)
            if field.name == requirement.name
        ),
        None,
    )
    if indexed_field is None:
        return [BindingIssue(location, "missing_field")]
    index, field = indexed_field
    issues: list[BindingIssue] = []
    if field.kind != requirement.kind:
        issues.append(BindingIssue((*location, "kind"), "incompatible_type"))
    if requirement.unit is not None and field.unit != requirement.unit:
        issues.append(BindingIssue((*location, "unit"), "incompatible_unit"))
    if not requirement.nullable:
        if field.nullable:
            issues.append(BindingIssue((*location, "nullable"), "nullability"))
        issues.extend(
            BindingIssue(("datasets", dataset.name, "rows", row_index, field.name), "nullability")
            for row_index, row in enumerate(dataset.rows)
            if row[index] is None
        )
    return issues


def _metric_issues(metric: ImportedMetric, requirement: MetricRequirement) -> list[BindingIssue]:
    location = ("metrics", metric.identity)
    issues: list[BindingIssue] = []
    if requirement.kinds and metric.value_schema.kind not in requirement.kinds:
        issues.append(BindingIssue((*location, "value_schema", "kind"), "incompatible_type"))
    if requirement.unit is not None and metric.unit != requirement.unit:
        issues.append(BindingIssue((*location, "unit"), "incompatible_unit"))
    if requirement.shape is not None and metric.shape != requirement.shape:
        issues.append(BindingIssue((*location, "shape"), "incompatible_shape"))
    if not requirement.nullable:
        if metric.value_schema.nullable:
            issues.append(BindingIssue((*location, "value_schema", "nullable"), "nullability"))
        issues.extend(
            BindingIssue((*location, "values", index), "nullability")
            for index, value in enumerate(metric.values)
            if value is None
        )
    return issues


def check_completeness(
    snapshot: Snapshot, requirements: InputRequirements
) -> tuple[BindingIssue, ...]:
    """Return source locations that prevent this accepted snapshot serving a binding.

    Requirements are supplied by the consumer's declarations; source samples
    never strengthen or weaken them. Checks preserve declaration and row order.
    """
    datasets = {dataset.name: dataset for dataset in snapshot.datasets}
    metrics = {metric.identity: metric for metric in snapshot.metrics}
    issues: list[BindingIssue] = []
    for required_dataset in requirements.datasets:
        dataset = datasets.get(required_dataset.name)
        if dataset is None:
            issues.append(BindingIssue(("datasets", required_dataset.name), "missing_dataset"))
        else:
            for field in required_dataset.fields:
                issues.extend(_field_issues(dataset, field))
    for required_metric in requirements.metrics:
        metric = metrics.get(required_metric.identity)
        if metric is None:
            issues.append(BindingIssue(("metrics", required_metric.identity), "missing_metric"))
        else:
            issues.extend(_metric_issues(metric, required_metric))
    return tuple(issues)
