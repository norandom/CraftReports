"""Pure typed validation failures for producer publications."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from craftreport.data.values import Dataset, Field, ImportedMetric, Scalar, Snapshot

type Location = tuple[str | int, ...]
type PublicationCode = Literal[
    "invalid_type",
    "required",
    "precision",
    "nullability",
    "shape",
    "duplicate_name",
    "invalid_key",
    "duplicate_key",
    "invalid_version",
    "invalid_digest",
    "invalid_datetime",
]


@dataclass(frozen=True, slots=True)
class PublicationIssue:
    location: Location
    code: PublicationCode


class PublicationValidationError(ValueError):
    def __init__(self, issue: PublicationIssue) -> None:
        self.issue = issue
        super().__init__(f"{issue.code} at {issue.location}")


def require(condition: bool, code: PublicationCode, location: Location) -> None:
    if not condition:
        raise PublicationValidationError(PublicationIssue(location, code))


def require_text(value: object, location: Location, *, empty: bool = False) -> None:
    require(type(value) is str, "invalid_type", location)
    require(empty or bool(str(value).strip()), "required", location)


def require_tuple(value: object, location: Location) -> None:
    require(type(value) is tuple, "invalid_type", location)


def require_unique(values: tuple[str, ...], location: Location) -> None:
    seen: set[str] = set()
    for index, value in enumerate(values):
        require_text(value, (*location, index))
        require(value not in seen, "duplicate_name", (*location, index))
        seen.add(value)


def validate_datetime(value: object, location: Location) -> None:
    require(type(value) is datetime, "invalid_type", location)
    assert isinstance(value, datetime)
    require(type(value.tzinfo) in (timezone, ZoneInfo), "invalid_datetime", location)
    require(value.utcoffset() is not None, "invalid_datetime", location)


def validate_datetime_lexeme(value: str, location: Location) -> None:
    """Guard the advertised microsecond profile before any datetime parser runs.

    The boundary codec parses the guarded string and normalizes UTC separately.
    """
    require_text(value, location)
    fractions = re.findall(r"[.,](\d+)", value)
    require(all(len(part) <= 6 for part in fractions), "precision", location)
    pattern = (
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:(?P<seconds>[0-5]\d)"
        r"(?:\.\d{1,6})?(?:Z|[+-](?P<hours>[01]\d|2[0-3]):[0-5]\d)"
    )
    require(re.fullmatch(pattern, value) is not None, "invalid_datetime", location)


def validate_field(field: Field) -> None:
    require_text(field.name, ("fields", "name"))
    location: Location = ("fields", field.name)
    require_text(field.label, (*location, "label"), empty=True)
    require(
        type(field.kind) is str
        and field.kind in ("text", "bool", "int64", "decimal", "date", "datetime"),
        "invalid_type",
        (*location, "kind"),
    )
    require(type(field.nullable) is bool, "invalid_type", (*location, "nullable"))
    if field.unit is not None:
        require_text(field.unit, (*location, "unit"))
    if field.kind == "decimal":
        precision, scale = field.precision, field.scale
        require(type(precision) is int and type(scale) is int, "precision", location)
        assert precision is not None and scale is not None
        require(1 <= precision <= 38 and 0 <= scale <= precision, "precision", location)
    else:
        require(field.precision is None and field.scale is None, "precision", location)


def validate_decimal(value: Decimal, field: Field, location: Location) -> None:
    require(value.is_finite(), "precision", location)
    parts = value.as_tuple()
    exponent = parts.exponent
    assert isinstance(exponent, int)
    assert field.precision is not None and field.scale is not None
    digits = list(parts.digits)
    while digits and digits[-1] == 0 and exponent < -field.scale:
        digits.pop()
        exponent += 1
    if not any(digits):
        return
    require(exponent >= -field.scale, "precision", location)
    require(max(len(digits) + exponent, 0) + field.scale <= field.precision, "precision", location)


def validate_scalar(value: Scalar, field: Field, location: Location) -> None:
    if value is None:
        require(field.nullable, "nullability", location)
        return
    expected = {
        "text": str,
        "bool": bool,
        "int64": int,
        "decimal": Decimal,
        "date": date,
        "datetime": datetime,
    }
    require(type(value) is expected[field.kind], "invalid_type", location)
    if field.kind == "int64":
        assert isinstance(value, int)
        require(-(2**63) <= value < 2**63, "precision", location)
    elif field.kind == "decimal":
        assert isinstance(value, Decimal)
        validate_decimal(value, field, location)
    elif field.kind == "datetime":
        assert isinstance(value, datetime)
        validate_datetime(value, location)


def key_component(value: Scalar) -> Scalar:
    """Compare datetime keys by their UTC instant without changing retained data.

    Integer microseconds avoid floating timestamps and UTC conversion overflow at
    calendar bounds. Each key position has one declared type, so this internal
    comparison representation cannot mix datetime and producer integer fields.
    """
    if isinstance(value, datetime):
        delta = value - datetime(1970, 1, 1, tzinfo=UTC)
        return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    return value


def validate_dataset(dataset: Dataset) -> None:
    from craftreport.data.values import Field

    require_text(dataset.name, ("datasets", "name"))
    location: Location = ("datasets", dataset.name)
    require_text(dataset.label, (*location, "label"), empty=True)
    for name in ("source_ref", "producer_id"):
        require_text(getattr(dataset, name), (*location, name))
    if dataset.source_version is not None:
        require_text(dataset.source_version, (*location, "source_version"))
    for name in ("fields", "rows", "keys"):
        require_tuple(getattr(dataset, name), (*location, name))
    for index, field in enumerate(dataset.fields):
        require(type(field) is Field, "invalid_type", (*location, "fields", index))
    names = tuple(field.name for field in dataset.fields)
    require_unique(names, (*location, "fields"))
    require_unique(dataset.keys, (*location, "keys"))
    for index, key in enumerate(dataset.keys):
        require(key in names, "invalid_key", (*location, "keys", index))
    key_indexes = tuple(names.index(key) for key in dataset.keys)
    seen: set[tuple[Scalar, ...]] = set()
    for index, row in enumerate(dataset.rows):
        row_location = (*location, "rows", index)
        require_tuple(row, row_location)
        require(len(row) == len(dataset.fields), "shape", row_location)
        for field, value in zip(dataset.fields, row, strict=True):
            validate_scalar(value, field, (*row_location, field.name))
        if key_indexes:
            key_values = tuple(key_component(row[i]) for i in key_indexes)
            require(None not in key_values, "invalid_key", (*row_location, "keys"))
            require(key_values not in seen, "duplicate_key", (*row_location, "keys"))
            seen.add(key_values)


def validate_metric(metric: ImportedMetric) -> None:
    from craftreport.data.values import Field

    require_text(metric.identity, ("metrics", "identity"))
    location: Location = ("metrics", metric.identity)
    for name in ("unit", "source_ref", "producer_id", "method_version"):
        require_text(getattr(metric, name), (*location, name))
    require(metric.period is not None or metric.as_of is not None, "required", location)
    if metric.period is not None:
        require_text(metric.period, (*location, "period"))
    if metric.as_of is not None:
        validate_datetime(metric.as_of, (*location, "as_of"))
    require(
        type(metric.shape) is str and metric.shape in ("scalar", "series"),
        "shape",
        (*location, "shape"),
    )
    require(type(metric.value_schema) is Field, "invalid_type", (*location, "value_schema"))
    for name in ("labels", "values", "external_evidence"):
        require_tuple(getattr(metric, name), (*location, name))
    for name in ("labels", "external_evidence"):
        for index, text in enumerate(getattr(metric, name)):
            require_text(text, (*location, name, index), empty=name == "labels")
    if metric.shape == "scalar":
        require(not metric.labels and len(metric.values) == 1, "shape", location)
    else:
        require(len(metric.labels) == len(metric.values), "shape", location)
    for index, value in enumerate(metric.values):
        validate_scalar(value, metric.value_schema, (*location, "values", index))


def validate_snapshot_ref(feed_id: str, producer_version: int, content_digest: str) -> None:
    require_text(feed_id, ("feed_id",))
    require(
        type(producer_version) is int and 1 <= producer_version < 2**63,
        "invalid_version",
        ("producer_version",),
    )
    require(
        type(content_digest) is str and re.fullmatch(r"[0-9a-f]{64}", content_digest) is not None,
        "invalid_digest",
        ("content_digest",),
    )


def validate_snapshot(snapshot: Snapshot) -> None:
    from craftreport.data.values import Dataset, ImportedMetric

    require(
        type(snapshot.schema_version) is str and snapshot.schema_version == "1",
        "invalid_version",
        ("schema_version",),
    )
    validate_snapshot_ref(snapshot.feed_id, snapshot.producer_version, snapshot.content_digest)
    require_tuple(snapshot.datasets, ("datasets",))
    require_tuple(snapshot.metrics, ("metrics",))
    for index, dataset in enumerate(snapshot.datasets):
        require(type(dataset) is Dataset, "invalid_type", ("datasets", index))
    for index, metric in enumerate(snapshot.metrics):
        require(type(metric) is ImportedMetric, "invalid_type", ("metrics", index))
    require_unique(tuple(dataset.name for dataset in snapshot.datasets), ("datasets",))
    require_unique(tuple(metric.identity for metric in snapshot.metrics), ("metrics",))
    for name in ("observation_time", "generation_time", "received_at", "accepted_at"):
        value: datetime | None = getattr(snapshot, name)
        if value is None and name in ("observation_time", "generation_time"):
            continue
        validate_datetime(value, (name,))
