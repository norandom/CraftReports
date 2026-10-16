"""Bounded production asset codecs and explicit semantic hash projections."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
from typing import Literal, cast

from pydantic import TypeAdapter

from craftreport.adapters import report_models as m
from craftreport.adapters.canonical import WireFailure, bounded_object, canonical_bytes
from craftreport.adapters.report_models import (
    DefinitionWire,
    PackManifest,
    ParameterDeclarationWire,
)
from craftreport.adapters.schema_embedding import close_schema
from craftreport.adapters.snapshot_models import MetricWire, ParameterWire, SnapshotRefWire
from craftreport.adapters.snapshot_wire import (
    decode_metric,
    decode_parameter,
    decode_scalar,
    encode_cell,
    encode_metric,
    encode_parameter,
)
from craftreport.adapters.validation import PydanticCodec, StrictWireModel, construct
from craftreport.contracts import OperationLimits
from craftreport.contracts.values import JsonObject, JsonValue
from craftreport.data.requirements import InputRequirements
from craftreport.data.values import Field, Scalar, SnapshotRef
from craftreport.policies.values import QualityEvaluation, ReleasePolicy
from craftreport.reporting import ports as p
from craftreport.reporting.definitions import (
    ParameterDefinition,
    ParameterValue,
    ReportDefinition,
    text,
)
from craftreport.reporting.prepared import (
    PreparedColumn,
    PreparedLineChart,
    PreparedReport,
    PreparedSeries,
    PreparedTable,
)
from craftreport.themes.values import Theme

DEFINITION = TypeAdapter(DefinitionWire)
THEME = TypeAdapter(Theme)
MANIFEST = TypeAdapter(PackManifest)


def _pairs(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate field")
    return result


def _decode[T](data: bytes, adapter: TypeAdapter[T], maximum: int) -> T:
    try:
        if len(data) > maximum:
            raise ValueError("Asset size")
        content = cast(JsonObject, json.loads(data, object_pairs_hook=_pairs))
        normalized = canonical_bytes(bounded_object(content, maximum))
        return adapter.validate_json(normalized, strict=True, extra="forbid")
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise WireFailure("invalid_asset") from None


def decode_manifest(data: bytes) -> PackManifest:
    return _decode(data, MANIFEST, 65536)


def _parameter(wire: ParameterDeclarationWire) -> ParameterDefinition:
    def scalar(value: ParameterWire | None) -> Scalar:
        if value is None:
            return None
        if value.kind != wire.kind:
            raise WireFailure("invalid_asset")
        return decode_parameter(cast(JsonObject, value.model_dump(mode="json")))

    return ParameterDefinition(
        wire.name,
        wire.kind,
        wire.required,
        scalar(wire.default),
        tuple(scalar(v) for v in wire.choices),
        scalar(wire.minimum),
        scalar(wire.maximum),
    )


def decode_definition(data: bytes) -> ReportDefinition:
    try:
        wire = _decode(data, DEFINITION, 65536)
        return construct(
            ReportDefinition,
            wire,
            {
                "parameters": tuple(
                    _parameter(p)
                    for p in cast(tuple[ParameterDeclarationWire, ...], getattr(wire, "parameters"))
                )
            },
        )
    except (ValueError, TypeError, ArithmeticError):
        raise WireFailure("invalid_asset") from None


def encode_definition(value: ReportDefinition) -> bytes:
    parameters: list[ParameterDeclarationWire] = []
    for parameter in value.parameters:
        raw: dict[str, object] = {
            "name": parameter.name,
            "kind": parameter.kind,
            "required": parameter.required,
            "choices": tuple(dict(encode_parameter(v)) for v in parameter.choices),
        }
        raw.update(
            {
                name: dict(encode_parameter(v))
                for name in ("default", "minimum", "maximum")
                if (v := cast(Scalar, getattr(parameter, name))) is not None
            }
        )
        parameters.append(ParameterDeclarationWire.model_validate(raw))
    content = {
        field.name: getattr(value, field.name)
        for field in fields(value)
        if field.name != "parameters"
    }
    wire = DefinitionWire.model_validate({**content, "parameters": tuple(parameters)})
    return canonical_bytes(
        bounded_object(cast(JsonObject, wire.model_dump(mode="json", exclude_none=True)), 65536)
    )


def definition_identifier(value: ReportDefinition) -> str:
    return sha256(encode_definition(value)).hexdigest()


def _theme_object(value: Theme) -> JsonObject:
    # JSON mode normalizes permitted integer presentation sizes to floats.
    normalized = THEME.validate_json(THEME.dump_json(value), strict=True, extra="forbid")
    return cast(JsonObject, THEME.dump_python(normalized, mode="json"))


def theme_identifier(value: Theme) -> str:
    content = dict(_theme_object(value))
    pin = dict(cast(JsonObject, content["version_pin"]))
    del pin["content_digest"]
    return sha256(canonical_bytes({**content, "version_pin": pin})).hexdigest()


def encode_theme(value: Theme) -> bytes:
    return canonical_bytes(bounded_object(_theme_object(value), 32768))


def decode_theme(data: bytes) -> Theme:
    value = _decode(data, THEME, 32768)
    if value.version_pin.content_digest != theme_identifier(value):
        raise WireFailure("invalid_asset")
    return value


def asset_schema(name: Literal["definition", "theme", "manifest"]) -> JsonObject:
    schema = {"definition": DEFINITION, "theme": THEME, "manifest": MANIFEST}[name].json_schema()

    return close_schema(schema)


def _members(value: object) -> dict[str, object]:
    assert is_dataclass(value) and not isinstance(value, type)
    return {field.name: getattr(value, field.name) for field in fields(value)}


def _dump(model: StrictWireModel) -> JsonObject:
    # Presentation int/float unions normalize through immediate strict revalidation.
    normalized = type(model).model_validate_json(
        model.model_dump_json(warnings=False), strict=True, extra="forbid"
    )
    return cast(JsonObject, normalized.model_dump(mode="json"))


def _tag(value: Scalar) -> ParameterWire:
    return ParameterWire.model_validate(dict(encode_parameter(value)))


def _untag(value: ParameterWire) -> Scalar:
    return decode_parameter(cast(JsonObject, value.model_dump(mode="json")))


def _snapshot(value: SnapshotRefWire) -> SnapshotRef:
    return construct(
        SnapshotRef, value, {"producer_version": int(cast(str, getattr(value, "producer_version")))}
    )


def _snapshot_wire(value: SnapshotRef) -> SnapshotRefWire:
    return SnapshotRefWire(**{**_members(value), "producer_version": str(value.producer_version)})


def _table(value: m.TableWire) -> PreparedTable:
    columns = cast(tuple[PreparedColumn, ...], getattr(value, "columns"))
    rows = cast(tuple[tuple[JsonValue, ...], ...], getattr(value, "rows"))
    return construct(
        PreparedTable,
        value,
        {
            "rows": tuple(
                tuple(decode_scalar(v, c.field) for v, c in zip(row, columns, strict=True))
                for row in rows
            )
        },
    )


def _table_wire(value: PreparedTable) -> m.TableWire:
    return m.TableWire(
        **{
            **_members(value),
            "rows": tuple(
                tuple(encode_cell(v, c.field) for v, c in zip(row, value.columns, strict=True))
                for row in value.rows
            ),
        }
    )


def _series(value: m.SeriesWire) -> PreparedSeries:
    field = cast(Field, getattr(value, "field"))
    return construct(
        PreparedSeries,
        value,
        {
            "values": tuple(
                decode_scalar(v, field)
                for v in cast(tuple[JsonValue, ...], getattr(value, "values"))
            )
        },
    )


def _series_wire(value: PreparedSeries) -> m.SeriesWire:
    return m.SeriesWire(
        **{**_members(value), "values": tuple(encode_cell(v, value.field) for v in value.values)}
    )


def _chart(value: m.ChartWire) -> PreparedLineChart:
    field = cast(Field, getattr(value, "category_schema"))
    return construct(
        PreparedLineChart,
        value,
        {
            "categories": tuple(
                decode_scalar(v, field)
                for v in cast(tuple[JsonValue, ...], getattr(value, "categories"))
            ),
            "series": tuple(
                _series(v) for v in cast(tuple[m.SeriesWire, ...], getattr(value, "series"))
            ),
        },
    )


def _chart_wire(value: PreparedLineChart) -> m.ChartWire:
    return m.ChartWire(
        **{
            **_members(value),
            "categories": tuple(encode_cell(v, value.category_schema) for v in value.categories),
            "series": tuple(_series_wire(v) for v in value.series),
        }
    )


def _content(value: PreparedReport) -> JsonObject:
    content = _members(value)
    content.pop("content_digest")
    content.update(
        snapshot=_snapshot_wire(value.snapshot),
        resolved_parameters=tuple((k, _tag(v)) for k, v in value.resolved_parameters),
        tables=tuple(_table_wire(v) for v in value.tables),
        charts=tuple(_chart_wire(v) for v in value.charts),
        metric_provenance=tuple(
            MetricWire.model_validate_json(
                canonical_bytes(encode_metric(v)), strict=True, extra="forbid"
            )
            for v in value.metric_provenance
        ),
    )
    return _dump(m.PreparedContentWire(**content))


def prepared_identifier(value: PreparedReport) -> str:
    return sha256(canonical_bytes(_content(value))).hexdigest()


def _prepared(value: m.PreparedWire) -> PreparedReport:
    result = construct(
        PreparedReport,
        value,
        {
            "snapshot": _snapshot(cast(SnapshotRefWire, getattr(value, "snapshot"))),
            "resolved_parameters": tuple(
                (k, _untag(v))
                for k, v in cast(
                    tuple[tuple[str, ParameterWire], ...], getattr(value, "resolved_parameters")
                )
            ),
            "tables": tuple(
                _table(v) for v in cast(tuple[m.TableWire, ...], getattr(value, "tables"))
            ),
            "charts": tuple(
                _chart(v) for v in cast(tuple[m.ChartWire, ...], getattr(value, "charts"))
            ),
            "metric_provenance": tuple(
                decode_metric(cast(JsonObject, v.model_dump(mode="json")))
                for v in cast(tuple[MetricWire, ...], getattr(value, "metric_provenance"))
            ),
        },
    )
    _prepared_object(result)
    return result


def _prepared_object(value: PreparedReport) -> JsonObject:
    content = _content(value)
    if sha256(canonical_bytes(content)).hexdigest() != value.content_digest:
        raise WireFailure("invalid_digest", location=("content_digest",))
    return {**content, "content_digest": value.content_digest}


def validation_scope_identifier(value: ReleasePolicy) -> str:
    return sha256(
        canonical_bytes(
            {
                "schema_version": "1",
                "required_checks": [str(k) for k in value.required_checks],
                "scope_label": value.scope_label,
            }
        )
    ).hexdigest()


def _request[T: p.ValidateRequest](cls: type[T], value: StrictWireModel) -> T:
    parameters = tuple(
        construct(ParameterValue, v, {"value": _untag(cast(ParameterWire, getattr(v, "value")))})
        for v in cast(tuple[m.ParameterValueWire, ...], getattr(value, "parameters"))
    )
    for parameter in parameters:
        if parameter.value is None:
            raise WireFailure("invalid_input", location=("parameters",))
        if type(parameter.value) is str:
            text(parameter.value, ("parameters",), 512, empty=True)
    replacement: dict[str, object] = {
        "parameters": parameters,
        "definition": None
        if getattr(value, "definition") is None
        else decode_definition(
            canonical_bytes(cast(JsonObject, getattr(value, "definition").model_dump(mode="json")))
        ),
    }
    if cls is p.PrepareRequest:
        replacement["snapshot"] = _snapshot(cast(SnapshotRefWire, getattr(value, "snapshot")))
    return construct(cls, value, replacement)


def _request_object(value: p.ValidateRequest) -> JsonObject:
    content = {
        **_members(value),
        "definition": None
        if value.definition is None
        else DEFINITION.validate_json(
            encode_definition(value.definition), strict=True, extra="forbid"
        ),
        "parameters": tuple(
            m.ParameterValueWire(**{"name": v.name, "value": _tag(v.value)})
            for v in value.parameters
        ),
    }
    if isinstance(value, p.PrepareRequest):
        content["snapshot"] = _snapshot_wire(value.snapshot)
    return _dump(
        (m.PrepareWire if isinstance(value, p.PrepareRequest) else m.ValidateWire)(**content)
    )


def _validation(value: m.ValidationWire) -> p.ValidationResult:
    return construct(
        p.ValidationResult,
        value,
        {
            "resolved_parameters": tuple(
                (k, _untag(v))
                for k, v in cast(
                    tuple[tuple[str, ParameterWire], ...], getattr(value, "resolved_parameters")
                )
            )
        },
    )


def _validation_object(value: p.ValidationResult) -> JsonObject:
    return _dump(
        m.ValidationWire(
            **{
                **_members(value),
                "resolved_parameters": tuple((k, _tag(v)) for k, v in value.resolved_parameters),
            }
        )
    )


def _result(value: m.PreparationWire) -> p.PreparationResult:
    return p.PreparationResult(
        _prepared(cast(m.PreparedWire, getattr(value, "prepared"))),
        cast(QualityEvaluation, getattr(value, "quality")),
    )


def _result_object(value: p.PreparationResult) -> JsonObject:
    return _dump(
        m.PreparationWire(
            **{
                "prepared": m.PreparedWire.model_validate_json(
                    canonical_bytes(_prepared_object(value.prepared)), strict=True, extra="forbid"
                ),
                "quality": value.quality,
            }
        )
    )


def _codec[T, M: StrictWireModel](
    model: type[M],
    decode: Callable[[M], T],
    encode: Callable[[T], JsonObject],
    large: bool = False,
    *,
    request: bool = False,
) -> PydanticCodec[T, M]:
    return PydanticCodec(
        model,
        decode,
        encode,
        OperationLimits(
            65536 if request else 8388608 if large else 1048576, 32, 8388608 if large else 1048576
        ),
        json_mode=True,
    )


def prepared_codec() -> PydanticCodec[PreparedReport, m.PreparedWire]:
    return _codec(m.PreparedWire, _prepared, _prepared_object, True)


def quality_codec() -> PydanticCodec[QualityEvaluation, m.QualityWire]:
    return _codec(
        m.QualityWire,
        lambda v: construct(QualityEvaluation, v, {}),
        lambda v: _dump(m.QualityWire(**_members(v))),
    )


def validation_request_codec() -> PydanticCodec[p.ValidateRequest, m.ValidateWire]:
    return _codec(
        m.ValidateWire, lambda v: _request(p.ValidateRequest, v), _request_object, request=True
    ).for_input()


def preparation_request_codec() -> PydanticCodec[p.PrepareRequest, m.PrepareWire]:
    return _codec(
        m.PrepareWire, lambda v: _request(p.PrepareRequest, v), _request_object, request=True
    ).for_input()


def validation_result_codec() -> ReportResultCodec[p.ValidationResult, m.ValidationWire]:
    return ReportResultCodec(_codec(m.ValidationWire, _validation, _validation_object))


def discovery_request_codec() -> PydanticCodec[p.EmptyRequest, m.EmptyWire]:
    return _codec(m.EmptyWire, lambda v: p.EmptyRequest(), lambda v: {}, request=True).for_input()


def discovery_result_codec() -> PydanticCodec[p.DiscoveryResult, m.DiscoveryWire]:
    return _codec(
        m.DiscoveryWire,
        lambda v: construct(p.DiscoveryResult, v, {}),
        lambda v: _dump(m.DiscoveryWire(**_members(v))),
    )


def preparation_result_codec() -> ReportResultCodec[p.PreparationResult, m.PreparationWire]:
    return ReportResultCodec(_codec(m.PreparationWire, _result, _result_object, True))


@dataclass(frozen=True, slots=True)
class ReportResultCodec[T, M: StrictWireModel]:
    success: PydanticCodec[T, M]

    def _failure(self) -> PydanticCodec[p.ReportFailure, m.FailureWire]:
        return PydanticCodec(
            m.FailureWire,
            lambda v: v.failure,
            lambda v: _dump(m.FailureWire(failure=v)),
            OperationLimits(263168, 32, 263168),
            json_mode=True,
        )

    @property
    def limits(self) -> OperationLimits:
        return self.success.limits

    def decode(self, value: JsonObject) -> T | p.ReportFailure:
        if "failure" in value:
            return self._failure().decode(value)
        return self.success.decode(value)

    def encode(self, value: T | p.ReportFailure) -> JsonObject:
        if isinstance(value, p.ReportFailure):
            return self._failure().encode(value)
        return self.success.encode(value)

    def schema(self) -> JsonObject:
        return close_schema(TypeAdapter(self.success.model | m.FailureWire).json_schema())


def requirements_schema() -> JsonObject:
    return close_schema(TypeAdapter(InputRequirements).json_schema())


def pack_summary_schema() -> JsonObject:
    return close_schema(TypeAdapter(p.PackSummary).json_schema())
