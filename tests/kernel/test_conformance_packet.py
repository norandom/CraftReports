"""The finalizer must derive status from complete observations, never caller labels."""

import json
from hashlib import sha256
from pathlib import Path

import pytest
from conformance_packet import (
    SCOPE,
    SUITE,
    CaseResult,
    CleanupResult,
    Packet,
    PacketIdentity,
    case_registry,
    helper_identity,
    load_record,
    required_owners,
    verdict,
)

from craftreport.contracts.capabilities import VerificationState


def complete_packet() -> Packet:
    return Packet(
        run_id="packet-test",
        build_digest="build-a",
        scope=SCOPE,
        identity=PacketIdentity(
            package="fixture",
            package_version="1",
            implementation_digest="source-a",
            core_contract_version="1",
            fixture_suite=SUITE,
            dependencies={"dep": "1"},
        ),
        cases=[
            CaseResult(
                case=case,
                phase=phase,
                outcome="passed",
                run_id="packet-test",
                build_digest="build-a",
                duration_seconds=0.1,
            )
            for case in case_registry()
            for phase in ("setup", "call", "teardown")
        ],
        cleanups=[
            CleanupResult(
                owner=owner,
                status="failed" if owner in {"startup-failure", "cleanup-failure"} else "passed",
                exit_code=1 if owner in {"startup-failure", "cleanup-failure"} else 0,
                forced_termination=False,
                providers_closed=True,
                pipes_closed=True,
            )
            for owner in required_owners()
        ],
        artifacts={},
        exit_code=0,
        excluded_claims=["browser", "durability", "XLSX"],
    )


def test_complete_actual_observation_set_becomes_scoped_record(tmp_path: Path) -> None:
    packet = complete_packet()
    path = persist_packet(tmp_path, packet)
    digest = sha256(path.read_bytes()).hexdigest()
    record = load_record(path, digest, packet.run_id, packet.identity.contract(), "core-a")
    assert record is not None and record.state is VerificationState.PASSED
    assert record.scope == SCOPE and record.evidence[0].content_digest == digest


def persist_packet(directory: Path, packet: Packet) -> Path:
    artifacts: dict[str, object] = {
        "inventory.json": {
            "unit_fixture": "explicit simulated observations",
            "environment": {"kernel_implementation_digest": "core-a"},
        },
        "cleanup.json": {
            item.owner: {
                **item.model_dump(),
                "providers": {"providers_closed": item.providers_closed},
            }
            for item in packet.cleanups
        },
        "source.json": {"unit_fixture": True, "fixture_helpers": helper_identity()},
        "required-cases.json": case_registry(),
        "coverage.json": {},
    }
    for name, value in artifacts.items():
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    packet.build_digest = sha256((directory / "inventory.json").read_bytes()).hexdigest()
    for case in packet.cases:
        case.build_digest = packet.build_digest
    (directory / "cases.json").write_text(json.dumps([case.model_dump() for case in packet.cases]))
    packet.artifacts.update(
        {
            name: sha256((directory / name).read_bytes()).hexdigest()
            for name in (*artifacts, "cases.json")
        }
    )
    path = directory / "packet.json"
    path.write_bytes(packet.model_dump_json().encode())
    return path


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "wrong-run",
        "wrong-build",
        "failed",
        "cleanup",
        "teardown",
        "missing-cleanup",
        "forced-cleanup",
    ],
)
def test_incomplete_or_failed_observations_cannot_pass(defect: str) -> None:
    packet = complete_packet()
    if defect == "missing":
        packet.cases.pop()
    elif defect == "duplicate":
        packet.cases.append(packet.cases[0])
    elif defect == "wrong-run":
        packet.cases[0].run_id = "foreign"
    elif defect == "wrong-build":
        packet.cases[0].build_digest = "foreign"
    elif defect == "cleanup":
        packet.cleanups[0].status = "failed"
    elif defect == "missing-cleanup":
        packet.cleanups.pop()
    elif defect == "forced-cleanup":
        packet.cleanups[0].forced_termination = True
    elif defect == "teardown":
        packet.cases[2].outcome = "failed"
    else:
        packet.cases[0].outcome = "failed"
    assert verdict(packet) is VerificationState.FAILED


@pytest.mark.parametrize(
    "defect",
    ["bytes", "digest", "run", "identity", "artifact", "stale-core", "cleanup-record", "profile"],
)
def test_packet_integrity_is_checked_before_record_creation(tmp_path: Path, defect: str) -> None:
    packet = complete_packet()
    artifact = tmp_path / "case.json"
    artifact.write_bytes(b"observed")
    packet.artifacts = {"case.json": sha256(artifact.read_bytes()).hexdigest()}
    path = persist_packet(tmp_path, packet)
    digest = sha256(path.read_bytes()).hexdigest()
    run = packet.run_id
    expected = packet.identity.contract()
    core_digest = "core-a"
    profile = packet.fixture_profile
    if defect == "bytes":
        path.write_bytes(path.read_bytes() + b" ")
    elif defect == "digest":
        digest = "wrong"
    elif defect == "run":
        run = "other"
    elif defect == "artifact":
        artifact.write_bytes(b"changed")
    elif defect == "stale-core":
        core_digest = "core-b"
    elif defect == "profile":
        profile = "synthetic-disconnected-v1"
    elif defect == "cleanup-record":
        cleanup_path = tmp_path / "cleanup.json"
        raw = json.loads(cleanup_path.read_bytes())
        raw[packet.cleanups[0].owner]["status"] = "failed"
        cleanup_path.write_text(json.dumps(raw))
        packet.artifacts["cleanup.json"] = sha256(cleanup_path.read_bytes()).hexdigest()
        path.write_bytes(packet.model_dump_json().encode())
        digest = sha256(path.read_bytes()).hexdigest()
    else:
        changed = packet.identity.model_copy(update={"implementation_digest": "new"})
        expected = changed.contract()
    assert load_record(path, digest, run, expected, core_digest, profile) is None


@pytest.mark.parametrize("helper", ["fixtures/kernel_services.py", "kernel/fixture_target.py"])
def test_changed_executed_helpers_make_original_packet_pending(tmp_path: Path, helper: str) -> None:
    packet = complete_packet()
    path = persist_packet(tmp_path, packet)
    original_packet = path.read_bytes()
    digest = sha256(original_packet).hexdigest()
    copied = tmp_path / "isolated-tests"
    source = Path(__file__).resolve().parents[1]
    for name in helper_identity():
        target = copied / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / name).read_bytes())

    def consume() -> object:
        return load_record(
            path,
            digest,
            packet.run_id,
            packet.identity.contract(),
            "core-a",
            expected_helpers=helper_identity(copied),
        )

    assert consume() is not None
    changed = copied / helper
    original_helper = changed.read_bytes()
    changed.write_bytes(original_helper + b"\n# changed provider implementation\n")
    assert consume() is None
    changed.write_bytes(original_helper)
    assert consume() is not None
    assert path.read_bytes() == original_packet
