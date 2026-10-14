"""Operator-side packet validation; no filesystem policy enters production code."""

import json
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from craftreport.application.verification import VerificationIdentity
from craftreport.contracts import CapabilityVersion, EvidenceRef, OperationKey
from craftreport.contracts.capabilities import VerificationRecord, VerificationState

SUITE = "kernel-synthetic-conformance-v1"
SCOPE = (
    "normal synthetic fixture operations and temporary state; "
    "contract and installed REST/MCP checks"
)
PROFILE = "synthetic-normal-v1"


def helper_identity(tests_root: Path | None = None) -> dict[str, str]:
    """Bind the complete two helper import trees, including transitive local modules."""
    root = tests_root or Path(__file__).resolve().parents[1]
    paths = [path for folder in ("fixtures", "kernel") for path in (root / folder).rglob("*.py")]
    paths.extend((root / "kernel").glob("conformance_*.json"))
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case: str
    phase: Literal["setup", "call", "teardown"]
    outcome: Literal["passed", "failed", "skipped"]
    run_id: str
    build_digest: str
    duration_seconds: float
    installed_builds: list[str] = Field(default_factory=list[str])


class PacketIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    package: str
    package_version: str
    implementation_digest: str
    core_contract_version: str
    fixture_suite: str
    dependencies: dict[str, str]

    def contract(self) -> VerificationIdentity:
        return VerificationIdentity(
            self.package,
            self.package_version,
            self.implementation_digest,
            self.core_contract_version,
            self.fixture_suite,
            tuple(CapabilityVersion(key, value) for key, value in self.dependencies.items()),
        )


class CleanupResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    owner: str
    status: str
    forced_termination: bool
    exit_code: int | None
    providers_closed: bool
    pipes_closed: bool


class ProviderCleanup(BaseModel):
    providers_closed: bool


class OwnedCleanup(BaseModel):
    status: str
    forced_termination: bool
    exit_code: int | None
    providers: ProviderCleanup | None
    pipes_closed: bool


def read_cleanups(path: Path) -> list[CleanupResult]:
    from pydantic import TypeAdapter

    raw = TypeAdapter(dict[str, OwnedCleanup]).validate_json(path.read_bytes(), strict=True)
    return [
        CleanupResult(
            owner=name,
            status=value.status,
            forced_termination=value.forced_termination,
            exit_code=value.exit_code,
            providers_closed=bool(value.providers and value.providers.providers_closed),
            pipes_closed=value.pipes_closed,
        )
        for name, value in raw.items()
    ]


class Packet(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    run_id: str
    build_digest: str
    identity: PacketIdentity
    scope: str
    excluded_claims: list[str]
    cases: list[CaseResult]
    cleanups: list[CleanupResult]
    artifacts: dict[str, str]
    exit_code: int
    command: list[str] = Field(default_factory=list[str])
    fixture_profile: str = PROFILE


def case_registry() -> dict[str, list[str]]:
    from pydantic import TypeAdapter

    return TypeAdapter(dict[str, list[str]]).validate_json(
        Path(__file__).with_name("conformance_cases.json").read_bytes(), strict=True
    )


def required_owners() -> list[str]:
    from pydantic import TypeAdapter

    return TypeAdapter(list[str]).validate_json(
        Path(__file__).with_name("conformance_owners.json").read_bytes(), strict=True
    )


def verdict(packet: Packet) -> VerificationState:
    required = case_registry()
    observed: dict[tuple[str, str], CaseResult] = {}
    for result in packet.cases:
        key = (result.case, result.phase)
        if (
            key in observed
            or result.run_id != packet.run_id
            or result.build_digest != packet.build_digest
        ):
            return VerificationState.FAILED
        observed[key] = result
    if any(
        (case, phase) not in observed
        for case in required
        for phase in ("setup", "call", "teardown")
    ):
        return VerificationState.FAILED
    if packet.exit_code or any(result.outcome != "passed" for result in packet.cases):
        return VerificationState.FAILED
    owners = [cleanup.owner for cleanup in packet.cleanups]
    if len(owners) != len(set(owners)) or set(owners) != set(required_owners()):
        return VerificationState.FAILED
    if not all(cleanup_ok(cleanup) for cleanup in packet.cleanups):
        return VerificationState.FAILED
    return VerificationState.PASSED


def cleanup_ok(cleanup: CleanupResult) -> bool:
    expected = cleanup.owner in {"startup-failure", "cleanup-failure"}
    return (
        not cleanup.forced_termination
        and cleanup.providers_closed
        and cleanup.pipes_closed
        and (
            (cleanup.status == "failed" and cleanup.exit_code not in (None, 0))
            if expected
            else (cleanup.status == "passed" and cleanup.exit_code == 0)
        )
    )


def record_for(packet: Packet, digest: str) -> VerificationRecord:
    identity = packet.identity.contract()
    return VerificationRecord(
        identity.package,
        identity.package_version,
        identity.implementation_digest,
        identity.core_contract_version,
        identity.fixture_suite,
        identity.dependency_versions,
        verdict(packet),
        SCOPE,
        (
            EvidenceRef(
                "kernel-conformance-" + packet.run_id,
                SCOPE,
                packet.run_id,
                OperationKey("synthetic.conformance", "1"),
                (),
                digest,
            ),
        ),
    )


def load_record(
    path: Path,
    digest: str,
    run_id: str,
    expected: VerificationIdentity,
    expected_core_digest: str,
    expected_profile: str = PROFILE,
    expected_helpers: dict[str, str] | None = None,
) -> VerificationRecord | None:
    """An absent, corrupt, foreign or stale packet cannot become trusted metadata."""
    try:
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != digest:
            return None
        packet = Packet.model_validate_json(raw)
        if packet.run_id != run_id or packet.identity.contract() != expected:
            return None
        if (
            packet.scope != SCOPE
            or packet.identity.fixture_suite != SUITE
            or packet.fixture_profile != expected_profile
        ):
            return None
        if not artifacts_valid(path, packet):
            return None
        source = json.loads((path.parent / "source.json").read_bytes())
        current_helpers = helper_identity() if expected_helpers is None else expected_helpers
        if not current_helpers or source.get("fixture_helpers") != current_helpers:
            return None
        inventory = json.loads((path.parent / "inventory.json").read_bytes())
        if inventory["environment"]["kernel_implementation_digest"] != expected_core_digest:
            return None
        return record_for(packet, digest)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def artifacts_valid(path: Path, packet: Packet) -> bool:
    required = {
        "inventory.json",
        "cases.json",
        "cleanup.json",
        "source.json",
        "required-cases.json",
        "coverage.json",
    }
    if not required <= packet.artifacts.keys():
        return False
    for name, checksum in packet.artifacts.items():
        artifact = (path.parent / name).resolve()
        if (
            not artifact.is_relative_to(path.parent.resolve())
            or sha256(artifact.read_bytes()).hexdigest() != checksum
        ):
            return False
    if sha256((path.parent / "inventory.json").read_bytes()).hexdigest() != packet.build_digest:
        return False
    if json.loads((path.parent / "cases.json").read_bytes()) != [
        case.model_dump() for case in packet.cases
    ]:
        return False
    if json.loads((path.parent / "required-cases.json").read_bytes()) != case_registry():
        return False
    if {item.owner: item for item in read_cleanups(path.parent / "cleanup.json")} != {
        item.owner: item for item in packet.cleanups
    }:
        return False
    return True
