"""Independent producer wire examples and admission-boundary failures."""

import asyncio
import hashlib
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import cast

import pytest

from craftreport.adapters.canonical import WireFailure, canonical_bytes
from craftreport.adapters.snapshot_wire import (
    SnapshotLimits,
    content_digest,
    decode_parameter,
    decode_scalar,
    encode_parameter,
    encode_scalar,
    finalize_snapshot,
    producer_bytes,
    publication_codec,
    snapshot_codec,
)
from craftreport.adapters.validation import PydanticCodec, StrictWireModel
from craftreport.application.service_values import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import ExpectedVersion, JsonObject, ResourceRef
from craftreport.contracts.values import JsonValue, require_immutable
from craftreport.data.ports import SnapshotFinalizer, SnapshotReader
from craftreport.data.values import Field, Scalar, ScalarKind, Snapshot, SnapshotRef

STAMP = datetime(2026, 10, 15, 9, 1, 2, 123456, tzinfo=UTC)
EMPTY_BYTES = (
    b'{"datasets":[],"feed_id":"feed","generation_time":null,"metrics":[], '
    b'"observation_time":null,"producer_version":"1","schema_version":"1"}'
).replace(b", ", b",")


@pytest.fixture
def payload() -> dict[str, JsonValue]:
    fields: list[JsonValue] = [
        {"name": "id", "label": "Identifier", "kind": "int64", "nullable": False},
        {
            "name": "amount",
            "label": "Amount",
            "kind": "decimal",
            "nullable": True,
            "unit": "USD",
            "precision": 38,
            "scale": 2,
        },
        {"name": "text", "label": "Text", "kind": "text", "nullable": False},
        {"name": "day", "label": "Day", "kind": "date", "nullable": False},
        {"name": "seen", "label": "Seen", "kind": "datetime", "nullable": False},
        {"name": "flag", "label": "Flag", "kind": "bool", "nullable": False},
    ]
    return {
        "schema_version": "1",
        "feed_id": "feed",
        "producer_version": "9223372036854775807",
        "datasets": [
            {
                "name": "positions",
                "label": "Positions",
                "fields": fields,
                "rows": [
                    [
                        "9223372036854775807",
                        "123456789012345678901234567890123456.78",
                        "=SUM(A1)",
                        "2026-10-14",
                        "2026-10-15T11:01:02.123456+02:00",
                        True,
                    ],
                    [
                        "-9223372036854775808",
                        "-0.000",
                        "@literal",
                        "2026-10-15",
                        "2026-10-15T09:01:02.123456Z",
                        False,
                    ],
                ],
                "keys": ["id"],
                "source_ref": "source:positions",
                "producer_id": "allocation",
                "source_version": "source-v9",
            }
        ],
        "metrics": [
            {
                "identity": "return",
                "unit": "%",
                "period": "Q3",
                "as_of": None,
                "source_ref": "source:metrics",
                "producer_id": "quant",
                "method_version": "v7",
                "shape": "series",
                "value_schema": {
                    "name": "value",
                    "label": "Return",
                    "kind": "decimal",
                    "nullable": True,
                    "unit": "%",
                    "precision": 10,
                    "scale": 4,
                },
                "labels": ["last", "first", "middle"],
                "values": ["-1.23", None, "0.00000"],
                "external_evidence": ["producer-claim:checked"],
            }
        ],
        "observation_time": "2026-10-15T07:00:00Z",
        "generation_time": "2026-10-15T08:00:00Z",
    }


