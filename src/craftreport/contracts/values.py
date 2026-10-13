"""Immutable JSON-shaped values and structural checks shared by contracts.

This copies retained containers; wire-profile validation and normalization belong
to the boundary codec. It performs no numeric, date, or string coercion.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from typing import cast
from uuid import UUID

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | tuple[JsonValue, ...] | JsonObject
)
type JsonObject = Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True, eq=False)
class _FrozenObject(Mapping[str, JsonValue]):
    """Owned tuple storage avoids read-only views of caller-mutable backing maps."""

    entries: tuple[tuple[str, JsonValue], ...]

    def __getitem__(self, key: str) -> JsonValue:
        for name, value in self.entries:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)


def freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return freeze_object(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise TypeError("Contract values cannot retain live handles")


def freeze_object(value: JsonObject) -> JsonObject:
    if any(type(key) is not str for key in value):
        raise TypeError("Object keys must be strings")
    return _FrozenObject(tuple((key, freeze_json(item)) for key, item in value.items()))


def require_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")


def require_positive(value: int, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


def require_unique[T](values: tuple[T, ...], field: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must be unique")


def require_enum(value: object, enum_type: type[Enum]) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"Invalid {enum_type.__name__}")


def require_immutable(value: object) -> None:
    """Reject mutable or live objects in generic typed outcome results."""
    if value is None or type(value) in (
        bool,
        int,
        float,
        str,
        bytes,
        Decimal,
        date,
        datetime,
        time,
        timedelta,
        UUID,
    ):
        return
    if isinstance(value, Enum):
        require_immutable(value.value)
        return
    if isinstance(value, (tuple, frozenset)):
        for item in cast(tuple[object, ...] | frozenset[object], value):
            require_immutable(item)
        return
    if is_dataclass(value) and not isinstance(value, type):
        parameters: object = getattr(value, "__dataclass_params__")
        if getattr(parameters, "frozen", False) is True:
            for field in fields(value):
                require_immutable(getattr(value, field.name))
            return
    raise TypeError("Outcome results must be recursively immutable plain values")
