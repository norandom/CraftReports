"""Strict app diagnostics and honest candidate-profile identity."""

import json
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from typing import cast

import pytest
from craftreport_gridcraft.app_values import (
    AppSettings,
    ArtifactRef,
    BrowserTarget,
    SavedCandidate,
    TargetObservation,
)
from craftreport_gridcraft.codecs import (
    artifact_codec,
    candidate_codec,
    issue_codec,
    layout_codec,
    observation_codec,
    settings_codec,
    support_descriptor,
    target_codec,
)
from craftreport_gridcraft.values import DECLARATION, PROFILE, AppIssue, OwnedLayout

from craftreport.adapters.canonical import WireFailure
from craftreport.contracts.identity import ExpectedVersion, ResourceRef
from craftreport.contracts.values import JsonObject, require_immutable
from craftreport.policies.values import CheckId, CheckObservation, QualityEvaluation
from craftreport.runtime.values import RunPins


def test_settings_accept_exact_configuration_and_reject_unbounded_inputs() -> None:
    settings = AppSettings(
        "http://localhost:8871",
        "deployment",
        "context",
        "principal",
        "D:/artifacts",
        ("exports",),
        "a" * 64,
        "b" * 64,
        "c" * 64,
        PROFILE.pin,
    )
    require_immutable(settings)
    for changes in (
        {"origin": "https://user:secret@host"},
        {"origin": "https://host/path"},
        {"action_seconds": True},
        {"action_seconds": 61},
        {"operation_seconds": 181},
        {"max_zip_members": 257},
        {"max_compressed_bytes": 4194305},
        {"artifact_root": "relative"},
        {"destination_ids": ("x", "x")},
        {"archive_digest": "bad"},
    ):
        with pytest.raises(ValueError):
            replace(settings, **changes)


def test_app_boundaries_preserve_exact_run_and_reject_nested_coercion(
    browser_target: BrowserTarget, run: RunPins, quality: QualityEvaluation
) -> None:
    evidence = quality.findings[0].evidence
    source = quality.findings[0]
    scope = replace(
        source.scope,
        target=ExpectedVersion(
            ResourceRef("app_document", browser_target.identity.document_id), "1"
        ),
    )
    findings = (
        CheckObservation(
            CheckId.TARGET_CONSISTENCY,
            scope,
            source.status,
            source.evidence,
            source.origin,
            source.reason_code,
        ),
    )
    observation = TargetObservation(
        browser_target, run, 1, "a" * 64, "b" * 64, "c" * 64, findings, evidence
    )
    candidate = SavedCandidate(browser_target, run, "export", "d" * 64, 1024, evidence[0])
    artifact = ArtifactRef("artifact-1", "export-1", candidate, evidence)
    assert target_codec().decode(target_codec().encode(browser_target)) == browser_target
    assert layout_codec().decode(
        layout_codec().encode(OwnedLayout(browser_target, run))
    ) == OwnedLayout(browser_target, run)
    assert observation_codec().decode(observation_codec().encode(observation)) == observation
    assert candidate_codec().decode(candidate_codec().encode(candidate)) == candidate
    assert artifact_codec().decode(artifact_codec().encode(artifact)) == artifact
    wire = candidate_codec().encode(candidate)
    for change in ({"size": True}, {"size": "1024"}, {"purpose": "passed"}, {"unexpected": 1}):
        with pytest.raises(WireFailure):
            candidate_codec().decode(cast(JsonObject, {**wire, **change}))
    changed_run = replace(run, target=replace(run.target, document_id="other"))
    with pytest.raises(ValueError):
        replace(candidate, run=changed_run)
    with pytest.raises(ValueError):
        replace(observation, run=changed_run)
    with pytest.raises(ValueError):
        replace(artifact, candidate=replace(candidate, purpose="inspection"))
    with pytest.raises(ValueError):
        replace(observation, evidence=())
    with pytest.raises(ValueError):
        replace(
            observation,
            findings=(
                replace(
                    findings[0],
                    scope=replace(
                        scope, target=ExpectedVersion(ResourceRef("app_document", "other"), "1")
                    ),
                ),
            ),
        )


def test_settings_codec_and_installed_support_are_closed() -> None:
    settings = AppSettings(
        "http://localhost:8871",
        "deployment",
        "context",
        "principal",
        "D:/artifacts",
        ("exports",),
        "a" * 64,
        "b" * 64,
        "c" * 64,
        PROFILE.pin,
    )
    codec = settings_codec()
    wire = codec.encode(settings)
    assert codec.decode(wire) == settings
    for change in (
        {"browser_executable": "evil"},
        {"owns_context": 1},
        {
            "profile_pin": {
                "identity": "x",
                "version": "1",
                "content_digest": "a" * 64,
                "extra": True,
            }
        },
    ):
        with pytest.raises(WireFailure):
            codec.decode(cast(JsonObject, {**wire, **change}))
    descriptor = support_descriptor()
    assert descriptor["operation_status"] == "untested"
    assert descriptor["headed_status"] == "MANUAL_VERIFY_REQUIRED"
    assert len(cast(tuple[object, ...], descriptor["properties"])) == 24
    require_immutable(descriptor)


def test_profile_is_pinned_and_unavailable_without_real_effect_evidence() -> None:
    assert PROFILE.pin.content_digest == sha256(DECLARATION.encode()).hexdigest()
    assert PROFILE.operation_status == "untested"
    assert json.loads(DECLARATION)["category_serialized_utf8_bytes"] == 16
    assert json.loads(DECLARATION)["literal_serialized_utf8_bytes"] == 32
    assert json.loads(DECLARATION)["excluded_unicode_categories"] == ["Cc", "Cf", "Cs", "Zl", "Zp"]
    require_immutable(PROFILE)
    with pytest.raises(FrozenInstanceError):
        setattr(PROFILE, "operation_status", "supported")


def test_issue_wire_rejects_extras_coercion_unknown_codes_and_mutability() -> None:
    codec = issue_codec()
    issue = AppIssue("limit", ("tables", 0, "rows", 1, 2))
    wire = codec.encode(issue)
    assert codec.decode(wire) == issue
    assert codec.schema()["additionalProperties"] is False
    for changed in (
        {**wire, "passed": True},
        {**wire, "code": "passed"},
        {**wire, "location": (True,)},
        {**wire, "stage": 1},
    ):
        with pytest.raises(WireFailure):
            codec.decode(cast(JsonObject, changed))