def dataset(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(list[dict[str, JsonValue]], payload["datasets"])[0]


def rows(payload: dict[str, JsonValue]) -> list[list[JsonValue]]:
    return cast(list[list[JsonValue]], dataset(payload)["rows"])


def empty() -> dict[str, JsonValue]:
    return {
        "schema_version": "1",
        "feed_id": "feed",
        "producer_version": "1",
        "datasets": [],
        "metrics": [],
        "observation_time": None,
        "generation_time": None,
    }


def test_exact_empty_bytes_and_digest() -> None:
    normalized = publication_codec().decode(empty())
    assert producer_bytes(normalized) == EMPTY_BYTES
    assert content_digest(normalized) == hashlib.sha256(EMPTY_BYTES).hexdigest()
    finalizer: SnapshotFinalizer = finalize_snapshot
    snapshot, retained = finalizer(normalized, STAMP, STAMP + timedelta(seconds=1))
    assert retained == EMPTY_BYTES
    assert snapshot.content_digest == hashlib.sha256(EMPTY_BYTES).hexdigest()
    assert canonical_bytes(snapshot_codec().encode(snapshot)) == (
        b'{"accepted_at":"2026-10-15T09:01:03.123456Z","content_digest":"'
        + hashlib.sha256(EMPTY_BYTES).hexdigest().encode()
        + b'","datasets":[],"feed_id":"feed","generation_time":null,"metrics":[], '
        b'"observation_time":null,"producer_version":"1",'
        b'"received_at":"2026-10-15T09:01:02.123456Z","schema_version":"1"}'
    ).replace(b", ", b",")


def test_exact_values_provenance_order_and_distinct_times(payload: dict[str, JsonValue]) -> None:
    normalized = publication_codec().decode(payload)
    require_immutable(normalized)
    snapshot, retained = finalize_snapshot(normalized, STAMP, STAMP + timedelta(seconds=2))
    assert retained == producer_bytes(normalized)
    data = snapshot.datasets[0]
    assert data.rows[0] == (
        9223372036854775807,
        Decimal("123456789012345678901234567890123456.78"),
        "=SUM(A1)",
        date(2026, 10, 14),
        STAMP,
        True,
    )
    assert data.rows[1][0:3] == (-9223372036854775808, Decimal("0.00"), "@literal")
    assert (data.label, data.source_ref, data.producer_id, data.source_version) == (
        "Positions",
        "source:positions",
        "allocation",
        "source-v9",
    )
    metric = snapshot.metrics[0]
    assert metric.labels == ("last", "first", "middle")
    assert metric.values == (Decimal("-1.2300"), None, Decimal("0.0000"))
    assert (
        metric.source_ref,
        metric.producer_id,
        metric.method_version,
        metric.external_evidence,
    ) == (
        "source:metrics",
        "quant",
        "v7",
        ("producer-claim:checked",),
    )
    assert snapshot.observation_time == STAMP.replace(hour=7, minute=0, second=0, microsecond=0)
    assert snapshot.generation_time == STAMP.replace(hour=8, minute=0, second=0, microsecond=0)
    assert snapshot.received_at == STAMP
    assert snapshot.accepted_at == STAMP + timedelta(seconds=2)
    assert snapshot_codec().decode(snapshot_codec().encode(snapshot)) == snapshot
    rows(payload)[0][2] = "changed"
    assert snapshot.datasets[0].rows[0][2] == "=SUM(A1)"


@pytest.mark.parametrize(
    "value,kind,wire",
    [
        (2**53, "int64", "9007199254740992"),
        (-(2**63), "int64", "-9223372036854775808"),
        (2**63 - 1, "int64", "9223372036854775807"),
        ("12", "text", "12"),
        ("+literal", "text", "+literal"),
        ("-literal", "text", "-literal"),
        (True, "bool", True),
        (None, "text", None),
        (date(2026, 10, 15), "date", "2026-10-15"),
        (STAMP.astimezone(timezone(timedelta(hours=2))), "datetime", "2026-10-15T09:01:02.123456Z"),
        (Decimal("1.20"), "decimal", "1.20"),
    ],
)
def test_shared_scalar(value: Scalar, kind: ScalarKind, wire: JsonValue) -> None:
    field = Field(
        "v",
        "Value",
        kind,
        True,
        precision=38 if kind == "decimal" else None,
        scale=2 if kind == "decimal" else None,
    )
    assert encode_scalar(value) == wire
    assert decode_scalar(wire, field) == value


@pytest.mark.parametrize(
    "value,kind",
    [
        ("12", "text"),
        (12, "int64"),
        (Decimal("12"), "decimal"),
        (True, "bool"),
        (date(2026, 10, 15), "date"),
        (STAMP, "datetime"),
        (None, "null"),
    ],
)
def test_tagged_parameters(value: Scalar, kind: str) -> None:
    tagged = encode_parameter(value)
    assert tagged == {"kind": kind, "value": encode_scalar(value)}
    decoded = decode_parameter(tagged)
    assert decoded == value and type(decoded) is type(value)


@pytest.mark.parametrize(
    "tagged",
    [
        {"kind": "int64", "value": 12},
        {"kind": "text", "value": True},
        {"kind": "null", "value": "None"},
        {"kind": "float", "value": "1"},
        {"kind": "int64", "value": "12", "extra": True},
    ],
)
def test_invalid_tagged_parameter(tagged: JsonObject) -> None:
    with pytest.raises(WireFailure) as error:
        decode_parameter(tagged)
    assert error.value.code != "disabled"


@pytest.mark.parametrize(
    "kind,value",
    [
        ("int64", 1),
        ("int64", True),
        ("int64", "01"),
        ("int64", "+1"),
        ("int64", "-0"),
        ("int64", "9223372036854775808"),
        ("decimal", 1.2),
        ("decimal", "NaN"),
        ("decimal", "Infinity"),
        ("decimal", "1.001"),
        ("decimal", "1e2"),
        ("date", "2026-1-01"),
        ("date", "2026-02-30"),
        ("datetime", "2026-10-15T00:00:00.1234567Z"),
        ("datetime", "2026-10-15T00:00:00Z" + "\n"),
        ("datetime", "2026-10-15T00:00:00"),
        ("datetime", "2026-10-15T00:00:60Z"),
        ("datetime", "2026-10-15T00:00:00+24:00"),
        ("bool", "true"),
        ("text", 1),
    ],
)
def test_unsafe_scalar_rejected(kind: ScalarKind, value: JsonValue) -> None:
    field = Field(
        "v",
        "V",
        kind,
        False,
        precision=38 if kind == "decimal" else None,
        scale=2 if kind == "decimal" else None,
    )
    with pytest.raises(WireFailure) as error:
        decode_scalar(value, field)
    assert error.value.code != "disabled"


def test_decimal_normalization_is_exact_and_context_independent(
    payload: dict[str, JsonValue],
) -> None:
    with localcontext() as context:
        context.prec = 3
        normalized = publication_codec().decode(payload)
    encoded_rows = cast(tuple[JsonObject, ...], normalized["datasets"])[0]["rows"]
    assert cast(tuple[tuple[JsonValue, ...], ...], encoded_rows)[0][1] == (
        "123456789012345678901234567890123456.78"
    )
    assert cast(tuple[tuple[JsonValue, ...], ...], encoded_rows)[1][1] == "0.00"
    other = deepcopy(payload)
    rows(other)[1][1] = "0.0"
    assert content_digest(publication_codec().decode(other)) == content_digest(normalized)


def test_identity_service_times_and_producer_changes(payload: dict[str, JsonValue]) -> None:
    normalized = publication_codec().decode(payload)
    first, _ = finalize_snapshot(normalized, STAMP, STAMP)
    later, _ = finalize_snapshot(normalized, STAMP + timedelta(days=1), STAMP + timedelta(days=2))
    assert producer_bytes(first) == producer_bytes(later)
    assert first.content_digest == later.content_digest
    for key, replacement in [("label", "Other"), ("source_version", "v10")]:
        changed = deepcopy(payload)
        dataset(changed)[key] = replacement
        assert content_digest(publication_codec().decode(changed)) != first.content_digest
    changed = deepcopy(payload)
    rows(changed).reverse()
    assert content_digest(publication_codec().decode(changed)) != first.content_digest


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", 1),
        ("schema_version", "2"),
        ("producer_version", 1),
        ("producer_version", "01"),
        ("producer_version", "0"),
        ("producer_version", "9223372036854775808"),
        ("received_at", "2026-10-15T00:00:00Z"),
        ("retry_key", "x"),
        ("content_digest", "a" * 64),
    ],
)
def test_invalid_publication_metadata(key: str, value: JsonValue) -> None:
    body = empty()
    body[key] = value
    with pytest.raises(WireFailure) as error:
        publication_codec().decode(body)
    assert error.value.code != "disabled"


