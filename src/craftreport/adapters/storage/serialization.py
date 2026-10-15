"""Concrete retained contract codecs using the existing canonical JSON profile."""

import hashlib
from typing import cast

from pydantic import TypeAdapter, ValidationError

from craftreport.adapters.canonical import canonical_bytes
from craftreport.contracts import CommandIntent, JsonObject, Receipt
from craftreport.contracts.values import require_immutable

_receipt = TypeAdapter(Receipt)
_intent = TypeAdapter(CommandIntent)


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
