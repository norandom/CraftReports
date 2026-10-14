"""Explicit canonical serializers and shared REST/MCP outcome semantics."""

from craftreport.adapters.canonical import canonical_bytes, wire_value
from craftreport.adapters.schema_embedding import embed_payload_schema
from craftreport.adapters.transport_models import EnvelopeWire, InvocationWire, ResultReadWire
from craftreport.adapters.validation import decode_envelope
from craftreport.contracts import (
    CapabilityManifest,
    CapabilityView,
    Catalog,
    Diagnostic,
    EvidenceRef,
    ExpectedVersion,
    InvocationEnvelope,
    InvocationResult,
    JsonObject,
    OperationDescriptor,
    OperationKey,
    OperationLimits,
    Receipt,
    ReceiptState,
    Rejection,
    ResourceRef,
    ResultReadback,
    StageResult,
    VerificationRecord,
)
from craftreport.contracts.values import freeze_object


def _key(value: OperationKey) -> JsonObject:
    return {"name": value.name, "contract_version": value.contract_version}


def _resource(value: ResourceRef) -> JsonObject:
    return {"kind": value.kind, "identity": value.identity}


def _expected(value: ExpectedVersion) -> JsonObject:
    return {"resource": _resource(value.resource), "version": value.version}


def _diagnostic(value: Diagnostic) -> JsonObject:
    return {
        "operation": _key(value.operation),
        "stage": value.stage,
        "code": value.code,
        "recovery": value.recovery.value,
        "location": list(value.location),
    }


def _evidence(value: EvidenceRef) -> JsonObject:
    return {
        "identity": value.identity,
        "scope": value.scope,
        "operation_id": value.operation_id,
        "operation": _key(value.operation),
        "resource_versions": [_expected(v) for v in value.resource_versions],
        "content_digest": value.content_digest,
    }


def _stage(value: StageResult) -> JsonObject:
    return {
        "stage": value.stage,
        "state": value.state.value,
        "reason_code": value.reason_code,
        "evidence": [_evidence(v) for v in value.evidence],
    }


def _receipt(value: Receipt) -> JsonObject:
    return {
        "operation_id": value.operation_id,
        "operation": _key(value.operation),
        "correlation_id": value.correlation_id,
        "revision": value.revision,
        "state": value.state.value,
        "capability_versions": [
            {"identity": v.identity, "version": v.version} for v in value.capability_versions
        ],
        "resources": [_resource(v) for v in value.resources],
        "expected_versions": [_expected(v) for v in value.expected_versions],
        "input_ref": value.input_ref,
        "result_ref": value.result_ref,
        "stages": [_stage(v) for v in value.stages],
        "diagnostics": [_diagnostic(v) for v in value.diagnostics],
        "evidence": [_evidence(v) for v in value.evidence],
        "deployment_epoch": value.deployment_epoch,
        "retention_profile": value.retention_profile,
        "result_availability": value.result_availability.value,
        "previous_operation_id": value.previous_operation_id,
    }


def encode_invocation_result(result: InvocationResult) -> JsonObject:
    """Encode every domain field explicitly; validate the published output contract."""
    value = (
        {"correlation_id": result.correlation_id, "diagnostic": _diagnostic(result.diagnostic)}
        if isinstance(result, Rejection)
        else _receipt(result)
    )
    InvocationWire.model_validate(value, strict=True)
    canonical_bytes(value, max_depth=None)
    return freeze_object(value)


def encode_result_readback(result: ResultReadback | Rejection) -> JsonObject:
    value = (
        encode_invocation_result(result)
        if isinstance(result, Rejection)
        else {"receipt": _receipt(result.receipt), "value": result.value}
    )
    ResultReadWire.model_validate(wire_value(value, max_depth=None), strict=True)
    canonical_bytes(value, max_depth=None)
    return freeze_object(value)


def result_readback_schema() -> JsonObject:
    return freeze_object({**ResultReadWire.model_json_schema(), "type": "object"})


def envelope_schema(
    key: OperationKey | None = None, payload_schema: JsonObject | None = None
) -> JsonObject:
    schema = EnvelopeWire.model_json_schema()
    if key is not None:
        schema["properties"]["operation"]["const"] = key.name
        schema["properties"]["contract_version"]["const"] = key.contract_version
    if payload_schema is not None:
        schema["properties"]["payload"] = embed_payload_schema(payload_schema)
    return freeze_object(schema)


def invocation_result_schema() -> JsonObject:
    """MCP requires an object root, including both canonical result alternatives."""
    return freeze_object({**InvocationWire.model_json_schema(), "type": "object"})