@pytest.mark.parametrize("mutation", ["extra", "duplicate", "row", "key", "null", "rule"])
def test_domain_failure_location(payload: dict[str, JsonValue], mutation: str) -> None:
    data = dataset(payload)
    if mutation == "extra":
        data["extra"] = True
    elif mutation == "duplicate":
        rows(payload)[1][0] = rows(payload)[0][0]
    elif mutation == "row":
        rows(payload)[0].pop()
    elif mutation == "key":
        data["keys"] = ["missing"]
    elif mutation == "null":
        rows(payload)[0][0] = None
    else:
        cast(list[dict[str, JsonValue]], data["fields"])[0]["expression"] = "1+1"
    with pytest.raises(WireFailure) as error:
        publication_codec().decode(payload)
    assert error.value.code != "disabled"
    assert error.value.location


@pytest.mark.parametrize(
    "name,limit",
    [
        ("max_datasets", 1),
        ("max_fields", 5),
        ("max_rows", 1),
        ("max_cells", 11),
        ("max_metrics", 1),
        ("max_metric_points", 2),
        ("max_string_length", 10),
        ("max_input_bytes", 100),
        ("max_nesting_depth", 3),
    ],
)
def test_named_downward_limits(payload: dict[str, JsonValue], name: str, limit: int) -> None:
    if name == "max_datasets":
        data = deepcopy(dataset(payload))
        data["name"] = "second"
        cast(list[JsonValue], payload["datasets"]).append(data)
    if name == "max_metrics":
        metric = deepcopy(cast(list[dict[str, JsonValue]], payload["metrics"])[0])
        metric["identity"] = "second"
        cast(list[JsonValue], payload["metrics"]).append(metric)
    limits = replace(SnapshotLimits(), **{name: limit})
    with pytest.raises(WireFailure) as error:
        publication_codec(limits).decode(payload)
    assert error.value.limit == name


