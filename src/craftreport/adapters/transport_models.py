"""Transport schema models, with explicit stable wire field names."""

from typing import Annotated, Literal

from pydantic import Field, RootModel

from craftreport.adapters.validation import StrictWireModel

Text = Annotated[str, Field(min_length=1)]
Token = Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_.-]{0,63}$")]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{0,47}$")]
Version = Annotated[str, Field(pattern=r"^[1-9][0-9]*$")]


class KeyWire(StrictWireModel):
    name: Name
    contract_version: Version


class ResourceWire(StrictWireModel):
    kind: Text
    identity: Text


class ExpectedWire(StrictWireModel):
    resource: ResourceWire
    version: Text


class EnvelopeWire(StrictWireModel):
    operation: Name
    contract_version: Version
    payload: dict[str, object]
    correlation_id: Text
    retry_key: Text | None = None
    expected_versions: list[ExpectedWire] = Field(default_factory=list[ExpectedWire])


class DiagnosticWire(StrictWireModel):
    operation: KeyWire
    stage: Token
    code: Token
    recovery: Literal["do_not_retry", "correct_request", "retry", "inspect", "reconcile"]
    location: list[Token | Annotated[int, Field(ge=0)]]


class EvidenceWire(StrictWireModel):
    identity: Text
    scope: Text
    operation_id: Text
    operation: KeyWire
    resource_versions: list[ExpectedWire]
    content_digest: Text | None


class StageWire(StrictWireModel):
    stage: Token
    state: Literal["passed", "failed", "pending", "not_applicable"]
    reason_code: Token
    evidence: list[EvidenceWire]


class CapabilityVersionWire(StrictWireModel):
    identity: Text
    version: Text


class ReceiptWire(StrictWireModel):
    operation_id: Text
    operation: KeyWire
    correlation_id: Text
    revision: Annotated[int, Field(ge=1)]
    state: Literal["accepted", "pending", "complete", "partial", "ambiguous", "failed"]
    capability_versions: list[CapabilityVersionWire]
    resources: list[ResourceWire]
    expected_versions: list[ExpectedWire]
    input_ref: Text | None
    result_ref: Text | None
    stages: list[StageWire]
    diagnostics: list[DiagnosticWire]
    evidence: list[EvidenceWire]
    deployment_epoch: Text
    retention_profile: Text
    result_availability: Literal["available", "missing", "inaccessible", "unavailable"]
    previous_operation_id: Text | None


class RejectionWire(StrictWireModel):
    correlation_id: Text
    diagnostic: DiagnosticWire


class InvocationWire(RootModel[ReceiptWire | RejectionWire]):
    pass


class ResultReadbackWire(StrictWireModel):
    receipt: ReceiptWire
    value: dict[str, object]


class ResultReadWire(RootModel[ResultReadbackWire | RejectionWire]):
    pass
