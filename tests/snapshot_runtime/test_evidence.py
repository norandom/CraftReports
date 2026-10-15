"""Retained preparation and publication facts preserve original observation scope."""

import asyncio
import hashlib
import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import evidence
from craftreport.adapters.storage.serialization import encode_evidence
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CommandIntent,
    EvidenceRef,
    ExpectedVersion,
    JsonObject,
    OperationKey,
    ResourceRef,
    RetryKey,
    StageState,
)

CHECKS = (
    "definition",
    "bindings",
    "semantic_resolution",
    "layout_fit",
    "target_consistency",
    "artifact_consistency",
    "artifact_reopen",
    "metric_methodology",
    "compliance_statement",
)
PINS = tuple(
    ExpectedVersion(ResourceRef(kind, identity), digest * 64)
    for kind, identity, digest in (
        ("snapshot", "portfolio:1", "a"),
        ("report_pack_source", "public:one", "b"),
        ("report_pack_artifact_scope", "public:one", "c"),
    )
)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    value = Database(tmp_path / "evidence.sqlite3", "deployment-a")
    yield value
    asyncio.run(value.close())


def fact(stage: str = "prepared") -> JsonObject:
    count = 3 if stage == "prepared" else 9
    return {
        "schema_version": "1",
        "stage": stage,
        "prepared_digest": "d" * 64,
        "validation_scope_digest": "e" * 64,
        "checks": tuple(
            {
                "check_id": name,
                "status": "passed" if index < 3 else "unevaluated",
                "origin": "craftreport",
                "reason_code": "observed",
            }
            for index, name in enumerate(CHECKS[:count])
        ),
        "decision": None
        if stage == "prepared"
        else {
            "requested_designation": "validated",
            "draft_eligible": True,
            "validated_release_eligible": False,
            "blocking_checks": ["layout_fit"],
        },
    }


@pytest.mark.parametrize("damage", ["query", "failed", "external", "decision", "reference_bound"])
def test_prepared_requires_command_and_successful_checks(database: Database, damage: str) -> None:
    from craftreport.contracts import Principal, ReceiptState

    async def exercise() -> None:
        ref = await reference(database)
        value = dict(fact())
        if damage == "query":
            observation = ports.QueryObservation(
                "query-header",
                Principal("deployment-a", "alice", frozenset()),
                ref.operation,
                "query",
                (),
                tuple(pin.resource for pin in PINS),
                (),
                ports.ReceiptUpdate(ReceiptState.FAILED),
            )
            await DurableJournal(database).record_query(observation)
            ref = replace(ref, operation_id="query-header")
        elif damage == "decision":
            value["decision"] = {
                "requested_designation": "draft",
                "draft_eligible": True,
                "validated_release_eligible": False,
                "blocking_checks": [],
            }
        elif damage == "reference_bound":
            ref = replace(ref, identity="x" * 3072)
        else:
            value["checks"] = tuple(
                {
                    "check_id": name,
                    "status": "failed" if damage == "failed" else "passed",
                    "origin": "external" if damage == "external" else "craftreport",
                    "reason_code": "observed",
                }
                for name in CHECKS[:3]
            )
        ref = replace(ref, content_digest=hashlib.sha256(canonical_bytes(value)).hexdigest())
        assert isinstance(
            await DurableResults(database).retain_preparation_fact(ref, value),
            ports.ServiceUnavailable,
        )

    asyncio.run(exercise())


async def reference(
    database: Database,
    stage: str = "prepared",
    *,
    preconditions: bool = True,
    operation: OperationKey = OperationKey("reports.prepare", "1"),
    pins: tuple[ExpectedVersion, ...] = PINS,
) -> EvidenceRef:
    intent = CommandIntent(
        RetryKey("deployment-a", "alice", operation, uuid4().hex),
        "a" * 64,
        "craftreport-json-v1",
        "correlation",
        (),
        tuple(p.resource for p in pins),
        pins if preconditions else (),
    )
    admitted = await DurableJournal(database).admit(intent)
    assert isinstance(admitted, ports.Admitted)
    return EvidenceRef(
        uuid4().hex,
        stage,
        admitted.receipt.operation_id,
        operation,
        pins,
        hashlib.sha256(canonical_bytes(fact(stage))).hexdigest(),
    )


