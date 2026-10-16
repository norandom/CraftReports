"""Concrete retained contract codecs using the existing canonical JSON profile."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import TypeAdapter, ValidationError

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.storage.schema import Deployment
from craftreport.application.dispatch_ports import RecordedHandoff
from craftreport.contracts import CommandIntent, EvidenceRef, JsonObject, Receipt
from craftreport.contracts.values import JsonValue, freeze_object, require_immutable

_receipt = TypeAdapter(Receipt)
_intent = TypeAdapter(CommandIntent)
_handoff = TypeAdapter(RecordedHandoff)
PURGED = b"\x00CRAFTREPORT-PURGED-CONTENT-V1\n"
type ContentKind = Literal["snapshot", "result"]


class TombstoneLimit(ValueError):
    """Selected valid identity cannot fit the bounded removal envelope."""


def _tombstone_fields(
    kind: ContentKind, deployment: Deployment, row: Mapping[str, object]
) -> JsonObject:
    names = (
        ("feed_id", "producer_version", "subject", "operation_id", "content_digest")
        if kind == "snapshot"
        else ("identity", "operation_id", "command_operation_id", "deployment_scope", "subject")
    )
    result: dict[str, JsonValue] = {
        "kind": kind,
        "schema_version": "1",
        "deployment_identity": deployment.identity,
        "deployment_epoch": deployment.epoch,
    }
    for name in names:
        value = row[name]
        if name == "producer_version":
            if type(value) is not int or not 0 < value < 2**63:
                raise ValueError("Invalid retained producer version")
            value = str(value)
        if value is None and name == "command_operation_id":
            result[name] = None
        elif isinstance(value, str) and value.strip():
            result[name] = value
        else:
            raise ValueError("Invalid retained removal identity")
    return result


def encode_tombstone(
    kind: ContentKind, deployment: Deployment, row: Mapping[str, object]
) -> tuple[bytes, str]:
    original = row[kind + "_digest"]
    if not isinstance(original, str) or re.fullmatch(r"[0-9a-f]{64}", original) is None:
        raise ValueError("Invalid original checksum")
    body, _ = encode_object(
        {**_tombstone_fields(kind, deployment, row), kind + "_digest": original}
    )
    if len(body) > 4096:
        raise TombstoneLimit("Removal envelope exceeds 4KiB")
    payload = PURGED + body
    return payload, hashlib.sha256(payload).hexdigest()


def decode_tombstone(
    payload: bytes,
    digest: str,
    kind: ContentKind,
    deployment: Deployment,
    row: Mapping[str, object],
) -> bool:
    if not payload.startswith(PURGED):
        return False
    _check(payload, digest)
    body = payload[len(PURGED) :]
    value = decode_object(body, hashlib.sha256(body).hexdigest(), max_bytes=4096)
    original = value.get(kind + "_digest")
    if (
        not isinstance(original, str)
        or re.fullmatch(r"[0-9a-f]{64}", original) is None
        or value != {**_tombstone_fields(kind, deployment, row), kind + "_digest": original}
    ):
        raise ValueError("Removal envelope identity differs")
    return True


def encode_handoff(value: RecordedHandoff) -> tuple[bytes, str]:
    require_immutable(value)
    data = cast(JsonObject, _handoff.dump_python(value, mode="json", warnings="error"))
    principal = cast(JsonObject, data["principal"])
    return _canonical(
        {
            **data,
            "principal": {
                **principal,
                "permitted_scopes": tuple(sorted(value.principal.permitted_scopes)),
            },
        }
    )


def decode_handoff(payload: bytes, digest: str) -> RecordedHandoff:
    _check(payload, digest)
    try:
        value = _handoff.validate_json(payload, strict=True, extra="forbid")
        if encode_handoff(value) != (payload, digest):
            raise ValueError("Noncanonical retained handoff")
        return value
    except (ValidationError, TypeError) as error:
        raise ValueError("Invalid retained handoff") from error


def _canonical(value: JsonObject) -> tuple[bytes, str]:
    payload = canonical_bytes(value, max_depth=None)
    return payload, hashlib.sha256(payload).hexdigest()


def _check(payload: bytes, digest: str) -> None:
    if type(payload) is not bytes or type(digest) is not str:
        raise ValueError("Invalid retained content types")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Retained content digest mismatch")


def encode_receipt(value: Receipt) -> tuple[bytes, str]:
    require_immutable(value)
    return _canonical(cast(JsonObject, _receipt.dump_python(value, mode="json", warnings="error")))


def decode_receipt(payload: bytes, digest: str) -> Receipt:
    _check(payload, digest)
    try:
        value = _receipt.validate_json(payload, strict=True, extra="forbid")
        if encode_receipt(value) != (payload, digest):
            raise ValueError("Noncanonical retained receipt")
        return value
    except (ValidationError, TypeError) as error:
        raise ValueError("Invalid retained receipt") from error


def encode_intent(value: CommandIntent) -> tuple[bytes, str]:
    require_immutable(value)
    return _canonical(cast(JsonObject, _intent.dump_python(value, mode="json", warnings="error")))


def decode_intent(payload: bytes, digest: str) -> CommandIntent:
    _check(payload, digest)
    try:
        value = _intent.validate_json(payload, strict=True, extra="forbid")
        if encode_intent(value) != (payload, digest):
            raise ValueError("Noncanonical retained intent")
        return value
    except (ValidationError, TypeError) as error:
        raise ValueError("Invalid retained intent") from error


_evidence = TypeAdapter(EvidenceRef)


def encode_evidence(value: EvidenceRef) -> tuple[bytes, str]:
    require_immutable(value)
    return _canonical(cast(JsonObject, _evidence.dump_python(value, mode="json", warnings="error")))


def decode_evidence(payload: bytes, digest: str) -> EvidenceRef:
    _check(payload, digest)
    try:
        value = _evidence.validate_json(payload, strict=True, extra="forbid")
        if encode_evidence(value) != (payload, digest):
            raise ValueError("Noncanonical retained evidence")
        return value
    except (ValidationError, TypeError) as error:
        raise ValueError("Invalid retained evidence") from error


def encode_object(value: JsonObject, *, max_bytes: int = 1_048_576) -> tuple[bytes, str]:
    payload = canonical_bytes(value)
    if len(payload) > max_bytes:
        raise ValueError("Retained object exceeds content limit")
    return payload, hashlib.sha256(payload).hexdigest()


def decode_object(payload: bytes, digest: str, *, max_bytes: int = 1_048_576) -> JsonObject:
    _check(payload, digest)
    if len(payload) > max_bytes:
        raise ValueError("Retained object exceeds content limit")
    value: object = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("Retained object required")
    result = cast(JsonObject, value)
    if encode_object(result, max_bytes=max_bytes) != (payload, digest):
        raise ValueError("Noncanonical retained object")
    return freeze_object(result)


_CHECK_IDS = (
    "definition",
    "bindings",
    "semantic_resolution",
    "layout_fit",
    "target_consistency",
    "artifact_consistency",
    "artifact_reopen",
    "metric_methodology",
    "compliance_statement",
)


@dataclass(frozen=True)
class _Check:
    check_id: str
    status: Literal["passed", "failed", "unevaluated", "not_applicable"]
    origin: Literal["craftreport", "external"]
    reason_code: str

    def __post_init__(self) -> None:
        if (
            self.check_id not in _CHECK_IDS
            or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", self.reason_code) is None
        ):
            raise ValueError("Invalid preparation check")


@dataclass(frozen=True)
class _Decision:
    requested_designation: Literal["draft", "validated"]
    draft_eligible: bool
    validated_release_eligible: bool
    blocking_checks: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(self.blocking_checks)) != len(self.blocking_checks) or not set(
            self.blocking_checks
        ) <= set(_CHECK_IDS):
            raise ValueError("Invalid preparation decision checks")


@dataclass(frozen=True)
class _Preparation:
    schema_version: Literal["1"]
    stage: Literal["prepared", "quality_evaluated"]
    prepared_digest: str
    validation_scope_digest: str
    checks: tuple[_Check, ...]
    decision: _Decision | None

    def __post_init__(self) -> None:
        count = 3 if self.stage == "prepared" else 9
        if any(
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for digest in (self.prepared_digest, self.validation_scope_digest)
        ):
            raise ValueError("Invalid preparation content identity")
        if tuple(check.check_id for check in self.checks) != _CHECK_IDS[:count]:
            raise ValueError("Invalid preparation check order")
        if (
            self.stage == "prepared"
            and (
                self.decision is not None
                or any(
                    check.status != "passed" or check.origin != "craftreport"
                    for check in self.checks
                )
            )
            or self.stage == "quality_evaluated"
            and self.decision is None
        ):
            raise ValueError("Invalid preparation stage data")


_preparation = TypeAdapter(_Preparation)


def validate_preparation(value: JsonObject, reference: EvidenceRef) -> tuple[bytes, str]:
    if len(encode_evidence(reference)[0]) > 3072:
        raise ValueError("Preparation reference exceeds retained bound")
    payload, digest = encode_object(value, max_bytes=16_384)
    parsed = _preparation.validate_json(payload, strict=True, extra="forbid")
    if parsed.stage != reference.scope or digest != reference.content_digest:
        raise ValueError("Preparation reference content differs")
    return payload, digest


@dataclass(frozen=True, slots=True)
class DecisionFact:
    schema_version: Literal["1"]
    operation_id: str
    feed_id: str
    requested_version: str
    requested_digest: str
    status: Literal["accepted", "existing", "stale_version", "version_conflict"]
    retained_version: str | None
    retained_digest: str | None
    high_water: str
    high_water_digest: str
    feed_revision: str


_decision_adapter = TypeAdapter(DecisionFact)


def decision_frame(fact: JsonObject) -> DecisionFact:
    payload, _ = encode_object(fact)
    if len(payload) > 65_536:
        raise ValueError("Decision metadata exceeds 64KiB")
    result = _decision_adapter.validate_json(payload, strict=True, extra="forbid")
    for value in (
        result.requested_version,
        result.retained_version,
        result.high_water,
        result.feed_revision,
    ):
        if value is not None and (
            re.fullmatch(r"[1-9][0-9]{0,18}", value) is None or int(value) >= 2**63
        ):
            raise ValueError("Invalid decision version")
    for value in (result.requested_digest, result.retained_digest, result.high_water_digest):
        if value is not None and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("Invalid decision digest")
    if not result.feed_id.strip() or not result.operation_id.strip():
        raise ValueError("Invalid decision identity")
    return result
