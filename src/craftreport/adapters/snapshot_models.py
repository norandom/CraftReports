"""Closed snapshot transport schemas and advertised bounded publication profile."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from pydantic import BeforeValidator, PlainSerializer, ValidateAs
from pydantic import Field as WireField

from craftreport.adapters.canonical import WireFailure
from craftreport.adapters.validation import StrictWireModel, construct, model_shape
from craftreport.application.ports import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import JsonObject, OperationLimits
from craftreport.contracts.values import JsonValue
from craftreport.data.validation import validate_datetime, validate_datetime_lexeme
from craftreport.data.values import Dataset, Field, ImportedMetric, ScalarKind, SnapshotRef
from craftreport.runtime.publication import (
    LatestRequest,
    LatestSelection,
    PublicationResult,
    SnapshotSummary,
)

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


def reference_object(value: SnapshotRef) -> JsonObject:
    return {**asdict(value), "producer_version": str(value.producer_version)}


def reference_value(value: SnapshotRefWire) -> SnapshotRef:
    return construct(
        SnapshotRef, value, {"producer_version": int(getattr(value, "producer_version"))}
    )


def _reference_input(value: object) -> object:
    return reference_object(value) if isinstance(value, SnapshotRef) else value


type Reference = Annotated[
    SnapshotRef,
    ValidateAs(SnapshotRefWire, reference_value),
    BeforeValidator(_reference_input),
    PlainSerializer(reference_object, return_type=dict[str, JsonValue]),
]


def _service_time(value: object) -> datetime:
    if isinstance(value, str):
        validate_datetime_lexeme(value, ())
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("Service timestamp required")
    validate_datetime(value, ())
    return value.astimezone(UTC)


type ServiceTime = Annotated[
    datetime,
    BeforeValidator(_service_time),
    PlainSerializer(
        lambda v: v.isoformat(timespec="microseconds").replace("+00:00", "Z"), return_type=str
    ),
]


class SummaryWire(
    model_shape(
        SnapshotSummary,
        {"reference": Reference, "received_at": ServiceTime, "accepted_at": ServiceTime},
    )
):
    pass


def _summary_input(value: object) -> object:
    return (
        {f.name: getattr(value, f.name) for f in fields(value)}
        if isinstance(value, SnapshotSummary)
        else value
    )


def _summary_object(value: SnapshotSummary) -> JsonObject:
    return cast(
        JsonObject, SummaryWire.model_validate(_summary_input(value)).model_dump(mode="json")
    )


type Summary = Annotated[
    SnapshotSummary,
    ValidateAs(SummaryWire, lambda v: construct(SnapshotSummary, v, {})),
    BeforeValidator(_summary_input),
    PlainSerializer(_summary_object, return_type=dict[str, JsonValue]),
]


class PublicationResultWire(
    model_shape(
        PublicationResult,
        {
            "requested": Reference,
            "retained": Reference | None,
            "latest_accepted": Reference,
            "summary": Summary | None,
        },
    )
):
    pass


class LatestRequestWire(model_shape(LatestRequest, {})):
    pass


class LatestSelectionWire(
    model_shape(
        LatestSelection, {"latest_accepted": Reference, "highest_complete": Reference | None}
    )
):
    pass


class MissingWire(model_shape(Missing, {}, defaults={"kind": ...})):
    pass


class UnavailableWire(model_shape(ServiceUnavailable, {}, defaults={"kind": ...})):
    pass


class ConflictWire(model_shape(VersionConflict, {}, defaults={"kind": ...})):
    pass


type MissingValue = Annotated[
    Missing, ValidateAs(MissingWire, lambda v: Missing()), PlainSerializer(asdict)
]
type UnavailableValue = Annotated[
    ServiceUnavailable,
    ValidateAs(UnavailableWire, lambda v: ServiceUnavailable(getattr(v, "service"))),
    PlainSerializer(asdict),
]
type ConflictValue = Annotated[
    VersionConflict,
    ValidateAs(
        ConflictWire, lambda v: VersionConflict(getattr(v, "expected"), getattr(v, "authoritative"))
    ),
    PlainSerializer(asdict),
]