@pytest.mark.parametrize("stage", ["prepared", "quality_evaluated"])
@pytest.mark.parametrize("preconditions", [True, False])
def test_original_fact_bytes_pins_and_blocked_decision_reopen(
    database: Database, stage: str, preconditions: bool
) -> None:
    async def exercise() -> None:
        ref = await reference(database, stage, preconditions=preconditions)
        writer = DurableResults(database)
        assert await writer.retain_preparation_fact(ref, fact(stage)) == ref
        assert await writer.retain_preparation_fact(ref, fact(stage)) == ref
        expected = await DurableEvidence(database).inspect((ref,))
        assert expected[0].availability is Availability.AVAILABLE
        assert expected[0].verification is StageState.PASSED
        await database.close()
        payload = canonical_bytes(fact(stage))
        with sqlite3.connect(database.path) as independent:
            row = independent.execute("SELECT fact_bytes,fact_digest FROM evidence").fetchone()
            assert row == (payload, hashlib.sha256(payload).hexdigest())
            assert independent.execute("SELECT count(*) FROM results").fetchone() == (0,)
        reopened = Database(database.path, "deployment-a")
        try:
            assert await DurableEvidence(reopened).inspect((ref,)) == expected
        finally:
            await reopened.close()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "damage",
    [
        "extra",
        "stage",
        "check",
        "order",
        "duplicate",
        "status",
        "origin",
        "bool",
        "body",
        "digest",
        "decision",
        "oversize",
    ],
)
def test_closed_fact_rejects_without_retention(database: Database, damage: str) -> None:
    async def exercise() -> None:
        ref = await reference(database, "quality_evaluated")
        value = dict(fact("quality_evaluated"))
        checks = [
            dict(check_id=name, status="passed", origin="craftreport", reason_code="observed")
            for name in CHECKS
        ]
        root_changes: dict[str, JsonObject] = {
            "extra": {"private_rows": []},
            "stage": {"stage": "artifact_reopened"},
            "digest": {"prepared_digest": "wrong"},
            "decision": {"decision": None},
            "oversize": {"source": "x" * 16_384},
            "bool": {
                "decision": {
                    "requested_designation": "validated",
                    "draft_eligible": 1,
                    "validated_release_eligible": False,
                    "blocking_checks": [],
                }
            },
        }
        if damage in root_changes:
            value.update(root_changes[damage])
        elif damage == "check":
            checks[0]["check_id"] = "invented"
        elif damage == "order":
            checks.reverse()
        elif damage == "duplicate":
            checks[-1] = checks[0]
        elif damage == "status":
            checks[0]["status"] = "trusted"
        elif damage == "origin":
            checks[0]["origin"] = "producer"
        elif damage == "body":
            checks[0]["reason_code"] = "C:/private/file"
        value["checks"] = tuple(checks)
        ref = replace(ref, content_digest=hashlib.sha256(canonical_bytes(value)).hexdigest())
        assert isinstance(
            await DurableResults(database).retain_preparation_fact(ref, value),
            ports.ServiceUnavailable,
        )
        assert await database.transaction(lambda c: c.scalar(select(evidence.c.identity))) is None

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "damage",
    [
        "missing_pin",
        "extra_pin",
        "pin_version",
        "pack_identity",
        "operation",
        "key",
        "scope",
        "ref_digest",
        "wrong_version",
    ],
)
def test_fact_original_operation_and_full_set_are_required(database: Database, damage: str) -> None:
    async def exercise() -> None:
        key = (
            OperationKey("reports.prepare", "2")
            if damage == "wrong_version"
            else OperationKey("reports.prepare", "1")
        )
        ref = await reference(database, operation=key)
        if damage == "missing_pin":
            ref = replace(ref, resource_versions=PINS[:2])
        elif damage == "extra_pin":
            ref = replace(
                ref, resource_versions=(*PINS, ExpectedVersion(ResourceRef("target", "one"), "1"))
            )
        elif damage == "pin_version":
            ref = replace(ref, resource_versions=(replace(PINS[0], version="f" * 64), *PINS[1:]))
        elif damage == "pack_identity":
            ref = replace(
                ref,
                resource_versions=(
                    *PINS[:2],
                    replace(PINS[2], resource=ResourceRef("report_pack_artifact_scope", "other")),
                ),
            )
        elif damage == "operation":
            ref = replace(ref, operation_id="missing")
        elif damage == "key":
            ref = replace(ref, operation=OperationKey("snapshot.publish", "1"))
        elif damage == "scope":
            ref = replace(ref, scope="target_applied")
        elif damage == "ref_digest":
            ref = replace(ref, content_digest="f" * 64)
        assert isinstance(
            await DurableResults(database).retain_preparation_fact(ref, fact()),
            ports.ServiceUnavailable,
        )
        assert await database.transaction(lambda c: c.scalar(select(evidence.c.identity))) is None

    asyncio.run(exercise())