def _descriptor(value: OperationDescriptor) -> JsonObject:
    return {
        "key": _key(value.key),
        "kind": value.kind.value,
        "input_schema": value.input_schema,
        "result_schema": value.result_schema,
        "starts_business_work": value.starts_business_work,
        "changes_business_state": value.changes_business_state,
        "resources": list(value.resources),
        "required_capabilities": [
            {"identity": v.identity, "version_range": v.version_range, "target_mode": v.target_mode}
            for v in value.required_capabilities
        ],
        "required_services": list(value.required_services),
        "limits": {
            "max_input_bytes": value.limits.max_input_bytes,
            "max_nesting_depth": value.limits.max_nesting_depth,
            "max_output_bytes": value.limits.max_output_bytes,
        },
        "completion_evidence": {"required_stages": list(value.completion_evidence.required_stages)},
    }


def _manifest(value: CapabilityManifest) -> JsonObject:
    return {
        "identity": value.identity,
        "package": value.package,
        "version": value.version,
        "core_contract_range": value.core_contract_range,
        "provided": [{"identity": v.identity, "version": v.version} for v in value.provided],
        "required": [
            {"identity": v.identity, "version_range": v.version_range, "target_mode": v.target_mode}
            for v in value.required
        ],
        "settings_schema": value.settings_schema,
        "operations": [_descriptor(v) for v in value.operations],
        "implementation_digest": value.implementation_digest,
    }


def _record(value: VerificationRecord) -> JsonObject:
    return {
        "package": value.package,
        "package_version": value.package_version,
        "implementation_digest": value.implementation_digest,
        "core_contract_version": value.core_contract_version,
        "fixture_suite": value.fixture_suite,
        "dependency_versions": [
            {"identity": v.identity, "version": v.version} for v in value.dependency_versions
        ],
        "state": value.state.value,
        "scope": value.scope,
        "evidence": [_evidence(v) for v in value.evidence],
    }


def _capability(value: CapabilityView) -> JsonObject:
    return {
        "manifest": _manifest(value.manifest),
        "verification": value.verification.value,
        "record": None if value.record is None else _record(value.record),
    }


def encode_catalog(catalog: Catalog) -> JsonObject:
    """Serialize an already authorized catalog without adding registry contents."""
    value: JsonObject = {
        "operations": [_descriptor(v) for v in catalog.operations],
        "capabilities": [_capability(v) for v in catalog.capabilities],
        "deployment_epoch": catalog.deployment_epoch,
        "retention_profile": catalog.retention_profile,
        "core_contract_version": catalog.core_contract_version,
    }
    if catalog.execution_limits is not None:
        limits = catalog.execution_limits
        value = {
            **value,
            "execution_limits": {
                "capacity": limits.capacity,
                "response_seconds": limits.response_seconds,
                "shutdown_seconds": limits.shutdown_seconds,
            },
        }
    canonical_bytes(value, max_depth=None)
    return freeze_object(value)


_STATUS = {
    "not_found": 404,
    "unsupported_operation": 404,
    "receipt_missing": 404,
    "access_denied": 404,
    "unauthenticated": 401,
    "forbidden": 403,
    "invalid_input": 422,
    "query_required": 422,
    "limit_exceeded": 413,
    "conflict": 409,
    "retry_conflict": 409,
    "version_conflict": 409,
    "unavailable": 503,
    "service_unavailable": 503,
    "unsupported_capability": 503,
    "capacity_exceeded": 429,
    "capacity": 429,
}


def canonical_status(result: InvocationResult | ResultReadback) -> int:
    if isinstance(result, ResultReadback):
        result = result.receipt
    if isinstance(result, Rejection):
        return _STATUS.get(result.diagnostic.code, 503)
    return 202 if result.state in (ReceiptState.ACCEPTED, ReceiptState.PENDING) else 200


def result_is_error(result: InvocationResult | ResultReadback) -> bool:
    if isinstance(result, ResultReadback):
        result = result.receipt
    return isinstance(result, Rejection) or result.state in (
        ReceiptState.FAILED,
        ReceiptState.PARTIAL,
        ReceiptState.AMBIGUOUS,
    )


class TransportWireAdapter:
    """Concrete boundary injected behind the application-owned transport port."""

    def decode_envelope(self, value: JsonObject, limits: OperationLimits) -> InvocationEnvelope:
        return decode_envelope(value, limits)

    def canonical_bytes(self, value: JsonObject) -> bytes:
        return canonical_bytes(value, max_depth=None)

    def encode_invocation_result(self, result: InvocationResult) -> JsonObject:
        return encode_invocation_result(result)

    def encode_result_readback(self, result: ResultReadback | Rejection) -> JsonObject:
        return encode_result_readback(result)

    def result_readback_schema(self) -> JsonObject:
        return result_readback_schema()

    def encode_catalog(self, catalog: Catalog) -> JsonObject:
        return encode_catalog(catalog)

    def envelope_schema(
        self, key: OperationKey | None = None, payload_schema: JsonObject | None = None
    ) -> JsonObject:
        return envelope_schema(key, payload_schema)

    def invocation_result_schema(self) -> JsonObject:
        return invocation_result_schema()

    def canonical_status(self, result: InvocationResult | ResultReadback) -> int:
        return canonical_status(result)

    def result_is_error(self, result: InvocationResult | ResultReadback) -> bool:
        return result_is_error(result)
