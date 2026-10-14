"""Validated immutable expectations for the single reviewed synthetic fixture."""

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .contracts import Sha256, Text, Value


class CellExpectation(Value):
    type: Literal["string", "number"]
    value: str | Annotated[float, Field(allow_inf_nan=False, strict=True)]

    @model_validator(mode="after")
    def matching_type(self) -> "CellExpectation":
        if (self.type == "string") != isinstance(self.value, str):
            raise ValueError("cell type and value disagree")
        return self


class FixtureSource(Value):
    file: Literal["reference.xlsx"]
    sha256: Sha256


class Authoring(Value):
    tool: Text
    version: Text
    created_utc: Text


class Marker(Value):
    address: Literal["D1"]
    value: Text


class Edit(Value):
    address: Literal["B3"]
    before: CellExpectation
    after: CellExpectation


class ChartExpectation(Value):
    count: Literal[1]
    type: Literal["line"]
    title: Text
    series_name: Text
    categories: Text
    values: Text
    anchor: Literal["F2"]


class Legend(Value):
    visible: bool
    position: Literal["b", "t", "l", "r", "tr"]
    overlay: bool


class Size(Value):
    width: Annotated[int, Field(gt=0, strict=True)]
    height: Annotated[int, Field(gt=0, strict=True)]


class Offset(Value):
    x: Annotated[int, Field(ge=0, strict=True)]
    y: Annotated[int, Field(ge=0, strict=True)]


class Presentation(Value):
    bold_cells: tuple[Text, ...]
    integer_cells: tuple[Text, ...]
    number_format: Literal["0"]
    legend: Legend
    chart_size_pixels: Size
    chart_offset_pixels: Offset


class FixtureExpectation(Value):
    schema_version: Literal[1]
    fixture: FixtureSource
    authoring: Authoring
    sheet: Literal["Report"]
    before: Mapping[str, CellExpectation]
    after: Mapping[str, CellExpectation]
    marker: Marker
    sentinels: tuple[Text, ...]
    edit: Edit
    chart: ChartExpectation
    presentation: Presentation

    @field_validator("before", "after")
    @classmethod
    def freeze_cells(cls, value: Mapping[str, CellExpectation]) -> Mapping[str, CellExpectation]:
        return MappingProxyType(dict(value))

    @model_validator(mode="after")
    def fixed_fixture(self) -> "FixtureExpectation":
        addresses = {"A1", "B1", "A2", "A3", "A4", "B2", "B3", "B4", "D1", "D2", "D3"}
        if set(self.before) != addresses or set(self.after) != addresses:
            raise ValueError("expected fixed eleven cells")
        if set(self.sentinels) != addresses - {self.edit.address}:
            raise ValueError("expected all unchanged sentinels")
        if any(self.before[key] != self.after[key] for key in self.sentinels):
            raise ValueError("sentinel expectations changed")
        if self.before["D1"] != CellExpectation(type="string", value=self.marker.value):
            raise ValueError("marker expectation disagrees")
        if self.before["B3"] != self.edit.before or self.after["B3"] != self.edit.after:
            raise ValueError("edit expectation disagrees")
        if self.edit.before == self.edit.after:
            raise ValueError("expected changed edit")
        if not set(self.presentation.bold_cells + self.presentation.integer_cells) <= addresses:
            raise ValueError("presentation references unknown cells")
        return self

    @classmethod
    def read(cls, path: Path) -> "FixtureExpectation":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