def test_independent_inspection_missing_corrupt_unknown_and_identity_collision(
    database: Database,
) -> None:
    async def exercise() -> None:
        ref = await reference(database)
        store, reader = DurableResults(database), DurableEvidence(database)
        assert await store.retain_preparation_fact(ref, fact()) == ref
        altered = replace(ref, resource_versions=tuple(reversed(ref.resource_versions)))
        unknown = replace(ref, scope="artifact_reopened")
        statuses = await reader.inspect((altered, unknown, replace(ref, identity="absent"), ref))
        assert [s.availability for s in statuses] == [
            Availability.INACCESSIBLE,
            Availability.INACCESSIBLE,
            Availability.MISSING,
            Availability.AVAILABLE,
        ]
        changed = dict(fact())
        changed["prepared_digest"] = "f" * 64
        collision = replace(
            ref, content_digest=hashlib.sha256(canonical_bytes(changed)).hexdigest()
        )
        assert isinstance(
            await store.retain_preparation_fact(collision, changed), ports.ServiceUnavailable
        )
        await database.transaction(lambda c: c.execute(update(evidence).values(fact_bytes=b"bad")))
        status = (await reader.inspect((ref,)))[0]
        assert (
            status.availability is Availability.UNAVAILABLE
            and status.verification is StageState.PENDING
        )
        await database.transaction(lambda c: c.execute(delete(evidence)))
        assert (await reader.inspect((ref,)))[0].availability is Availability.MISSING
        await database.close()
        assert (await reader.inspect((ref,)))[0].availability is Availability.UNAVAILABLE

    asyncio.run(exercise())


def test_unknown_retained_scope_never_passes_and_corrupt_owner_is_unavailable(
    database: Database,
) -> None:
    from craftreport.adapters.storage.schema import commands

    async def exercise() -> None:
        ref = await reference(database)
        assert await DurableResults(database).retain_preparation_fact(ref, fact()) == ref
        unknown = replace(ref, scope="artifact_reopened")
        payload, digest = encode_evidence(unknown)
        await database.transaction(
            lambda c: c.execute(
                update(evidence).values(reference_bytes=payload, reference_digest=digest)
            )
        )
        result = (await DurableEvidence(database).inspect((unknown,)))[0]
        assert (
            result.availability is Availability.UNAVAILABLE
            and result.verification is StageState.PENDING
        )
        payload, digest = encode_evidence(ref)
        await database.transaction(
            lambda c: c.execute(
                update(evidence).values(reference_bytes=payload, reference_digest=digest)
            )
        )
        await database.transaction(lambda c: c.execute(update(commands).values(subject="bob")))
        assert (await DurableEvidence(database).inspect((ref,)))[
            0
        ].availability is Availability.UNAVAILABLE

    asyncio.run(exercise())


def test_largest_closed_fact_is_bounded_and_failed_findings_are_retained(
    database: Database,
) -> None:
    async def exercise() -> None:
        value = dict(fact("quality_evaluated"))
        value["checks"] = tuple(
            {"check_id": check, "status": "failed", "origin": "external", "reason_code": "x" * 64}
            for check in CHECKS
        )
        value["decision"] = {
            "requested_designation": "validated",
            "draft_eligible": False,
            "validated_release_eligible": False,
            "blocking_checks": CHECKS,
        }
        payload = canonical_bytes(value)
        assert len(payload) < 16_384
        ref = replace(
            await reference(database, "quality_evaluated"),
            content_digest=hashlib.sha256(payload).hexdigest(),
        )
        assert await DurableResults(database).retain_preparation_fact(ref, value) == ref
        assert (await DurableEvidence(database).inspect((ref,)))[
            0
        ].verification is StageState.PASSED
        assert (
            await database.transaction(lambda c: c.scalar(select(evidence.c.fact_bytes))) == payload
        )

    asyncio.run(exercise())
