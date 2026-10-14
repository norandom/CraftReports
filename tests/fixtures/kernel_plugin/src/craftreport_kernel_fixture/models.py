"""Strict wire schemas explicitly converted to immutable handler values."""

from dataclasses import dataclass

from pydantic import Field

from craftreport.adapters.validation import PydanticCodec, StrictWireModel
from craftreport.contracts import OperationLimits

LIMITS = OperationLimits(max_input_bytes=4096, max_nesting_depth=8, max_output_bytes=4096)


@dataclass(frozen=True, slots=True)
class Settings:
    resource_kind: str
    fail_open: bool = False
    fail_close: bool = False


class SettingsWire(StrictWireModel):
    resource_kind: str = Field(min_length=1, max_length=64)
    fail_open: bool = False
    fail_close: bool = False


SETTINGS = PydanticCodec(
    SettingsWire,
    lambda wire: Settings(wire.resource_kind, wire.fail_open, wire.fail_close),
    lambda value: {
        "resource_kind": value.resource_kind,
        "fail_open": value.fail_open,
        "fail_close": value.fail_close,
    },
    LIMITS,
).for_input()


@dataclass(frozen=True, slots=True)
class ReadRequest:
    resource: str


@dataclass(frozen=True, slots=True)
class WriteRequest:
    resource: str
    value: str


@dataclass(frozen=True, slots=True)
class Result:
    value: str
    version: str


class ReadWire(StrictWireModel):
    resource: str = Field(min_length=1, max_length=128)


class WriteWire(ReadWire):
    value: str = Field(max_length=512)


class ResultWire(StrictWireModel):
    value: str
    version: str = Field(min_length=1)


READ = PydanticCodec(
    ReadWire,
    lambda wire: ReadRequest(wire.resource),
    lambda value: {"resource": value.resource},
    LIMITS,
).for_input()
WRITE = PydanticCodec(
    WriteWire,
    lambda wire: WriteRequest(wire.resource, wire.value),
    lambda value: {"resource": value.resource, "value": value.value},
    LIMITS,
).for_input()
RESULT = PydanticCodec(
    ResultWire,
    lambda wire: Result(wire.value, wire.version),
    lambda value: {"value": value.value, "version": value.version},
    LIMITS,
)
