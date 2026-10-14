"""Installed service harness smoke; full behavioral conformance follows separately."""

import json
from pathlib import Path

import pytest
from fixture_packaging import InstalledFixture

pytestmark = pytest.mark.integration


def test_installed_discovery_and_owned_cleanup(installed_runtime: InstalledFixture) -> None:
    from installed_clients import discover
    from installed_process import InstalledProcess

    owner = InstalledProcess(installed_runtime, "smoke")
    with owner:
        observed = discover(owner)
        assert observed.protocol_version
        assert {"synthetic.read.v1", "synthetic.write.v1"} <= set(observed.tools)
        assert observed.operations == ("synthetic.read", "synthetic.write")
        assert observed.verification == "pending"
    assert owner.cleanup["status"] == "passed"
    assert owner.process is not None and owner.process.poll() == 0
    _assert_secrets_absent(installed_runtime.directory, owner.secrets)


def test_forced_startup_preserves_failure_and_cleanup(installed_runtime: InstalledFixture) -> None:
    from installed_process import InstalledProcess, StartupFailure

    owner = InstalledProcess(installed_runtime, "startup-failure", failure="startup")
    with pytest.raises(StartupFailure):
        with owner:
            pytest.fail("Forced startup unexpectedly became usable")
    assert owner.process is not None and owner.process.poll() is not None
    assert owner.cleanup["status"] == "failed"
    assert owner.cleanup["exit_code"] != 0
    assert owner.cleanup["forced_termination"] is False
    assert "Synthetic initialization failure after acquire" in (
        owner.directory / "server-diagnostics.log"
    ).read_text(encoding="utf-8")


def test_forced_cleanup_cannot_pass(installed_runtime: InstalledFixture) -> None:
    from installed_clients import discover
    from installed_process import CleanupFailure, InstalledProcess

    owner = InstalledProcess(installed_runtime, "cleanup-failure", failure="cleanup")
    with pytest.raises(CleanupFailure):
        with owner:
            assert discover(owner).protocol_version
    assert owner.process is not None and owner.process.poll() is not None
    assert owner.cleanup["status"] == "failed"
    assert owner.cleanup["exit_code"] != 0
    assert owner.cleanup["forced_termination"] is False
    assert "Synthetic cleanup failure after release" in (
        owner.directory / "server-diagnostics.log"
    ).read_text(encoding="utf-8")
    _assert_secrets_absent(installed_runtime.directory, owner.secrets)


def _assert_secrets_absent(directory: Path, secrets: tuple[str, ...]) -> None:
    for pattern in ("*.json", "*.jsonl", "*.log", "*.xml"):
        for path in directory.rglob(pattern):
            if "env" in path.relative_to(directory).parts:
                continue
            content = path.read_text(encoding="utf-8")
            assert all(secret not in content for secret in secrets), path
    inventory = json.loads((directory / "inventory.json").read_text(encoding="utf-8"))
    assert inventory["wheels"] and inventory["lock_sha256"]
