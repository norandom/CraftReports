"""Independent examples for precise producer data, not financial methodology."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime
from decimal import Decimal, localcontext
from io import BytesIO
from struct import pack
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from craftreport.contracts.pins import VersionPin
from craftreport.data.validation import PublicationValidationError, validate_datetime_lexeme
from craftreport.data.values import (
    Dataset,
    Field,
    ImportedMetric,
    Scalar,
    ScalarKind,
    Snapshot,
    SnapshotRef,
)

DIGEST = "a" * 64
STAMP = datetime(2026, 10, 15, 9, 1, 2, 123456, tzinfo=UTC)


@pytest.fixture
def dataset() -> Dataset:
    return Dataset(
        "holdings",
        "Positions",
        (
            Field("id", "Identifier", "int64", False),
            Field("amount", "Amount", "decimal", True, "USD", 38, 2),
            Field("note", "Note", "text", False),
            Field("day", "Day", "date", False),
            Field("seen", "Seen", "datetime", False),
            Field("active", "Active", "bool", False),
        ),
        (
            (
                2**63 - 1,
                Decimal("123456789012345678901234567890123456.78"),
                "=SUM(A1)",
                date(2026, 10, 14),
                STAMP,
                True,
            ),
            (-(2**63), None, "@literal", date(2026, 10, 15), STAMP, False),
        ),
        ("id",),
        "source:positions",
        "allocation-producer",
        "source-v9",
    )


@pytest.fixture
def metric() -> ImportedMetric:
    return ImportedMetric(
        "supplied-return",
        "%",
        "2026-Q3",
        None,
        "source:metrics",
        "quant-producer",
        "method-v7",
        "series",
        Field("value", "Return", "decimal", True, "%", 10, 4),
        ("last", "first", "middle"),
        (Decimal("-1.2300"), None, Decimal("0.0000")),
        ("producer-claim:checked",),
    )


@pytest.fixture
def snapshot(dataset: Dataset, metric: ImportedMetric) -> Snapshot:
    return Snapshot(
        "1",
        "feed:portfolio",
        2**63 - 1,
        DIGEST,
        (dataset,),
        (metric,),
        STAMP.replace(hour=7),
        STAMP.replace(hour=8),
        STAMP.replace(hour=9),
        STAMP.replace(hour=10),
    )


def assert_issue(
    error: pytest.ExceptionInfo[PublicationValidationError],
    code: str,
    location: tuple[str | int, ...],
) -> None:
    assert error.value.issue.code == code
    assert error.value.issue.location == location


def test_exact_fixture_and_provenance(snapshot: Snapshot) -> None:
    actual = snapshot.datasets[0]
    assert actual.rows == (
        (
            9223372036854775807,
            Decimal("123456789012345678901234567890123456.78"),
            "=SUM(A1)",
            date(2026, 10, 14),
            STAMP,
            True,
        ),
        (-9223372036854775808, None, "@literal", date(2026, 10, 15), STAMP, False),
    )
    assert (actual.label, actual.source_ref, actual.producer_id, actual.source_version) == (
        "Positions",
        "source:positions",
        "allocation-producer",
        "source-v9",
    )
    imported = snapshot.metrics[0]
    assert (imported.labels, imported.values) == (
        ("last", "first", "middle"),
        (Decimal("-1.2300"), None, Decimal("0.0000")),
    )
    assert (
        imported.source_ref,
        imported.producer_id,
        imported.method_version,
        imported.external_evidence,
    ) == ("source:metrics", "quant-producer", "method-v7", ("producer-claim:checked",))
    assert [
        snapshot.observation_time,
        snapshot.generation_time,
        snapshot.received_at,
        snapshot.accepted_at,
    ] == [STAMP.replace(hour=h) for h in (7, 8, 9, 10)]


def test_empty_typed_content_and_scalar_shape(dataset: Dataset, metric: ImportedMetric) -> None:
    assert replace(dataset, rows=()).fields == dataset.fields
    assert replace(metric, values=(), labels=()).shape == "series"
    scalar = replace(metric, shape="scalar", values=(Decimal("1.2300"),), labels=())
    assert scalar.values[0] == Decimal("1.2300")
    assert replace(scalar, period=None, as_of=STAMP).as_of == STAMP


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("int64", True),
        ("int64", 2**63),
        ("int64", -(2**63) - 1),
        ("bool", 1),
        ("decimal", 1),
        ("decimal", 1.2),
        ("date", STAMP),
        ("datetime", date(2026, 1, 1)),
        ("text", 3),
        ("datetime", STAMP.replace(tzinfo=None)),
    ],
)
def test_reject_wrong_type_without_coercion(kind: ScalarKind, value: object) -> None:
    with pytest.raises(PublicationValidationError) as error:
        Dataset(
            "test",
            "Test",
            (
                Field(
                    "v",
                    "Value",
                    kind,
                    False,
                    None,
                    38 if kind == "decimal" else None,
                    2 if kind == "decimal" else None,
                ),
            ),
            ((cast(Scalar, value),),),
            (),
            "source",
            "producer",
            None,
        )
    assert error.value.issue.location == ("datasets", "test", "rows", 0, "v")


@pytest.mark.parametrize(
    "value", [Decimal("NaN"), Decimal("Infinity"), Decimal("1.001"), Decimal("1000.00")]
)
def test_reject_decimal_precision(value: Decimal) -> None:
    with pytest.raises(PublicationValidationError) as error:
        Dataset(
            "test",
            "Test",
            (Field("v", "V", "decimal", False, None, 5, 2),),
            ((value,),),
            (),
            "source",
            "producer",
            None,
        )
    assert_issue(error, "precision", ("datasets", "test", "rows", 0, "v"))


def test_decimal_validation_does_not_round_or_use_context(dataset: Dataset) -> None:
    with localcontext() as context:
        context.prec = 2
        assert replace(dataset).rows[0][1] == Decimal("123456789012345678901234567890123456.78")
        field = Field("v", "V", "decimal", False, None, 3, 2)
        value = Decimal("1.230000")
        assert Dataset("d", "D", (field,), ((value,),), (), "s", "p", None).rows[0][0] is value


@pytest.mark.parametrize(
    ("precision", "scale"), [(0, 0), (39, 2), (5, -1), (5, 6), (None, 2), (5, None), (True, 0)]
)
def test_invalid_decimal_declarations(precision: int | None, scale: int | None) -> None:
    with pytest.raises(PublicationValidationError):
        Field("v", "V", "decimal", False, None, precision, scale)


def test_key_required_field_and_shape_locations(dataset: Dataset) -> None:
    with pytest.raises(PublicationValidationError) as error:
        replace(dataset, rows=(dataset.rows[0], dataset.rows[0]))
    assert_issue(error, "duplicate_key", ("datasets", "holdings", "rows", 1, "keys"))
    with pytest.raises(PublicationValidationError) as error:
        replace(dataset, rows=((None, *dataset.rows[0][1:]),))
    assert_issue(error, "nullability", ("datasets", "holdings", "rows", 0, "id"))
    with pytest.raises(PublicationValidationError) as error:
        replace(dataset, rows=((1,),))
    assert_issue(error, "shape", ("datasets", "holdings", "rows", 0))
    with pytest.raises(PublicationValidationError) as error:
        replace(dataset, keys=("absent",))
    assert_issue(error, "invalid_key", ("datasets", "holdings", "keys", 0))


def test_duplicate_names_and_key_declarations(dataset: Dataset, snapshot: Snapshot) -> None:
    with pytest.raises(PublicationValidationError):
        replace(dataset, fields=(dataset.fields[0], dataset.fields[0]))
    with pytest.raises(PublicationValidationError):
        replace(dataset, keys=("id", "id"))
    with pytest.raises(PublicationValidationError):
        replace(snapshot, datasets=(dataset, dataset))
    with pytest.raises(PublicationValidationError):
        replace(snapshot, metrics=(snapshot.metrics[0], snapshot.metrics[0]))


@pytest.mark.parametrize(
    "field_name", ["identity", "unit", "source_ref", "producer_id", "method_version"]
)
def test_metric_requires_metadata(metric: ImportedMetric, field_name: str) -> None:
    with pytest.raises(PublicationValidationError) as error:
        replace(metric, **{field_name: ""})
    assert error.value.issue.location == (
        ("metrics", "identity")
        if field_name == "identity"
        else ("metrics", "supplied-return", field_name)
    )


def test_metric_period_shape_and_schema_failures(metric: ImportedMetric) -> None:
    for changes in (
        {"period": None},
        {"shape": "scalar"},
        {"labels": ("one",)},
        {"values": ("text",), "labels": ("one",)},
        {"shape": "other"},
    ):
        with pytest.raises(PublicationValidationError):
            replace(metric, **changes)


def test_recursive_immutability_and_no_mutable_aliases(
    dataset: Dataset, snapshot: Snapshot
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(dataset, "label", "changed")
    with pytest.raises(PublicationValidationError):
        replace(dataset, rows=cast(tuple[tuple[Scalar, ...], ...], [list(dataset.rows[0])]))
    with pytest.raises(PublicationValidationError):
        replace(dataset, fields=cast(tuple[Field, ...], list(dataset.fields)))
    with pytest.raises(PublicationValidationError):
        replace(snapshot, datasets=cast(tuple[Dataset, ...], list(snapshot.datasets)))
    with pytest.raises(PublicationValidationError):
        replace(dataset, rows=((cast(Scalar, {"mutable": 1}), *dataset.rows[0][1:]),))


@pytest.mark.parametrize("version", [True, 0, -1, 2**63])
def test_snapshot_version_requires_positive_signed64(version: int) -> None:
    with pytest.raises(PublicationValidationError):
        SnapshotRef("feed", version, DIGEST)


def test_generic_version_pin_and_snapshot_identity() -> None:
    assert VersionPin("template", "release-2026.10", DIGEST).version == "release-2026.10"
    assert SnapshotRef("feed", 1, DIGEST).content_digest == DIGEST
    for digest in ("", "A" * 64, "z" * 64, "a" * 63):
        with pytest.raises(ValueError):
            VersionPin("template", "v1", digest)
        with pytest.raises(PublicationValidationError):
            SnapshotRef("feed", 1, digest)


@pytest.mark.parametrize("literal", ["=SUM(A1)", "+123", "-12", "@formula"])
def test_formula_markers_remain_literal_text(literal: str) -> None:
    field = Field("v", "Value", "text", False)
    dataset = Dataset("d", "D", (field,), ((literal,),), (), "source", "producer", None)
    assert type(dataset.rows[0][0]) is str
    assert dataset.rows[0][0] == literal


def test_nullable_key_still_requires_a_nonnull_value() -> None:
    field = Field("id", "ID", "int64", True)
    with pytest.raises(PublicationValidationError) as error:
        Dataset("d", "D", (field,), ((None,),), ("id",), "source", "producer", None)
    assert_issue(error, "invalid_key", ("datasets", "d", "rows", 0, "keys"))


def test_scalar_nonnull_and_untyped_metric_containers(metric: ImportedMetric) -> None:
    for changes in (
        {"labels": cast(tuple[str, ...], ["last", "first", "middle"])},
        {"external_evidence": cast(tuple[str, ...], ["claim"])},
        {"values": cast(tuple[Scalar, ...], [Decimal("1.00")])},
        {"value_schema": Field("v", "V", "decimal", False, "%", 10, 4)},
    ):
        with pytest.raises(PublicationValidationError):
            replace(metric, **changes)


def test_snapshot_schema_and_required_timestamps(snapshot: Snapshot) -> None:
    for changes in (
        {"schema_version": "2"},
        {"received_at": None},
        {"accepted_at": STAMP.replace(tzinfo=None)},
        {"feed_id": ""},
    ):
        with pytest.raises(PublicationValidationError):
            replace(snapshot, **changes)
    assert replace(snapshot, observation_time=None, generation_time=None).observation_time is None


def test_generic_pin_labels_are_required() -> None:
    for identity, version in (("", "v1"), ("template", ""), (" ", "v1")):
        with pytest.raises(ValueError):
            VersionPin(identity, version, DIGEST)


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-15T09:01:02.1234567Z",
        "2026-10-15T09:01:02.0000000+00:00",
        "2026-10-15T09:01:02,1234567Z",
    ],
)
def test_datetime_lexical_precision_rejected_before_parsing(text: str) -> None:
    with pytest.raises(PublicationValidationError) as error:
        validate_datetime_lexeme(text, ("value",))
    assert_issue(error, "precision", ("value",))


@pytest.mark.parametrize("text", ["2026-10-15T09:01:02Z", "2026-10-15T09:01:02.123456+02:30"])
def test_valid_datetime_lexical_precision(text: str) -> None:
    assert validate_datetime_lexeme(text, ("value",)) is None


@pytest.mark.parametrize(
    "text", ["2026-10-15T09:01:02", "2026-10-15T09:01:60Z", "2026-10-15T09:01:02+25:00"]
)
def test_invalid_datetime_lexemes(text: str) -> None:
    with pytest.raises(PublicationValidationError):
        validate_datetime_lexeme(text, ("value",))


@pytest.fixture
def rollback_zone() -> ZoneInfo:
    """Synthetic +02 to +01 rollback, independent of installed timezone data."""
    header = b"TZif\x00" + b"\x00" * 15 + pack(">6l", 0, 0, 0, 1, 2, 9)
    transition = pack(">l", 1792890000) + b"\x01"  # 2026-10-25 01:00:00 UTC
    offsets = pack(">lbb", 7200, 0, 0) + pack(">lbb", 3600, 0, 5)
    return ZoneInfo.from_file(BytesIO(header + transition + offsets + b"CEST\x00CET\x00"))


def test_datetime_keys_distinguish_rollback_instants(rollback_zone: ZoneInfo) -> None:
    first = datetime(2026, 10, 25, 2, 30, tzinfo=rollback_zone, fold=0)
    second = datetime(2026, 10, 25, 2, 30, tzinfo=rollback_zone, fold=1)
    assert first.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert second.astimezone(UTC) == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    dataset = Dataset(
        "d",
        "D",
        (Field("id", "ID", "datetime", False),),
        ((first,), (second,)),
        ("id",),
        "source",
        "producer",
        None,
    )
    assert dataset.rows[0][0] is first
    assert dataset.rows[1][0] is second


def test_datetime_keys_reject_same_instant_across_zones(rollback_zone: ZoneInfo) -> None:
    local = datetime(2026, 10, 25, 2, 30, tzinfo=rollback_zone, fold=1)
    utc = datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    with pytest.raises(PublicationValidationError) as error:
        Dataset(
            "d",
            "D",
            (Field("id", "ID", "datetime", False),),
            ((local,), (utc,)),
            ("id",),
            "source",
            "producer",
            None,
        )
    assert_issue(error, "duplicate_key", ("datasets", "d", "rows", 1, "keys"))


@pytest.mark.parametrize("owner", ["fields", "datasets", "metrics"])
def test_malformed_identifiers_have_immutable_diagnostics(
    owner: str,
    dataset: Dataset,
    metric: ImportedMetric,
) -> None:
    mutable_name: list[str] = []
    with pytest.raises(PublicationValidationError) as error:
        if owner == "fields":
            replace(dataset.fields[0], name=cast(str, mutable_name))
        elif owner == "datasets":
            replace(dataset, name=cast(str, mutable_name))
        else:
            replace(metric, identity=cast(str, mutable_name))
    identifier = "identity" if owner == "metrics" else "name"
    assert_issue(error, "invalid_type", (owner, identifier))
    mutable_name.append("changed after rejection")
    assert error.value.issue.location == (owner, identifier)
    assert type(error.value.issue.location) is tuple
    assert all(type(part) in (str, int) for part in error.value.issue.location)
