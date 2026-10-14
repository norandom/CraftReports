"""Synthetic metadata matching only; no production or app conformance claims."""

from dataclasses import FrozenInstanceError, replace

import pytest

from craftreport.application.verification import VerificationIdentity, resolve_verification
from craftreport.contracts import (
    CapabilityManifest,
    CapabilityVersion,
    CapabilityView,
    Catalog,
    EvidenceRef,
    OperationKey,
    VerificationRecord,
    VerificationState,
)

PINS = (CapabilityVersion("fixture.target", "1.2.0"), CapabilityVersion("fixture.store", "2.0"))
MANIFEST = CapabilityManifest(
    "fixture", "fixture-package", "1.0.0", ">=1,<2", (), (), {}, (), "sha256:build-a"
)
RECORD = VerificationRecord(
    MANIFEST.package,
    MANIFEST.version,
    MANIFEST.implementation_digest,
    "1.0.0",
    "kernel-synthetic-v1",
    PINS,
    VerificationState.PASSED,
    "synthetic effects and temporary state only",
    (EvidenceRef("synthetic-case-1", "synthetic", "run-1", OperationKey("fixture.read", "1")),),
)


def resolve(
    record: VerificationRecord | None, manifest: CapabilityManifest = MANIFEST
) -> CapabilityView:
    return resolve_verification(
        manifest,
        record,
        core_contract_version="1.0.0",
        fixture_suite="kernel-synthetic-v1",
        dependency_versions=PINS,
    )


@pytest.mark.parametrize("state", list(VerificationState))
def test_matched_record_retains_exact_outcome_scope_and_evidence(state: VerificationState) -> None:
    record = replace(RECORD, state=state)
    view = resolve(record)
    assert view.verification is state
    assert view.record is record
    assert view.record is not None
    assert view.record.scope == "synthetic effects and temporary state only"
    assert view.record.evidence is record.evidence
    assert view.manifest is MANIFEST


@pytest.mark.parametrize(
    "record",
    [
        None,
        replace(RECORD, package="another-package"),
        replace(RECORD, package_version="1.0.1"),
        replace(RECORD, package_version="1.0"),
        replace(RECORD, implementation_digest="sha256:build-b"),
        replace(RECORD, core_contract_version="1.1.0"),
        replace(RECORD, fixture_suite="another-suite"),
        replace(RECORD, dependency_versions=()),
        replace(RECORD, dependency_versions=PINS[:1]),
        replace(RECORD, dependency_versions=(*PINS, CapabilityVersion("extra", "1"))),
        replace(RECORD, dependency_versions=(CapabilityVersion("wrong", "1.2.0"), PINS[1])),
        replace(
            RECORD, dependency_versions=(CapabilityVersion(PINS[0].identity, "1.3.0"), PINS[1])
        ),
        replace(RECORD, dependency_versions=(*PINS, PINS[0])),
        replace(RECORD, dependency_versions=(*PINS, CapabilityVersion(PINS[0].identity, "9"))),
        replace(RECORD, state=VerificationState.FAILED, implementation_digest="old-build"),
    ],
)
def test_missing_stale_or_ambiguous_record_is_pending(record: VerificationRecord | None) -> None:
    view = resolve(record)
    assert view.verification is VerificationState.PENDING
    assert view.record is None


def test_dependency_order_is_not_identity() -> None:
    record = replace(RECORD, dependency_versions=tuple(reversed(PINS)))
    assert resolve(record).verification is VerificationState.PASSED
    assert VerificationIdentity.from_record(record) == VerificationIdentity.from_record(RECORD)


@pytest.mark.parametrize(
    ("core", "suite", "pins"),
    [
        ("2.0.0", RECORD.fixture_suite, PINS),
        ("1.0.0", "new-suite", PINS),
        ("1.0.0", RECORD.fixture_suite, ()),
    ],
)
def test_operator_expectations_are_independent_of_record(
    core: str, suite: str, pins: tuple[CapabilityVersion, ...]
) -> None:
    view = resolve_verification(
        MANIFEST, RECORD, core_contract_version=core, fixture_suite=suite, dependency_versions=pins
    )
    assert view.verification is VerificationState.PENDING
    assert view.record is None


@pytest.mark.parametrize("duplicate", [PINS[0], CapabilityVersion(PINS[0].identity, "9")])
def test_ambiguous_operator_expectations_are_rejected(duplicate: CapabilityVersion) -> None:
    with pytest.raises(ValueError, match="dependencies must be unique"):
        resolve_verification(
            MANIFEST,
            RECORD,
            core_contract_version="1.0.0",
            fixture_suite=RECORD.fixture_suite,
            dependency_versions=(*PINS, duplicate),
        )


def test_catalog_support_declarations_and_new_build_cannot_upgrade_status() -> None:
    manifest = replace(MANIFEST, settings_schema={"supported": True})
    catalog = Catalog(
        (),
        (resolve(None, manifest), resolve(RECORD, replace(manifest, implementation_digest="new"))),
        "deployment-1",
        "temporary",
    )
    assert all(view.verification is VerificationState.PENDING for view in catalog.capabilities)
    assert all(view.record is None for view in catalog.capabilities)
    with pytest.raises(FrozenInstanceError):
        setattr(catalog.capabilities[0], "verification", VerificationState.PASSED)


def test_identity_is_frozen_and_shared_with_record_writer() -> None:
    identity = VerificationIdentity(
        MANIFEST.package,
        MANIFEST.version,
        MANIFEST.implementation_digest,
        "1.0.0",
        "kernel-synthetic-v1",
        tuple(reversed(PINS)),
    )
    assert identity == VerificationIdentity.from_record(RECORD)
    assert hash(identity) == hash(VerificationIdentity.from_record(RECORD))
    with pytest.raises(FrozenInstanceError):
        setattr(identity, "fixture_suite", "other")
