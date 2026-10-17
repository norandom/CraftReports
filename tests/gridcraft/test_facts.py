"""Immutable external-effect facts, fsync durability, digest readback and recovery."""

from dataclasses import replace
from pathlib import Path

import pytest
from craftreport_gridcraft.codecs import (
    intent_codec,
    observation_fact_codec,
    pointer_codec,
)
from craftreport_gridcraft.facts import AppFacts, FactUnavailable
from craftreport_gridcraft.values import (
    AppIntentFact,
    AppObservationFact,
    BrowserTarget,
    CurrentObservationPointer,
    TargetObservation,
)

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.contracts.values import require_immutable
from craftreport.policies.values import CheckId, CheckObservation, QualityEvaluation
from craftreport.runtime.values import RunPins


@pytest.fixture
def target_observation(
    browser_target: BrowserTarget, run: RunPins, quality: QualityEvaluation
) -> TargetObservation:
    source = quality.findings[0]
    scope = replace(
        source.scope,
        target=ExpectedVersion(
            ResourceRef("app_document", browser_target.identity.document_id), "1"
        ),
    )
    finding = CheckObservation(
        CheckId.TARGET_CONSISTENCY,
        scope,
        source.status,
        source.evidence,
        source.origin,
        source.reason_code,
    )
    return TargetObservation(
        browser_target,
        run,
        1,
        "a" * 64,
        "b" * 64,
        "c" * 64,
        (finding,),
        source.evidence,
    )


@pytest.fixture
def evidence_ref() -> EvidenceRef:
    return EvidenceRef(
        identity="ev-1",
        scope="browser_observation",
        operation_id="op-123",
        operation=OperationKey("gridcraft.apply", "1"),
        resource_versions=(),
        content_digest="e" * 64,
    )


def test_intent_fact_codecs_and_immutability(browser_target: BrowserTarget, run: RunPins) -> None:
    intent = AppIntentFact(
        operation_id="op-1",
        subject="operator-1",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        purpose="apply",
        created_at="2026-10-17T12:00:00Z",
    )
    require_immutable(intent)
    encoded = intent_codec().encode(intent)
    decoded = intent_codec().decode(encoded)
    assert decoded == intent
    assert intent.content_digest


def test_observation_fact_codecs_and_immutability(
    browser_target: BrowserTarget,
    run: RunPins,
    target_observation: TargetObservation,
    evidence_ref: EvidenceRef,
) -> None:
    fact = AppObservationFact(
        operation_id="op-1",
        subject="operator-1",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        observation=target_observation,
        candidate=None,
        evidence=(evidence_ref,),
        reason_code=None,
        created_at="2026-10-17T12:00:05Z",
    )
    require_immutable(fact)
    encoded = observation_fact_codec().encode(fact)
    decoded = observation_fact_codec().decode(encoded)
    assert decoded == fact
    assert fact.content_digest


def test_current_observation_pointer_codecs_and_immutability(
    browser_target: BrowserTarget, run: RunPins
) -> None:
    pointer = CurrentObservationPointer(
        document_id=browser_target.identity.document_id,
        operation_id="op-1",
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        fact_digest="f" * 64,
        updated_at="2026-10-17T12:00:10Z",
    )
    require_immutable(pointer)
    encoded = pointer_codec().encode(pointer)
    decoded = pointer_codec().decode(encoded)
    assert decoded == pointer
    assert pointer.content_digest


def test_app_facts_intent_lifecycle_and_idempotency(
    tmp_path: Path, browser_target: BrowserTarget, run: RunPins
) -> None:
    store = AppFacts(tmp_path / "facts")
    intent = AppIntentFact(
        operation_id="op-100",
        subject="operator-1",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        purpose="apply",
        created_at="2026-10-17T12:00:00Z",
    )

    # Missing before write
    assert store.read_intent("op-100") is None

    # Write and readback
    recorded = store.record_intent(intent)
    assert recorded == intent

    # Reopen in fresh store instance
    reopened_store = AppFacts(tmp_path / "facts")
    read = reopened_store.read_intent("op-100")
    assert read == intent

    # Idempotent re-record of identical intent
    same = store.record_intent(intent)
    assert same == intent

    # Conflicting re-record of different intent with same operation_id rejects
    different = replace(intent, revision=2)
    with pytest.raises(ValueError, match="Immutable intent cannot be altered"):
        store.record_intent(different)


def test_app_facts_observation_lifecycle_and_corruption_handling(
    tmp_path: Path,
    browser_target: BrowserTarget,
    run: RunPins,
    target_observation: TargetObservation,
    evidence_ref: EvidenceRef,
) -> None:
    store = AppFacts(tmp_path / "facts")
    fact = AppObservationFact(
        operation_id="op-200",
        subject="operator-1",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        observation=target_observation,
        candidate=None,
        evidence=(evidence_ref,),
        reason_code=None,
        created_at="2026-10-17T12:00:05Z",
    )

    # Missing returns None
    assert store.read_observation("op-200") is None

    # Record and readback
    recorded = store.record_observation(fact)
    assert recorded == fact

    # Reopen
    reopened = AppFacts(tmp_path / "facts")
    assert reopened.read_observation("op-200") == fact

    # Corrupt fact file fails with FactUnavailable (not missing)
    fact_file = tmp_path / "facts/observations/op-200.json"
    assert fact_file.is_file()
    fact_file.write_text('{"corrupted": true}', encoding="utf-8")
    with pytest.raises(FactUnavailable, match="Corrupt observation fact"):
        reopened.read_observation("op-200")


