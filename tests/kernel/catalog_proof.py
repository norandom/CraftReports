"""Second phase: fresh installed hosts consume a completed first-phase packet."""

import asyncio
import json
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

from conformance_packet import Packet, helper_identity
from fixture_packaging import ROOT, InstalledFixture
from installed_clients import discover, mcp_client, rest_client
from installed_process import InstalledProcess, write_json


async def mcp_catalog(owner: InstalledProcess, principal: str) -> dict[str, Any]:
    async with mcp_client(owner, principal) as client:
        result = await client.call_tool("craftreport.catalog.v1", {})
        assert result.structured_content is not None and not result.is_error
        return result.structured_content


def compare_catalogs(rest: dict[str, Any], mcp: dict[str, Any]) -> None:
    shared = dict(rest)
    assert shared.pop("transport_limits") == {"max_raw_bytes": 4194304}
    assert "transport_limits" not in mcp
    assert shared == mcp


def check_catalog(owner: InstalledProcess, expected: str) -> None:
    assert discover(owner).verification == expected
    with rest_client(owner) as client:
        rest = client.get("/v1/catalog").json()
    mcp = asyncio.run(mcp_catalog(owner, "alice"))
    with rest_client(owner, "bob") as client:
        private = client.get("/v1/catalog").json()
    private_mcp = asyncio.run(mcp_catalog(owner, "bob"))
    write_json(
        owner.directory / "catalog-proof.json",
        {
            "expected": expected,
            "rest": rest,
            "mcp": mcp,
            "restricted": private,
            "restricted_mcp": private_mcp,
        },
    )
    compare_catalogs(rest, mcp)
    capability = rest["capabilities"][0]
    if expected == "pending":
        assert capability["record"] is None
    else:
        assert capability["record"]["state"] == expected
        assert "synthetic" in capability["record"]["scope"]
        # A new epoch cannot authorize an old run's receipt; existing policy filters refs.
        assert capability["record"]["evidence"] == []
    compare_catalogs(private, private_mcp)
    assert private["operations"] == [] and private["capabilities"] == []


def variants(directory: Path, proof: Path) -> list[tuple[str, Path, str, str]]:
    original = directory / "kernel-manifest.json"
    packet = Packet.model_validate_json(original.read_bytes())
    cases = [("passed", original, sha256(original.read_bytes()).hexdigest(), "passed")]
    for name, expected in (
        ("failed", "failed"),
        ("stale", "pending"),
        ("wrong-build", "pending"),
        ("tampered", "pending"),
    ):
        changed = packet.model_copy(deep=True)
        if name == "failed":
            changed.cases[0].outcome = "failed"
            changed.exit_code = 1
        elif name == "stale":
            changed.identity.fixture_suite = "superseded-suite"
        elif name == "wrong-build":
            changed.identity.implementation_digest = "different-installed-bytes"
        variant_dir = proof / ("operator-negative-" + name)
        variant_dir.mkdir()
        for artifact in packet.artifacts:
            destination = variant_dir / artifact
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((directory / artifact).read_bytes())
        write_json(variant_dir / "cases.json", [case.model_dump() for case in changed.cases])
        changed.artifacts["cases.json"] = sha256(
            (variant_dir / "cases.json").read_bytes()
        ).hexdigest()
        path = variant_dir / "packet.json"
        path.write_bytes(changed.model_dump_json(indent=2).encode())
        digest = sha256(path.read_bytes()).hexdigest()
        if name == "tampered":
            path.write_bytes(path.read_bytes() + b" ")
        cases.append((name, path, digest, expected))
    cases.append(("missing", directory / "absent-packet.json", "absent", "pending"))
    cases.append(
        ("broken-configuration", original, sha256(original.read_bytes()).hexdigest(), "pending")
    )
    for name, expected in (
        ("stale-provider", "pending"),
        ("stale-target", "pending"),
        ("unchanged-helpers", "passed"),
    ):
        cases.append((name, original, sha256(original.read_bytes()).hexdigest(), expected))
    return cases


def isolated_helpers(proof: Path, name: str) -> Path:
    root = proof / "helper-copies" / name
    for relative in helper_identity():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / "tests" / relative).read_bytes())
    mutations = {
        "stale-provider": (
            "fixtures/kernel_services.py",
            b'{"value": "before"}',
            b'{"value": "changed"}',
        ),
        "stale-target": (
            "kernel/fixture_target.py",
            b"self.effect_count = 0",
            b"self.effect_count = 17",
        ),
    }
    if name in mutations:
        relative, before, after = mutations[name]
        source = root / relative
        original = source.read_bytes()
        assert original.count(before) == 1
        source.write_bytes(original.replace(before, after))
    return root


def main(directory: Path, proof_name: str = "catalog-proof") -> None:
    verification = json.loads((directory / "verification.json").read_bytes())
    assert verification["state"] == "passed", "First-phase conformance did not pass"
    assert Path(proof_name).name == proof_name
    proof = directory / proof_name
    proof.mkdir()
    installed = InstalledFixture(
        directory / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"),
        proof,
        tuple(sorted((directory / "wheels").glob("*.whl"))),
    )
    outcomes: list[dict[str, str]] = []
    try:
        for name, packet, digest, expected in variants(directory, proof):
            helper_root = (
                isolated_helpers(proof, name)
                if name in {"stale-provider", "stale-target", "unchanged-helpers"}
                else ROOT / "tests"
            )
            with InstalledProcess(
                installed,
                name,
                verification_packet=packet,
                verification_digest=digest,
                verification_run=directory.name,
                sensitivity_variant="disconnected" if name == "broken-configuration" else "normal",
                helper_root=helper_root,
            ) as owner:
                check_catalog(owner, expected)
                if name in {"stale-provider", "stale-target", "unchanged-helpers"}:
                    observed = owner.observe()
                    assert observed.value == ("changed" if name == "stale-provider" else "before")
                    assert observed.effect_count == (17 if name == "stale-target" else 0)
            assert owner.cleanup["status"] == "passed"
            outcomes.append({"case": name, "expected": expected, "outcome": "passed"})
    finally:
        write_json(
            proof / "results.json",
            {
                "phase": "catalog after finalized packet",
                "outcomes": outcomes,
                "complete": len(outcomes) == 10,
                "command": [sys.executable, *sys.argv],
            },
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
