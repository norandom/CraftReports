"""Immutable app external-effect facts, fsync durability, digest readback and recovery."""

import json
import os
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import uuid4

from craftreport.contracts.values import JsonObject
from craftreport_gridcraft.codecs import (
    intent_codec,
    observation_fact_codec,
    pointer_codec,
)
from craftreport_gridcraft.values import (
    AppIntentFact,
    AppObservationFact,
    CurrentObservationPointer,
    TargetRecovery,
)

_TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}")


class FactUnavailable(RuntimeError):
    """Raised when a retained fact or index is torn, corrupt, or unreadable."""


def _unfreeze(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(k): _unfreeze(v) for k, v in mapping.items()}
    if isinstance(value, (list, tuple)):
        seq = cast(Sequence[object], value)
        return [_unfreeze(v) for v in seq]
    return value


def _validate_token(value: str) -> None:
    if not _TOKEN.fullmatch(value):
        raise ValueError(f"Invalid identifier token: {value!r}")


def _safe_path(directory: Path, filename: str) -> Path:
    _validate_token(filename.removesuffix(".json"))
    target = (directory / filename).resolve()
    if not target.is_relative_to(directory.resolve()):
        raise ValueError("Path traversal rejected")
    return target


def _canonical_write(dest: Path, tmp_dir: Path, data: bytes, expected_digest: str) -> None:
    tmp_path = tmp_dir / f"{uuid4().hex}.tmp"
    with open(tmp_path, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    tmp_path.replace(dest)
    actual_digest = sha256(dest.read_bytes()).hexdigest()
    if actual_digest != expected_digest:
        raise FactUnavailable(f"Digest mismatch after write: {actual_digest} != {expected_digest}")


class AppFacts:
    """Retain and verify immutable operation-linked facts under a private configured root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.intents_dir = self.root / "intents"
        self.observations_dir = self.root / "observations"
        self.indexes_dir = self.root / "indexes"
        self.tmp_dir = self.root / "tmp"
        for directory in (self.intents_dir, self.observations_dir, self.indexes_dir, self.tmp_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def record_intent(self, intent: AppIntentFact) -> AppIntentFact:
        dest = _safe_path(self.intents_dir, f"{intent.operation_id}.json")
        encoded = intent_codec().encode(intent)
        data = json.dumps(_unfreeze(encoded), sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = sha256(data).hexdigest()
        if dest.is_file():
            existing = self.read_intent(intent.operation_id)
            if existing is not None and existing == intent:
                return existing
            raise ValueError("Immutable intent cannot be altered")
        _canonical_write(dest, self.tmp_dir, data, digest)
        verified = self.read_intent(intent.operation_id)
        if verified is None or verified != intent:
            raise FactUnavailable("Independent digest readback failed for intent")
        return verified

    def read_intent(self, operation_id: str) -> AppIntentFact | None:
        dest = _safe_path(self.intents_dir, f"{operation_id}.json")
        if not dest.is_file():
            return None
        try:
            content = dest.read_bytes()
            actual_digest = sha256(content).hexdigest()
            parsed = cast(JsonObject, json.loads(content.decode("utf-8")))
            fact = intent_codec().decode(parsed)
            expected_data = json.dumps(
                _unfreeze(intent_codec().encode(fact)), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if actual_digest != sha256(expected_data).hexdigest():
                raise FactUnavailable(f"Corrupt intent fact: digest mismatch for {operation_id}")
            return fact
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as error:
            raise FactUnavailable(f"Corrupt intent fact for {operation_id}: {error}") from error

    def record_observation(self, fact: AppObservationFact) -> AppObservationFact:
        dest = _safe_path(self.observations_dir, f"{fact.operation_id}.json")
        encoded = observation_fact_codec().encode(fact)
        data = json.dumps(_unfreeze(encoded), sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = sha256(data).hexdigest()
        if dest.is_file():
            existing = self.read_observation(fact.operation_id)
            if existing is not None and existing == fact:
                return existing
            raise ValueError("Immutable observation cannot be altered")
        _canonical_write(dest, self.tmp_dir, data, digest)
        verified = self.read_observation(fact.operation_id)
        if verified is None or verified != fact:
            raise FactUnavailable("Independent digest readback failed for observation")
        return verified

    def read_observation(self, operation_id: str) -> AppObservationFact | None:
        dest = _safe_path(self.observations_dir, f"{operation_id}.json")
        if not dest.is_file():
            return None
        try:
            content = dest.read_bytes()
            actual_digest = sha256(content).hexdigest()
            parsed = cast(JsonObject, json.loads(content.decode("utf-8")))
            fact = observation_fact_codec().decode(parsed)
            expected_data = json.dumps(
                _unfreeze(observation_fact_codec().encode(fact)),
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            if actual_digest != sha256(expected_data).hexdigest():
                raise FactUnavailable(
                    f"Corrupt observation fact: digest mismatch for {operation_id}"
                )
            return fact
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as error:
            raise FactUnavailable(
                f"Corrupt observation fact for {operation_id}: {error}"
            ) from error

    def update_current_index(self, pointer: CurrentObservationPointer) -> CurrentObservationPointer:
        dest = _safe_path(self.indexes_dir, f"{pointer.document_id}.json")
        encoded = pointer_codec().encode(pointer)
        data = json.dumps(_unfreeze(encoded), sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = sha256(data).hexdigest()
        _canonical_write(dest, self.tmp_dir, data, digest)
        verified = self.read_current_index(pointer.document_id)
        if verified is None or verified != pointer:
            raise FactUnavailable("Independent digest readback failed for index pointer")
        return verified

    def read_current_index(self, document_id: str) -> CurrentObservationPointer | None:
        dest = _safe_path(self.indexes_dir, f"{document_id}.json")
        if not dest.is_file():
            return None
        try:
            content = dest.read_bytes()
            actual_digest = sha256(content).hexdigest()
            parsed = cast(JsonObject, json.loads(content.decode("utf-8")))
            pointer = pointer_codec().decode(parsed)
            expected_data = json.dumps(
                _unfreeze(pointer_codec().encode(pointer)), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if actual_digest != sha256(expected_data).hexdigest():
                raise FactUnavailable(f"Corrupt index: digest mismatch for {document_id}")
            return pointer
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as error:
            raise FactUnavailable(f"Corrupt index for {document_id}: {error}") from error

    def find_orphaned_intents(self, document_id: str | None = None) -> tuple[AppIntentFact, ...]:
        orphans: list[AppIntentFact] = []
        for path in sorted(self.intents_dir.glob("*.json")):
            intent = self.read_intent(path.stem)
            if intent is None:
                continue
            if document_id is not None and intent.target.identity.document_id != document_id:
                continue
            obs_file = self.observations_dir / f"{intent.operation_id}.json"
            if not obs_file.is_file():
                orphans.append(intent)
        return tuple(orphans)

    def inspect_target_recovery(self, document_id: str) -> TargetRecovery:
        pointer = self.read_current_index(document_id)
        orphans = self.find_orphaned_intents(document_id)
        latest_obs = None
        if pointer is not None:
            latest_obs = self.read_observation(pointer.operation_id)
        if pointer is None:
            # Check if any observation exists for this document
            any_obs = False
            for path in self.observations_dir.glob("*.json"):
                obs = self.read_observation(path.stem)
                if obs and obs.target.identity.document_id == document_id:
                    any_obs = True
                    latest_obs = obs
                    break
            if any_obs:
                return TargetRecovery(document_id, "index_stale", None, orphans, latest_obs, True)
            if orphans:
                return TargetRecovery(document_id, "orphan_intent", None, orphans, None, True)
            return TargetRecovery(document_id, "missing", None, (), None, False)
        if orphans:
            return TargetRecovery(document_id, "orphan_intent", pointer, orphans, latest_obs, True)
        if pointer.outcome in ("ambiguous", "partial", "failed"):
            return TargetRecovery(document_id, pointer.outcome, pointer, (), latest_obs, True)
        return TargetRecovery(document_id, "clean", pointer, (), latest_obs, False)
