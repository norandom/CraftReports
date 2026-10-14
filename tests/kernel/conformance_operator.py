"""Installed test-host operator adapter for already finalized conformance packets."""

from hashlib import sha256
from importlib.metadata import distributions
from pathlib import Path

from conformance_packet import SUITE, PacketIdentity, helper_identity, load_record
from craftreport_kernel_fixture import factory

import craftreport
from craftreport.composition.settings import VerificationExpectation
from craftreport.contracts.capabilities import CORE_CONTRACT_VERSION


def installed_identity() -> PacketIdentity:
    manifest = factory().describe()
    return PacketIdentity(
        package=manifest.package,
        package_version=manifest.version,
        implementation_digest=manifest.implementation_digest,
        core_contract_version=CORE_CONTRACT_VERSION,
        fixture_suite=SUITE,
        dependencies={dist.metadata["Name"]: dist.version for dist in distributions()},
    )


def expectation(
    path: Path | None, digest: str, run_id: str, fixture_profile: str
) -> VerificationExpectation:
    expected = installed_identity().contract()
    root = Path(craftreport.__file__).parent
    core_digest = sha256()
    for source in sorted(root.rglob("*.py")):
        core_digest.update(source.relative_to(root).as_posix().encode())
        core_digest.update(source.read_bytes())
    record = (
        load_record(
            path,
            digest,
            run_id,
            expected,
            core_digest.hexdigest(),
            fixture_profile,
            helper_identity(Path(__file__).resolve().parents[1]),
        )
        if path is not None
        else None
    )
    return VerificationExpectation(expected, record)