def test_full_result_bound_rejects_before_finalization() -> None:
    body = empty()
    request_bytes = len(EMPTY_BYTES)
    # Producer bytes fit, but digest, both fixed service timestamps and their keys do not.
    limits = replace(SnapshotLimits(), max_output_bytes=request_bytes + 100)
    with pytest.raises(WireFailure) as error:
        publication_codec(limits).decode(body)
    assert error.value.code == "limit_exceeded"
    assert error.value.limit == "max_output_bytes"


@pytest.mark.parametrize(
    "name",
    [
        "max_input_bytes",
        "max_output_bytes",
        "max_nesting_depth",
        "max_datasets",
        "max_fields",
        "max_rows",
        "max_cells",
        "max_metrics",
        "max_metric_points",
        "max_string_length",
    ],
)
def test_limits_cannot_be_raised_or_disabled(name: str) -> None:
    defaults = SnapshotLimits()
    for value in (0, True, getattr(defaults, name) + 1):
        with pytest.raises(ValueError):
            replace(defaults, **{name: value})


def test_wide_json_numbers_and_nested_depth_fail() -> None:
    body = empty()
    body["extra"] = 2**53
    with pytest.raises(WireFailure) as error:
        publication_codec().decode(body)
    assert error.value.code != "disabled"


class _RegressionWire(StrictWireModel):
    value: str


def test_pydantic_codec_preserves_explicit_failure() -> None:
    def fail(_: _RegressionWire) -> str:
        raise WireFailure(
            "precision", location=("datasets", "positions", "rows", 2, "amount"), limit="max_cells"
        )

    codec = PydanticCodec(_RegressionWire, fail, lambda value: {"value": value})
    with pytest.raises(WireFailure) as error:
        codec.decode({"value": "x"})
    assert (error.value.code, error.value.location, error.value.limit) == (
        "precision",
        ("datasets", "positions", "rows", 2, "amount"),
        "max_cells",
    )


def test_reader_protocol_outcomes_are_not_storage_evidence() -> None:
    snapshot, _ = finalize_snapshot(publication_codec().decode(empty()), STAMP, STAMP)
    resource = ResourceRef("snapshot", "feed:1")
    conflict = VersionConflict(
        (ExpectedVersion(resource, "a" * 64),),
        (ExpectedVersion(resource, snapshot.content_digest),),
    )
    outcomes = (snapshot, Missing(), conflict, ServiceUnavailable("snapshots"))

    class Reader:
        async def read(
            self, ref: SnapshotRef
        ) -> Snapshot | Missing | VersionConflict | ServiceUnavailable:
            assert ref.feed_id == "feed"
            return outcomes[index]

    reader: SnapshotReader = Reader()
    for index, expected in enumerate(outcomes):
        result = asyncio.run(reader.read(SnapshotRef("feed", 1, "a" * 64)))
        assert result is expected
    assert isinstance(publication_codec().schema(), Mapping)