def test_app_facts_index_lifecycle_and_corruption_handling(
    tmp_path: Path, browser_target: BrowserTarget, run: RunPins
) -> None:
    store = AppFacts(tmp_path / "facts")
    doc_id = browser_target.identity.document_id
    pointer = CurrentObservationPointer(
        document_id=doc_id,
        operation_id="op-300",
        target=browser_target,
        run=run,
        revision=1,
        outcome="complete",
        fact_digest="a" * 64,
        updated_at="2026-10-17T12:00:00Z",
    )

    assert store.read_current_index(doc_id) is None

    # Record pointer
    recorded = store.update_current_index(pointer)
    assert recorded == pointer
    assert store.read_current_index(doc_id) == pointer

    # Update index to new revision
    updated = replace(pointer, revision=2, fact_digest="b" * 64, updated_at="2026-10-17T12:00:10Z")
    store.update_current_index(updated)
    assert store.read_current_index(doc_id) == updated

    # Corrupt index file fails with FactUnavailable
    index_file = tmp_path / f"facts/indexes/{doc_id}.json"
    index_file.write_text("not json!", encoding="utf-8")
    with pytest.raises(FactUnavailable, match="Corrupt index"):
        store.read_current_index(doc_id)


def test_path_containment_and_invalid_identifiers_rejected(
    tmp_path: Path, browser_target: BrowserTarget, run: RunPins
) -> None:
    store = AppFacts(tmp_path / "facts")
    for bad_id in ("../escape", "sub/dir", "", " ", "bad/name", "a" * 65, "with\\slash"):
        with pytest.raises(ValueError):
            store.read_intent(bad_id)
        with pytest.raises(ValueError):
            store.read_observation(bad_id)
        with pytest.raises(ValueError):
            store.read_current_index(bad_id)


def test_crash_cutpoints_and_recovery_inspection(
    tmp_path: Path,
    browser_target: BrowserTarget,
    run: RunPins,
    target_observation: TargetObservation,
    evidence_ref: EvidenceRef,
) -> None:
    store = AppFacts(tmp_path / "facts")
    doc_id = browser_target.identity.document_id

    # Cutpoint 0: completely missing / fresh target
    rec = store.inspect_target_recovery(doc_id)
    assert rec.status == "missing"
    assert not rec.recovery_required
    assert rec.current_pointer is None

    # Cutpoint 1: Intent recorded, crash before observation (orphan intent)
    intent = AppIntentFact(
        operation_id="op-cut-1",
        subject="op",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        purpose="apply",
        created_at="2026-10-17T12:00:00Z",
    )
    store.record_intent(intent)
    assert store.find_orphaned_intents(doc_id) == (intent,)

    rec1 = store.inspect_target_recovery(doc_id)
    assert rec1.status == "orphan_intent"
    assert rec1.recovery_required
    assert rec1.orphaned_intents == (intent,)

    # Cutpoint 2: Observation recorded as partial/ambiguous
    obs_ambig = AppObservationFact(
        operation_id="op-cut-1",
        subject="op",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=1,
        outcome="ambiguous",
        observation=None,
        candidate=None,
        evidence=(evidence_ref,),
        reason_code="TIMEOUT_AFTER_DISPATCH",
        created_at="2026-10-17T12:00:05Z",
    )
    store.record_observation(obs_ambig)
    # No longer an orphan intent since observation exists
    assert store.find_orphaned_intents(doc_id) == ()

    # Index still missing while observation exists -> index_stale / recovery required
    rec2 = store.inspect_target_recovery(doc_id)
    assert rec2.status == "index_stale"
    assert rec2.recovery_required

    # Update index to reflect ambiguous outcome
    pointer_ambig = CurrentObservationPointer(
        document_id=doc_id,
        operation_id="op-cut-1",
        target=browser_target,
        run=run,
        revision=1,
        outcome="ambiguous",
        fact_digest=obs_ambig.content_digest,
        updated_at="2026-10-17T12:00:06Z",
    )
    store.update_current_index(pointer_ambig)
    rec3 = store.inspect_target_recovery(doc_id)
    assert rec3.status == "ambiguous"
    assert rec3.recovery_required

    # Cutpoint 3: Complete operation recorded and index updated -> clean verified state
    obs_complete = AppObservationFact(
        operation_id="op-cut-2",
        subject="op",
        deployment_id=browser_target.deployment_id,
        target=browser_target,
        run=run,
        revision=2,
        outcome="complete",
        observation=target_observation,
        candidate=None,
        evidence=(evidence_ref,),
        reason_code=None,
        created_at="2026-10-17T12:01:05Z",
    )
    intent_complete = replace(intent, operation_id="op-cut-2", revision=2)
    store.record_intent(intent_complete)
    store.record_observation(obs_complete)
    pointer_complete = CurrentObservationPointer(
        document_id=doc_id,
        operation_id="op-cut-2",
        target=browser_target,
        run=run,
        revision=2,
        outcome="complete",
        fact_digest=obs_complete.content_digest,
        updated_at="2026-10-17T12:01:06Z",
    )
    store.update_current_index(pointer_complete)

    rec4 = store.inspect_target_recovery(doc_id)
    assert rec4.status == "clean"
    assert not rec4.recovery_required
    assert rec4.current_pointer == pointer_complete
