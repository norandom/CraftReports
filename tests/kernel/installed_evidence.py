"""Aggregate actual pytest assertions and owned cleanup into a scoped packet."""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from fixture_packaging import ROOT, InstalledFixture
from installed_process import write_json


def source_identity() -> dict[str, object]:
    from conformance_packet import helper_identity

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    paths = [ROOT / "pyproject.toml", ROOT / "breadth.toml", ROOT / "quality.toml"]
    paths.extend(
        (
            ROOT / "uv.lock",
            ROOT / "tests/kernel/conformance_cases.json",
            ROOT / "tests/kernel/conformance_owners.json",
        )
    )
    paths.extend(
        path for folder in ("src", "scripts", "tests") for path in (ROOT / folder).rglob("*.py")
    )
    return {
        "revision": revision,
        "dirty": bool(status),
        "worktree_status": status.splitlines(),
        "fixture_helpers": helper_identity(),
        "source_sha256": {
            str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths)
        },
    }


@dataclass
class Evidence:
    directory: Path
    cases: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    source: dict[str, object] = field(default_factory=source_identity)

    def capture_build(self, installed: InstalledFixture) -> str:
        """Keep actual per-fixture provenance, comparing content rather than zip timestamps."""
        raw = (installed.directory / "inventory.json").read_bytes()
        digest = sha256(raw).hexdigest()
        primary = json.loads((self.directory / "inventory.json").read_bytes())
        observed = json.loads(raw)
        for key in ("kernel_implementation_digest", "core_contract_version", "capability"):
            assert primary["environment"][key] == observed["environment"][key], key
        assert primary["lock_sha256"] == observed["lock_sha256"]
        builds = self.directory / "builds"
        builds.mkdir(exist_ok=True)
        (builds / (digest + ".json")).write_bytes(raw)
        return digest

    @property
    def build_digest(self) -> str:
        inventory = self.directory / "inventory.json"
        return sha256(inventory.read_bytes()).hexdigest() if inventory.exists() else "unbuilt"

    def finish(self, exit_code: int) -> bool:
        from conformance_packet import (
            SCOPE,
            SUITE,
            CaseResult,
            CleanupResult,
            Packet,
            PacketIdentity,
            case_registry,
            record_for,
            verdict,
        )

        from craftreport.contracts.capabilities import VerificationState

        inventory_path = self.directory / "inventory.json"
        if not inventory_path.exists():
            write_json(self.directory / "finalization-error.json", {"reason": "missing inventory"})
            return False
        inventory = json.loads(inventory_path.read_bytes())
        environment = inventory["environment"]
        capability = environment["capability"]
        cleanups = {
            path.parent.name: json.loads(path.read_bytes())
            for path in self.directory.glob("*/cleanup.json")
        }
        write_json(self.directory / "cases.json", self.cases)
        write_json(self.directory / "cleanup.json", cleanups)
        write_json(self.directory / "source.json", self.source)
        write_json(self.directory / "required-cases.json", case_registry())
        write_json(
            self.directory / "coverage.json",
            {
                requirement: [case for case, refs in case_registry().items() if requirement in refs]
                for requirement in sorted(
                    {ref for refs in case_registry().values() for ref in refs}
                )
            },
        )
        packet = Packet(
            run_id=self.directory.name,
            build_digest=self.build_digest,
            identity=PacketIdentity(
                package=capability["package"],
                package_version=capability["version"],
                implementation_digest=capability["implementation_digest"],
                core_contract_version=environment["core_contract_version"],
                fixture_suite=SUITE,
                dependencies=environment["packages"],
            ),
            scope=SCOPE,
            excluded_claims=[
                "production durability",
                "browser behavior",
                "GridCraft",
                "financial accuracy",
                "XLSX",
            ],
            cases=[CaseResult.model_validate(case) for case in self.cases],
            cleanups=[
                CleanupResult(
                    owner=name,
                    status=value["status"],
                    forced_termination=value["forced_termination"],
                    exit_code=value["exit_code"],
                    pipes_closed=value["pipes_closed"],
                    providers_closed=bool(
                        value.get("providers") and value["providers"]["providers_closed"]
                    ),
                )
                for name, value in cleanups.items()
            ],
            artifacts=artifact_hashes(self.directory),
            exit_code=exit_code if self.source == source_identity() else 1,
            command=[sys.executable, *sys.argv],
        )
        path = self.directory / "kernel-manifest.json"
        path.write_bytes(packet.model_dump_json(indent=2).encode("utf-8"))
        digest = sha256(path.read_bytes()).hexdigest()
        record = record_for(packet, digest)
        write_json(
            self.directory / "verification.json",
            {
                "packet": path.name,
                "digest": digest,
                "run_id": packet.run_id,
                "state": record.state.value,
                "scope": record.scope,
                "evidence_id": record.evidence[0].identity,
            },
        )
        print(f"Conformance packet: {record.state.value}; {path}", flush=True)
        return verdict(packet) is VerificationState.PASSED


def artifact_hashes(directory: Path) -> dict[str, str]:
    paths = [
        *directory.glob("*.json"),
        *directory.glob("*/*.json"),
        *directory.glob("*/*.jsonl"),
        *directory.glob("*/*.log"),
        *directory.glob("*.log"),
        *directory.glob("*.xml"),
    ]
    excluded = {"kernel-manifest.json", "verification.json"}
    return {
        path.relative_to(directory).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
        if path.name not in excluded
    }
