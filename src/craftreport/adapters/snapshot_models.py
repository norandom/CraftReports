"""Closed snapshot transport schemas and advertised bounded publication profile."""

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Annotated, Literal, cast

from pydantic import Field as WireField

from craftreport.adapters.canonical import WireFailure
from craftreport.adapters.validation import StrictWireModel, model_shape
from craftreport.contracts import JsonObject, OperationLimits
from craftreport.contracts.values import JsonValue
from craftreport.data.values import Dataset, Field, ImportedMetric, ScalarKind, SnapshotRef

type Text = str
type ScalarWire = Text | bool | None
type VersionWire = Annotated[str, WireField(pattern=r"^[1-9][0-9]{0,18}$")]


class FieldWire(
    model_shape(
        Field,
        {
            "name": Text,
            "label": Text,
            "unit": Text | None,
            "precision": Annotated[int | None, WireField(ge=1, le=38)],
            "scale": Annotated[int | None, WireField(ge=0, le=38)],
        },
    )
):
    pass


class DatasetWire(
    model_shape(
        Dataset,
        {
            "name": Text,
            "label": Text,
            "fields": list[FieldWire],
            "rows": list[list[ScalarWire]],
            "keys": list[Text],
            "source_ref": Text,
            "producer_id": Text,
            "source_version": Text | None,
        },
        defaults={"source_version": None},
    )
):
    pass


class MetricWire(
    model_shape(
        ImportedMetric,
        {
            "identity": Text,
            "unit": Text,
            "period": Text | None,
            "as_of": Text | None,
            "source_ref": Text,
            "producer_id": Text,
            "method_version": Text,
            "value_schema": FieldWire,
            "labels": list[Text],
            "values": list[ScalarWire],
            "external_evidence": list[Text],
        },
        defaults={"period": None, "as_of": None},
    )
):
    pass


class SnapshotRefWire(
    model_shape(
        SnapshotRef,
        {
            "producer_version": VersionWire,
            "content_digest": Annotated[str, WireField(pattern=r"^[0-9a-f]{64}$")],
        },
    )
):
    pass


class PublicationWire(StrictWireModel):
    schema_version: Literal["1"]
    feed_id: Text
    producer_version: VersionWire
    datasets: list[DatasetWire]
    metrics: list[MetricWire]
    observation_time: Text | None = None
    generation_time: Text | None = None


class SnapshotWire(PublicationWire):
    content_digest: Annotated[str, WireField(pattern=r"^[0-9a-f]{64}$")]
    received_at: Text
    accepted_at: Text


class ParameterWire(StrictWireModel):
    kind: ScalarKind | Literal["null"]
    value: ScalarWire


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 1_048_576
    max_nesting_depth: int = 32
    max_datasets: int = 16
    max_fields: int = 128
    max_rows: int = 10_000
    max_cells: int = 100_000
    max_metrics: int = 128
    max_metric_points: int = 10_000
    max_string_length: int = 4096

    def __post_init__(self) -> None:
        for field in fields(self):
            value: int = getattr(self, field.name)
            if type(value) is not int or not 1 <= value <= cast(int, field.default):
                raise ValueError(f"{field.name} can only lower the advertised default")

    def operation_limits(self) -> OperationLimits:
        return OperationLimits(self.max_input_bytes, self.max_nesting_depth, self.max_output_bytes)


def check_count(count: int, maximum: int, name: str, location: tuple[str | int, ...] = ()) -> None:
    if count > maximum:
        raise WireFailure("limit_exceeded", limit=name, location=location)


def _check_strings(value: JsonValue, maximum: int, location: tuple[str | int, ...] = ()) -> None:
    if isinstance(value, str):
        check_count(len(value), maximum, "max_string_length", location)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            _check_strings(item, maximum, (*location, key))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _check_strings(item, maximum, (*location, index))


def check_shape(content: JsonObject, limits: SnapshotLimits) -> None:
    """Cardinality totals complement the library's closed field/type schemas."""
    datasets = cast(tuple[JsonObject, ...], content["datasets"])
    metrics = cast(tuple[JsonObject, ...], content["metrics"])
    check_count(len(datasets), limits.max_datasets, "max_datasets", ("datasets",))
    check_count(len(metrics), limits.max_metrics, "max_metrics", ("metrics",))
    rows = cells = 0
    for data in datasets:
        fields = cast(tuple[JsonValue, ...], data["fields"])
        values = cast(tuple[tuple[JsonValue, ...], ...], data["rows"])
        location = ("datasets", str(data["name"]))
        check_count(len(fields), limits.max_fields, "max_fields", location)
        rows += len(values)
        cells += sum(len(row) for row in values)
    check_count(rows, limits.max_rows, "max_rows", ("datasets",))
    check_count(cells, limits.max_cells, "max_cells", ("datasets",))
    points = sum(len(cast(tuple[JsonValue, ...], item["values"])) for item in metrics)
    check_count(points, limits.max_metric_points, "max_metric_points", ("metrics",))
    _check_strings(content, limits.max_string_length)
