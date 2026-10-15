"""Exact shared scalar encoding and snapshot boundary codecs."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, cast

from pydantic import ValidationError

from craftreport.adapters.canonical import WireFailure, canonical_bytes
from craftreport.adapters.snapshot_models import (
    ParameterWire,
    PublicationWire,
    SnapshotWire,
    check_count,
    check_shape,
)
from craftreport.adapters.snapshot_models import (
    SnapshotLimits as SnapshotLimits,
)
from craftreport.adapters.validation import PydanticCodec
from craftreport.contracts import JsonObject
from craftreport.contracts.values import JsonValue, freeze_object
from craftreport.data.validation import (
    PublicationValidationError,
    require_unique,
    validate_datetime,
    validate_datetime_lexeme,
    validate_scalar,
)
from craftreport.data.values import Dataset, Field, ImportedMetric, Scalar, ScalarKind, Snapshot


def _timestamp(value: datetime) -> str:
    validate_datetime(value, ("datetime",))
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _datetime(value: JsonValue, location: tuple[str | int, ...] = ()) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WireFailure("invalid_type", location=location)
    validate_datetime_lexeme(value, location)
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except (ValueError, OverflowError):
        raise WireFailure("invalid_datetime", location=location) from None


def encode_scalar(value: Scalar) -> JsonValue:
    if type(value) is datetime:
        return _timestamp(value)
    if type(value) is date:
        return value.isoformat()
    if type(value) is Decimal:
        if not value.is_finite() or len(value.as_tuple().digits) > 38:
            raise WireFailure("precision")
        exponent = cast(int, value.as_tuple().exponent)
        if abs(exponent) > 38 or value.adjusted() >= 38:
            raise WireFailure("precision")
        return format(value.copy_abs() if value.is_zero() else value, "f")
    if type(value) is int:
        if not -(2**63) <= value < 2**63:
            raise WireFailure("precision")
        return str(value)
    if isinstance(value, str):
        check_count(len(value), 4096, "max_string_length")
        return value
    if value is None or type(value) is bool:
        return value
    raise WireFailure("invalid_type")


def _parse_scalar(value: JsonValue, field: Field) -> Scalar:
    if value is None or field.kind in ("text", "bool"):
        return cast(Scalar, value)
    if type(value) is not str:
        raise WireFailure("invalid_type", location=(field.name,))
    if field.kind == "int64":
        if re.fullmatch(r"0|-[1-9][0-9]{0,18}|[1-9][0-9]{0,18}", value) is None:
            raise WireFailure("invalid_type", location=(field.name,))
        return int(value)
    if field.kind == "decimal":
        if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value) is None:
            raise WireFailure("precision", location=(field.name,))
        return Decimal(value)
    if field.kind == "datetime":
        return _datetime(value, (field.name,))
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise WireFailure("invalid_type", location=(field.name,))
    return date.fromisoformat(value)


def decode_scalar(value: JsonValue, field: Field) -> Scalar:
    try:
        if isinstance(value, str):
            check_count(len(value), 4096, "max_string_length", (field.name,))
        result = _parse_scalar(value, field)
        if isinstance(result, Decimal):
            return _scaled_decimal(result, field)
        validate_scalar(result, field, (field.name,))
        return result
    except PublicationValidationError as error:
        raise WireFailure(error.issue.code, location=error.issue.location) from None
    except WireFailure:
        raise
    except (ValueError, ArithmeticError):
        raise WireFailure("invalid_type", location=(field.name,)) from None


def _scaled_decimal(value: Decimal, field: Field) -> Decimal:
    """Rebuild validated exact digits at field scale without context arithmetic."""
    validate_scalar(value, field, (field.name,))
    scale = cast(int, field.scale)
    if value.is_zero():
        return Decimal((0, (0,), -scale))
    parts = value.as_tuple()
    shift = cast(int, parts.exponent) + scale
    digits = parts.digits + (0,) * shift if shift >= 0 else parts.digits[:shift]
    return Decimal((parts.sign, digits, -scale))


def encode_parameter(value: Scalar) -> JsonObject:
    kinds = {
        str: "text",
        bool: "bool",
        int: "int64",
        Decimal: "decimal",
        date: "date",
        datetime: "datetime",
        type(None): "null",
    }
    return freeze_object({"kind": kinds[type(value)], "value": encode_scalar(value)})


def decode_parameter(value: JsonObject) -> Scalar:
    try:
        wire = ParameterWire.model_validate(dict(value))
        if wire.kind == "null":
            if wire.value is not None:
                raise WireFailure("invalid_type")
            return None
        scale = 0
        if wire.kind == "decimal" and isinstance(wire.value, str):
            scale = len(wire.value.partition(".")[2])
        field = Field(
            "value",
            "Value",
            wire.kind,
            False,
            precision=38 if wire.kind == "decimal" else None,
            scale=scale if wire.kind == "decimal" else None,
        )
        return decode_scalar(wire.value, field)
    except (ValidationError, PublicationValidationError):
        raise WireFailure("invalid_input") from None


def _field(value: JsonValue) -> Field:
    raw = cast(JsonObject, value)
    return Field(
        cast(str, raw["name"]),
        cast(str, raw["label"]),
        cast(ScalarKind, raw["kind"]),
        cast(bool, raw["nullable"]),
        cast(str | None, raw["unit"]),
        cast(int | None, raw["precision"]),
        cast(int | None, raw["scale"]),
    )


def _cell(value: JsonValue, field: Field, location: tuple[str | int, ...]) -> Scalar:
    try:
        return decode_scalar(value, field)
    except WireFailure as error:
        raise WireFailure(error.code, location=(*location, field.name), limit=error.limit) from None


def _dataset(raw: JsonObject) -> Dataset:
    fields = tuple(_field(value) for value in cast(tuple[JsonValue, ...], raw["fields"]))
    rows = cast(tuple[tuple[JsonValue, ...], ...], raw["rows"])
    location = ("datasets", cast(str, raw["name"]))
    decoded: list[tuple[Scalar, ...]] = []
    for index, row in enumerate(rows):
        if len(row) != len(fields):
            raise WireFailure("shape", location=(*location, "rows", index))
        decoded.append(
            tuple(
                _cell(value, field, (*location, "rows", index))
                for value, field in zip(row, fields, strict=True)
            )
        )
    return Dataset(
        cast(str, raw["name"]),
        cast(str, raw["label"]),
        fields,
        tuple(decoded),
        tuple(cast(tuple[str, ...], raw["keys"])),
        cast(str, raw["source_ref"]),
        cast(str, raw["producer_id"]),
        cast(str | None, raw["source_version"]),
    )


def _metric(raw: JsonObject) -> ImportedMetric:
    field = _field(raw["value_schema"])
    location = ("metrics", cast(str, raw["identity"]), "values")
    return ImportedMetric(
        cast(str, raw["identity"]),
        cast(str, raw["unit"]),
        cast(str | None, raw["period"]),
        _datetime(raw["as_of"], ("metrics", cast(str, raw["identity"]), "as_of")),
        cast(str, raw["source_ref"]),
        cast(str, raw["producer_id"]),
        cast(str, raw["method_version"]),
        cast(Literal["scalar", "series"], raw["shape"]),
        field,
        tuple(cast(tuple[str, ...], raw["labels"])),
        tuple(
            _cell(value, field, (*location, index))
            for index, value in enumerate(cast(tuple[JsonValue, ...], raw["values"]))
        ),
        tuple(cast(tuple[str, ...], raw["external_evidence"])),
    )


def _dataset_object(data: Dataset) -> JsonObject:
    result = cast(dict[str, JsonValue], asdict(data))
    result["rows"] = [
        [_encode_cell(value, field) for value, field in zip(row, data.fields, strict=True)]
        for row in data.rows
    ]
    return result


def _metric_object(metric: ImportedMetric) -> JsonObject:
    result = cast(dict[str, JsonValue], asdict(metric))
    result["values"] = [_encode_cell(value, metric.value_schema) for value in metric.values]
    result["as_of"] = _timestamp(metric.as_of) if metric.as_of is not None else None
    return result


def _encode_cell(value: Scalar, field: Field) -> JsonValue:
    return encode_scalar(_scaled_decimal(value, field) if isinstance(value, Decimal) else value)


encode_cell = _encode_cell
decode_metric = _metric
encode_metric = _metric_object


def _normalize(content: JsonObject) -> JsonObject:
    datasets = tuple(_dataset(raw) for raw in cast(tuple[JsonObject, ...], content["datasets"]))
    metrics = tuple(_metric(raw) for raw in cast(tuple[JsonObject, ...], content["metrics"]))
    require_unique(tuple(data.name for data in datasets), ("datasets",))
    require_unique(tuple(metric.identity for metric in metrics), ("metrics",))
    version = int(cast(str, content["producer_version"]))
    if not 1 <= version < 2**63:
        raise WireFailure("invalid_version", location=("producer_version",))
    if not cast(str, content["feed_id"]).strip():
        raise WireFailure("required", location=("feed_id",))
    result = dict(content)
    result.update(
        datasets=[_dataset_object(data) for data in datasets],
        metrics=[_metric_object(metric) for metric in metrics],
    )
    for name in ("observation_time", "generation_time"):
        parsed = _datetime(content[name], (name,))
        result[name] = _timestamp(parsed) if parsed is not None else None
    return freeze_object(result)


def _producer(value: JsonObject | Snapshot) -> JsonObject:
    if isinstance(value, Mapping):
        return value
    result = cast(dict[str, JsonValue], asdict(value))
    for name in ("content_digest", "received_at", "accepted_at"):
        result.pop(name)
    result.update(
        producer_version=str(value.producer_version),
        datasets=[_dataset_object(data) for data in value.datasets],
        metrics=[_metric_object(metric) for metric in value.metrics],
    )
    for name in ("observation_time", "generation_time"):
        stamp: datetime | None = getattr(value, name)
        result[name] = _timestamp(stamp) if stamp is not None else None
    return result


def producer_bytes(value: JsonObject | Snapshot) -> bytes:
    """Serialize codec-normalized producer content or an inward Snapshot."""
    return canonical_bytes(_producer(value))


def content_digest(value: JsonObject | Snapshot) -> str:
    return hashlib.sha256(producer_bytes(value)).hexdigest()


def finalize_snapshot(
    content: JsonObject, received_at: datetime, accepted_at: datetime
) -> tuple[Snapshot, bytes]:
    """Trusted codec output only; service times are supplied by publication runtime."""
    encoded = producer_bytes(content)
    snapshot = Snapshot(
        "1",
        cast(str, content["feed_id"]),
        int(cast(str, content["producer_version"])),
        hashlib.sha256(encoded).hexdigest(),
        tuple(_dataset(raw) for raw in cast(tuple[JsonObject, ...], content["datasets"])),
        tuple(_metric(raw) for raw in cast(tuple[JsonObject, ...], content["metrics"])),
        _datetime(content["observation_time"]),
        _datetime(content["generation_time"]),
        received_at,
        accepted_at,
    )
    return snapshot, encoded


def _read_object(snapshot: Snapshot) -> JsonObject:
    return {
        **_producer(snapshot),
        "content_digest": snapshot.content_digest,
        "received_at": _timestamp(snapshot.received_at),
        "accepted_at": _timestamp(snapshot.accepted_at),
    }


def publication_codec(
    limits: SnapshotLimits = SnapshotLimits(),
) -> PydanticCodec[JsonObject, PublicationWire]:

    def decode(model: PublicationWire) -> JsonObject:
        try:
            raw = cast(JsonObject, model.model_dump(mode="python"))
            check_shape(raw, limits)
            normalized = _normalize(raw)
            check_count(
                len(canonical_bytes(normalized, limits.max_nesting_depth)),
                limits.max_input_bytes,
                "max_input_bytes",
            )
            candidate = {
                **normalized,
                "content_digest": "f" * 64,
                "received_at": "9999-12-31T23:59:59.999999Z",
                "accepted_at": "9999-12-31T23:59:59.999999Z",
            }
            check_shape(candidate, limits)
            check_count(
                len(canonical_bytes(candidate, limits.max_nesting_depth)),
                limits.max_output_bytes,
                "max_output_bytes",
            )
            return normalized
        except PublicationValidationError as error:
            raise WireFailure(error.issue.code, location=error.issue.location) from None

    return PydanticCodec(
        PublicationWire, decode, lambda value: value, limits.operation_limits()
    ).for_input()


def snapshot_codec(
    limits: SnapshotLimits = SnapshotLimits(),
) -> PydanticCodec[Snapshot, SnapshotWire]:

    def decode(model: SnapshotWire) -> Snapshot:
        raw = cast(dict[str, JsonValue], model.model_dump(mode="python"))
        received, accepted = _datetime(raw.pop("received_at")), _datetime(raw.pop("accepted_at"))
        digest = raw.pop("content_digest")
        assert received is not None and accepted is not None
        normalized = publication_codec(limits).decode(raw)
        result, _ = finalize_snapshot(normalized, received, accepted)
        if digest != result.content_digest:
            raise WireFailure("invalid_digest", location=("content_digest",))
        return result

    def encode(snapshot: Snapshot) -> JsonObject:
        result = _read_object(snapshot)
        check_shape(result, limits)
        if snapshot.content_digest != content_digest(snapshot):
            raise WireFailure("invalid_digest", location=("content_digest",))
        return result

    return PydanticCodec(SnapshotWire, decode, encode, limits.operation_limits())
