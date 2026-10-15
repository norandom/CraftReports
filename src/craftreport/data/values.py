"""Immutable producer values; no financial calculation or wire coercion."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

type Scalar = str | bool | int | Decimal | date | datetime | None
type ScalarKind = Literal["text", "bool", "int64", "decimal", "date", "datetime"]


@dataclass(frozen=True, slots=True)
class Field:
    name: str
    label: str
    kind: ScalarKind
    nullable: bool
    unit: str | None = None
    precision: int | None = None
    scale: int | None = None

    def __post_init__(self) -> None:
        from craftreport.data.validation import validate_field

        validate_field(self)


@dataclass(frozen=True, slots=True)
class Dataset:
    name: str
    label: str
    fields: tuple[Field, ...]
    rows: tuple[tuple[Scalar, ...], ...]
    keys: tuple[str, ...]
    source_ref: str
    producer_id: str
    source_version: str | None

    def __post_init__(self) -> None:
        from craftreport.data.validation import validate_dataset

        validate_dataset(self)


@dataclass(frozen=True, slots=True)
class ImportedMetric:
    identity: str
    unit: str
    period: str | None
    as_of: datetime | None
    source_ref: str
    producer_id: str
    method_version: str
    shape: Literal["scalar", "series"]
    value_schema: Field
    labels: tuple[str, ...]
    values: tuple[Scalar, ...]
    external_evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        from craftreport.data.validation import validate_metric

        validate_metric(self)


@dataclass(frozen=True, slots=True)
class SnapshotRef:
    feed_id: str
    producer_version: int
    content_digest: str

    def __post_init__(self) -> None:
        from craftreport.data.validation import validate_snapshot_ref

        validate_snapshot_ref(self.feed_id, self.producer_version, self.content_digest)


@dataclass(frozen=True, slots=True)
class Snapshot:
    schema_version: Literal["1"]
    feed_id: str
    producer_version: int
    content_digest: str
    datasets: tuple[Dataset, ...]
    metrics: tuple[ImportedMetric, ...]
    observation_time: datetime | None
    generation_time: datetime | None
    received_at: datetime
    accepted_at: datetime

    def __post_init__(self) -> None:
        from craftreport.data.validation import validate_snapshot

        validate_snapshot(self)
