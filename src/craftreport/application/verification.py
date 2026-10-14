"""Resolve operator-owned conformance metadata without claiming content proof."""

from dataclasses import dataclass
from typing import Self

from craftreport.contracts import (
    CapabilityManifest,
    CapabilityVersion,
    CapabilityView,
    VerificationRecord,
)
from craftreport.contracts.values import require_text, require_unique


@dataclass(frozen=True, slots=True)
class VerificationIdentity:
    """Exact evidence key shared by discovery and conformance record writers.

    Versions are recorded identities, not compatibility ranges. Dependency order
    is immaterial; duplicate identities are invalid even with identical versions.
    """

    package: str
    package_version: str
    implementation_digest: str
    core_contract_version: str
    fixture_suite: str
    dependency_versions: tuple[CapabilityVersion, ...]

    def __post_init__(self) -> None:
        for value in (
            self.package,
            self.package_version,
            self.implementation_digest,
            self.core_contract_version,
            self.fixture_suite,
        ):
            require_text(value, "verification identity")
        pins = tuple(self.dependency_versions)
        require_unique(tuple(pin.identity for pin in pins), "verification dependencies")
        object.__setattr__(
            self, "dependency_versions", tuple(sorted(pins, key=lambda p: p.identity))
        )

    @classmethod
    def from_record(cls, record: VerificationRecord) -> Self:
        return cls(
            record.package,
            record.package_version,
            record.implementation_digest,
            record.core_contract_version,
            record.fixture_suite,
            record.dependency_versions,
        )


def resolve_verification(
    manifest: CapabilityManifest,
    record: VerificationRecord | None,
    *,
    core_contract_version: str,
    fixture_suite: str,
    dependency_versions: tuple[CapabilityVersion, ...],
) -> CapabilityView:
    """Use trusted operator expectations and records, never plugin support flags.

    Matching metadata preserves only its recorded scope and evidence references;
    it does not inspect evidence bytes or prove browser behavior or durability.
    Invalid expected identities raise; absent, stale or ambiguous records remain
    pending without exposing an inapplicable passed record.
    """
    expected = VerificationIdentity(
        manifest.package,
        manifest.version,
        manifest.implementation_digest,
        core_contract_version,
        fixture_suite,
        dependency_versions,
    )
    if record is None:
        return CapabilityView(manifest)
    try:
        observed = VerificationIdentity.from_record(record)
    except ValueError:
        return CapabilityView(manifest)
    if observed != expected:
        return CapabilityView(manifest)
    return CapabilityView(manifest, record.state, record)