@pytest.mark.parametrize(
    "name",
    [
        "max_datasets",
        "max_fields",
        "max_rows",
        "max_cells",
        "max_metrics",
        "max_metric_points",
        "max_string_length",
    ],
)
def test_default_shape_limits_identify_named_limit(name: str) -> None:
    field: JsonObject = {"name": "value", "label": "V", "kind": "text", "nullable": True}
    data: dict[str, JsonValue] = {
        "name": "d",
        "label": "D",
        "fields": [field],
        "rows": [],
        "keys": [],
        "source_ref": "s",
        "producer_id": "p",
    }
    metric: dict[str, JsonValue] = {
        "identity": "m",
        "unit": "u",
        "period": "p",
        "source_ref": "s",
        "producer_id": "p",
        "method_version": "v",
        "shape": "series",
        "value_schema": field,
        "labels": [],
        "values": [],
        "external_evidence": [],
    }
    body = empty()
    body["datasets"] = [data]
    if name == "max_datasets":
        body["datasets"] = [{**data, "name": str(i)} for i in range(17)]
    elif name == "max_fields":
        data["fields"] = [{**field, "name": str(i)} for i in range(129)]
    elif name == "max_rows":
        data["rows"] = [[None] for _ in range(10001)]
    elif name == "max_cells":
        data["fields"] = [{**field, "name": str(i)} for i in range(11)]
        data["rows"] = cast(JsonValue, [[None] * 11 for _ in range(10000)])
    elif name == "max_metrics":
        body["metrics"] = [{**metric, "identity": str(i)} for i in range(129)]
    elif name == "max_metric_points":
        metric.update(labels=cast(JsonValue, [""] * 10001), values=cast(JsonValue, [None] * 10001))
        body["metrics"] = [metric]
    else:
        data["label"] = "x" * 4097
    with pytest.raises(WireFailure) as error:
        publication_codec().decode(body)
    assert (error.value.code, error.value.limit) == ("limit_exceeded", name)


def test_output_bound_is_exact_including_utf8_escaping_and_normalized_defaults() -> None:
    body = empty()
    body["feed_id"] = 'f🙂"\\\n'
    normalized = publication_codec().decode(body)
    snapshot, _ = finalize_snapshot(normalized, datetime.max.replace(tzinfo=UTC), STAMP)
    size = len(canonical_bytes(snapshot_codec().encode(snapshot)))
    assert (
        publication_codec(replace(SnapshotLimits(), max_output_bytes=size)).decode(body)
        == normalized
    )
    with pytest.raises(WireFailure) as error:
        publication_codec(replace(SnapshotLimits(), max_output_bytes=size - 1)).decode(body)
    assert error.value.limit == "max_output_bytes"


def test_normalized_input_cap_is_enforced() -> None:
    body = empty()
    del body["generation_time"]
    del body["observation_time"]
    limits = replace(SnapshotLimits(), max_input_bytes=len(canonical_bytes(body)))
    with pytest.raises(WireFailure) as error:
        publication_codec(limits).decode(body)
    assert error.value.limit == "max_input_bytes"


def test_snapshot_direct_decimal_canonicalization_and_wrong_digest(
    payload: dict[str, JsonValue],
) -> None:
    snapshot, _ = finalize_snapshot(publication_codec().decode(payload), STAMP, STAMP)
    data = snapshot.datasets[0]
    altered_rows = (data.rows[0], (data.rows[1][0], Decimal("-0.000000"), *data.rows[1][2:]))
    equivalent = replace(snapshot, datasets=(replace(data, rows=altered_rows),))
    assert producer_bytes(equivalent) == producer_bytes(snapshot)
    assert snapshot_codec().encode(equivalent) == snapshot_codec().encode(snapshot)
    with pytest.raises(WireFailure) as error:
        snapshot_codec().encode(replace(snapshot, content_digest="b" * 64))
    assert error.value.code == "result_contract_failure"
    encoded = dict(snapshot_codec().encode(snapshot))
    encoded["content_digest"] = "b" * 64
    with pytest.raises(WireFailure) as error:
        snapshot_codec().decode(encoded)
    assert error.value.code == "invalid_digest"


def test_nonnull_parameter_tags_cannot_hide_null() -> None:
    with pytest.raises(WireFailure):
        decode_parameter({"kind": "text", "value": None})


@pytest.mark.parametrize("maximum", [1, 26, 63])
def test_full_read_service_strings_must_fit_before_admission(maximum: int) -> None:
    body = empty()
    body["feed_id"] = "f"
    limits = replace(SnapshotLimits(), max_string_length=maximum)
    with pytest.raises(WireFailure) as error:
        publication_codec(limits).decode(body)
    assert (error.value.code, error.value.limit) == ("limit_exceeded", "max_string_length")


def test_full_read_service_string_limit_64_is_supported() -> None:
    limits = replace(SnapshotLimits(), max_string_length=64)
    content = publication_codec(limits).decode(empty())
    snapshot, _ = finalize_snapshot(content, STAMP, STAMP)
    assert len(snapshot.content_digest) == 64
    assert snapshot_codec(limits).decode(snapshot_codec(limits).encode(snapshot)) == snapshot
