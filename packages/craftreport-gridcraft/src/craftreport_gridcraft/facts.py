"""Immutable app external-effect facts, fsync durability, digest readback and recovery."""

import json
import os
import re
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
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

    def _read_item(self, directory: Path, ident: str, codec: Any, label: str) -> Any:
        dest = _safe_path(directory, f"{ident}.json")
        if not dest.is_file():
            return None
        try:
            content = dest.read_bytes()
            decoded = codec.decode(cast(JsonObject, json.loads(content.decode("utf-8"))))
            expected = json.dumps(
                _unfreeze(codec.encode(decoded)), sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if sha256(content).hexdigest() != sha256(expected).hexdigest():
                raise FactUnavailable(f"Corrupt {label} fact: digest mismatch for {ident}")
            return decoded
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as error:
            raise FactUnavailable(f"Corrupt {label} fact for {ident}: {error}") from error

    def _write_item(
        self, directory: Path, ident: str, item: Any, codec: Any, label: str, immutable: bool = True
    ) -> Any:
        dest = _safe_path(directory, f"{ident}.json")
        data = json.dumps(
            _unfreeze(codec.encode(item)), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if immutable and dest.is_file():
            existing = self._read_item(directory, ident, codec, label)
            if existing == item:
                return existing
            raise ValueError(f"Immutable {label} cannot be altered")
        _canonical_write(dest, self.tmp_dir, data, sha256(data).hexdigest())
        verified = self._read_item(directory, ident, codec, label)
        if verified != item:
            raise FactUnavailable(f"Independent digest readback failed for {label}")
        return verified

    def record_intent(self, intent: AppIntentFact) -> AppIntentFact:
        return cast(
            AppIntentFact,
            self._write_item(
                self.intents_dir, intent.operation_id, intent, intent_codec(), "intent"
            ),
        )

    def read_intent(self, operation_id: str) -> AppIntentFact | None:
        return cast(
            AppIntentFact | None,
            self._read_item(self.intents_dir, operation_id, intent_codec(), "intent"),
        )

    def record_observation(self, fact: AppObservationFact) -> AppObservationFact:
        return cast(
            AppObservationFact,
            self._write_item(
                self.observations_dir,
                fact.operation_id,
                fact,
                observation_fact_codec(),
                "observation",
            ),
        )

    def read_observation(self, operation_id: str) -> AppObservationFact | None:
        return cast(
            AppObservationFact | None,
            self._read_item(
                self.observations_dir, operation_id, observation_fact_codec(), "observation"
            ),
        )

    def update_current_index(self, pointer: CurrentObservationPointer) -> CurrentObservationPointer:
        return cast(
            CurrentObservationPointer,
            self._write_item(
                self.indexes_dir, pointer.document_id, pointer, pointer_codec(), "index", False
            ),
        )

    def read_current_index(self, document_id: str) -> CurrentObservationPointer | None:
        return cast(
            CurrentObservationPointer | None,
            self._read_item(self.indexes_dir, document_id, pointer_codec(), "index"),
        )

    def find_orphaned_intents(self, document_id: str | None = None) -> tuple[AppIntentFact, ...]:
        orphans: list[AppIntentFact] = []
        for path in sorted(self.intents_dir.glob("*.json")):
            intent = self.read_intent(path.stem)
            if intent and (
                document_id is None or intent.target.identity.document_id == document_id
            ):
                if not (self.observations_dir / f"{intent.operation_id}.json").is_file():
                    orphans.append(intent)
        return tuple(orphans)

    def inspect_target_recovery(self, document_id: str) -> TargetRecovery:
        pointer = self.read_current_index(document_id)
        orphans = self.find_orphaned_intents(document_id)
        latest_obs = self.read_observation(pointer.operation_id) if pointer else None
        if pointer is None:
            for path in self.observations_dir.glob("*.json"):
                obs = self.read_observation(path.stem)
                if obs and obs.target.identity.document_id == document_id:
                    return TargetRecovery(document_id, "index_stale", None, orphans, obs, True)
            if orphans:
                return TargetRecovery(document_id, "orphan_intent", None, orphans, None, True)
            return TargetRecovery(document_id, "missing", None, (), None, False)
        if orphans:
            return TargetRecovery(document_id, "orphan_intent", pointer, orphans, latest_obs, True)
        if pointer.outcome in ("ambiguous", "partial", "failed"):
            return TargetRecovery(document_id, pointer.outcome, pointer, (), latest_obs, True)
        return TargetRecovery(document_id, "clean", pointer, (), latest_obs, False)
