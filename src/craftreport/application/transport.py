"""Framework-free transport conversion port; composition supplies its adapter."""

from typing import Protocol

from craftreport.contracts import (
    Catalog,
    InvocationEnvelope,
    InvocationResult,
    JsonObject,
    OperationKey,
    OperationLimits,
)


class TransportWire(Protocol):
    def decode_envelope(self, value: JsonObject, limits: OperationLimits) -> InvocationEnvelope: ...

    def canonical_bytes(self, value: JsonObject) -> bytes: ...

    def encode_invocation_result(self, result: InvocationResult) -> JsonObject: ...

    def encode_catalog(self, catalog: Catalog) -> JsonObject: ...

    def envelope_schema(
        self, key: OperationKey | None = None, payload_schema: JsonObject | None = None
    ) -> JsonObject: ...

    def invocation_result_schema(self) -> JsonObject: ...

    def canonical_status(self, result: InvocationResult) -> int: ...

    def result_is_error(self, result: InvocationResult) -> bool: ...
