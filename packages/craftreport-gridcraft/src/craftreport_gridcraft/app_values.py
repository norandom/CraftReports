"""Frozen configured browser, observation and app-byte identities; no live handles."""

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from urllib.parse import urlsplit

from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable
from craftreport.policies.values import CheckId, CheckObservation
from craftreport.runtime.values import RunPins, TargetIdentity


def text(value: str) -> None:
    if type(value) is not str or not value.strip() or len(value.encode()) > 65536:
        raise ValueError("Expected bounded nonempty identity")


def digest(value: str) -> None:
    VersionPin("digest", "1", value)


def count(value: int, maximum: int) -> None:
    if type(value) is not int or not 0 < value <= maximum:
        raise ValueError("Expected bounded positive integer")


def origin(value: str) -> None:
    text(value)
    parsed = urlsplit(value)
    if value != f"{parsed.scheme}://{parsed.netloc}":
        raise ValueError("Origin must be exact, without path/query/fragment")
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Expected exact HTTP origin without credentials or path")
    if parsed.port is not None and not 0 < parsed.port <= 65535:
        raise ValueError("Invalid origin port")


@dataclass(frozen=True, slots=True)
class AppSettings:
    origin: str
    deployment_id: str
    context_id: str
    principal_id: str
    artifact_root: str
    destination_ids: tuple[str, ...]
    archive_digest: str
    javascript_digest: str
    wasm_digest: str
    profile_pin: VersionPin
    owns_context: bool = True
    action_seconds: int = 60
    operation_seconds: int = 180
    refresh_seconds: int = 10
    stale_seconds: int = 30
    max_compressed_bytes: int = 4194304
    max_uncompressed_bytes: int = 33554432
    max_zip_members: int = 256

    def __post_init__(self) -> None:
        require_immutable(self)
        origin(self.origin)
        for value in (
            self.deployment_id,
            self.context_id,
            self.principal_id,
            self.artifact_root,
            *self.destination_ids,
        ):
            text(value)
        if not (
            PurePosixPath(self.artifact_root).is_absolute()
            or PureWindowsPath(self.artifact_root).is_absolute()
        ):
            raise ValueError("Configured artifact root must be absolute")
        if (
            type(self.destination_ids) is not tuple
            or not self.destination_ids
            or len(set(self.destination_ids)) != len(self.destination_ids)
        ):
            raise ValueError("Explicit unique destination allowlist required")
        if type(self.owns_context) is not bool or type(self.profile_pin) is not VersionPin:
            raise ValueError("Invalid context ownership/profile")
        for value in (self.archive_digest, self.javascript_digest, self.wasm_digest):
            digest(value)
        for value, maximum in (
            (self.action_seconds, 60),
            (self.operation_seconds, 180),
            (self.refresh_seconds, 2**31 - 1),
            (self.stale_seconds, 2**31 - 1),
            (self.max_compressed_bytes, 4194304),
            (self.max_uncompressed_bytes, 33554432),
            (self.max_zip_members, 256),
        ):
            count(value, maximum)
        if self.action_seconds > self.operation_seconds:
            raise ValueError("Action deadline exceeds operation deadline")


@dataclass(frozen=True, slots=True)
class BrowserTarget:
    identity: TargetIdentity
    deployment_id: str
    context_id: str
    page_id: str
    navigation_generation: int
    origin: str
    archive_digest: str
    javascript_digest: str
    wasm_digest: str
    profile_pin: VersionPin
    document_marker: str

    def __post_init__(self) -> None:
        require_immutable(self)
        if (
            type(self.identity) is not TargetIdentity
            or self.identity.mode != "browser"
            or type(self.profile_pin) is not VersionPin
        ):
            raise ValueError("Exact browser target/profile required")
        for value in (self.deployment_id, self.context_id, self.page_id, self.document_marker):
            text(value)
        origin(self.origin)
        count(self.navigation_generation, 2**63 - 1)
        for value in (self.archive_digest, self.javascript_digest, self.wasm_digest):
            digest(value)


def evidence(values: tuple[EvidenceRef, ...]) -> None:
    if type(values) is not tuple or not values or any(type(v) is not EvidenceRef for v in values):
        raise ValueError("Actual immutable evidence references required")


@dataclass(frozen=True, slots=True)
class TargetObservation:
    target: BrowserTarget
    run: RunPins
    revision: int
    before_fingerprint: str
    after_fingerprint: str
    outside_fingerprint: str
    findings: tuple[CheckObservation, ...]
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        require_immutable(self)
        matched(self.target, self.run)
        count(self.revision, 2**63 - 1)
        for value in (self.before_fingerprint, self.after_fingerprint, self.outside_fingerprint):
            digest(value)
        evidence(self.evidence)
        if not self.findings or any(
            type(f) is not CheckObservation
            or f.check_id not in (CheckId.LAYOUT_FIT, CheckId.TARGET_CONSISTENCY)
            or f.scope.content_digest != self.run.prepared_digest
            or f.scope.validation_scope_digest != self.run.validation_scope
            or f.scope.target is None
            or f.scope.target.resource.kind != "app_document"
            or f.scope.target.resource.identity != self.target.identity.document_id
            or f.scope.artifact_digest is not None
            for f in self.findings
        ):
            raise ValueError("Exact run-scoped observations required")


def matched(target: BrowserTarget, run: RunPins) -> None:
    if (
        type(target) is not BrowserTarget
        or type(run) is not RunPins
        or target.identity != run.target
    ):
        raise ValueError("Target differs from pinned run")


@dataclass(frozen=True, slots=True)
class SavedCandidate:
    target: BrowserTarget
    run: RunPins
    purpose: Literal["inspection", "export"]
    bytes_digest: str
    size: int
    capture_fact: EvidenceRef

    def __post_init__(self) -> None:
        require_immutable(self)
        matched(self.target, self.run)
        digest(self.bytes_digest)
        count(self.size, 4194304)
        if (
            self.purpose not in ("inspection", "export")
            or type(self.capture_fact) is not EvidenceRef
        ):
            raise ValueError("Invalid app capture fact")


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    artifact_id: str
    destination_id: str
    candidate: SavedCandidate
    evidence: tuple[EvidenceRef, ...]

    def __post_init__(self) -> None:
        require_immutable(self)
        for value in (self.artifact_id, self.destination_id):
            text(value)
        if type(self.candidate) is not SavedCandidate or self.candidate.purpose != "export":
            raise ValueError("Only exported candidates can identify published artifacts")
        evidence(self.evidence)
