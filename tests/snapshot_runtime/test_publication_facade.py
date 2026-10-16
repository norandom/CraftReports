"""Ordinary facade publication receipts, exact queries, retry and access checks."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from craftreport.adapters.storage.database import Database
from craftreport.contracts import (
    ExpectedVersion,
    InvocationEnvelope,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
)
from tests.snapshot_runtime.publication_fixture import PublicationFixture
from tests.snapshot_runtime.test_providers import FEED, producer

ALICE = Principal("deployment-a", "alice", frozenset())


def request(version: int, previous: str, key: str) -> InvocationEnvelope:
    return InvocationEnvelope(
        OperationKey("snapshot.publish", "1"),
        producer(version),
        key,
        key,
        (ExpectedVersion(FEED, previous),),
    )


def test_complete_receipts_retained_original_retry_and_exact_queries(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "facade.sqlite3", ALICE.deployment_scope)
        fixture = PublicationFixture(database)
        try:
            first = await fixture.facade.invoke(ALICE, request(3, "absent", "one"))
            assert isinstance(first, Receipt) and first.state is ReceiptState.COMPLETE
            assert await fixture.facade.invoke(ALICE, request(3, "absent", "one")) == first
            assert isinstance(
                await fixture.facade.invoke(ALICE, request(4, "absent", "one")), Rejection
            )
            for envelope, status in (
                (request(3, "1", "two"), "existing"),
                (request(2, "1", "three"), "stale_version"),
            ):
                receipt = await fixture.facade.invoke(ALICE, envelope)
                assert isinstance(receipt, Receipt) and receipt.state is ReceiptState.COMPLETE
                assert receipt.result_ref is not None
                result = await fixture.results.read(ALICE, receipt.operation_id, receipt.result_ref)
                assert result.value is not None and result.value["status"] == status
            assert first.result_ref is not None
            result = await fixture.results.read(ALICE, first.operation_id, first.result_ref)
            assert result.value is not None
            ref = result.value["requested"]
            from collections.abc import Mapping

            assert isinstance(ref, Mapping)
            query = InvocationEnvelope(OperationKey("snapshot.read", "1"), ref, "read")
            read = await fixture.facade.invoke(ALICE, query)
            assert isinstance(read, Receipt) and read.state is ReceiptState.COMPLETE
            assert read.result_ref is not None
            content = await fixture.results.read(ALICE, read.operation_id, read.result_ref)
            assert content.value is not None and content.value["producer_version"] == "3"
            assert "snapshot" not in content.value
        finally:
            assert await fixture.facade.shutdown()
            await database.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("mode", ["lost_ack", "precommit", "dropped", "wrong_pin"])
def test_effect_acknowledgement_and_exact_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async def exercise() -> None:
        from craftreport.application import ports
        from craftreport.contracts import JsonObject, ResourceRef

        database = Database(tmp_path / "fault.sqlite3", ALICE.deployment_scope)
        fixture = PublicationFixture(database)
        original = fixture.resources.apply

        async def apply(
            resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
        ) -> ports.ResourceEffectResult:
            if mode == "precommit":
                return ports.ServiceUnavailable("effects")
            observed = await original(resource, change, guard)
            assert isinstance(observed, ports.ResourceEffect)
            if mode == "lost_ack":
                return ports.ServiceUnavailable("effects")
            if mode == "dropped":
                return replace(observed, evidence=observed.evidence[1:])
            return replace(observed, versions=(ExpectedVersion(FEED, "999"),))

        monkeypatch.setattr(fixture.resources, "apply", apply)
        try:
            receipt = await fixture.facade.invoke(ALICE, request(1, "absent", "fault"))
            assert isinstance(receipt, Receipt)
            expected = ReceiptState.COMPLETE if mode == "lost_ack" else ReceiptState.AMBIGUOUS
            assert receipt.state is expected
        finally:
            assert await fixture.facade.shutdown()
            await database.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("denied", ["feed", "snapshot.publish", "snapshot.read", "snapshot.latest"])
def test_operation_and_resource_denials(tmp_path: Path, denied: str) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "access.sqlite3", ALICE.deployment_scope)
        fixture = PublicationFixture(database)
        fixture.access.denied.add(denied)
        try:
            envelope = request(1, "absent", "one")
            if denied == "snapshot.latest":
                envelope = InvocationEnvelope(
                    OperationKey(denied, "1"),
                    {"feed_id": FEED.identity, "requirements": None},
                    "latest",
                )
            elif denied == "snapshot.read":
                envelope = InvocationEnvelope(
                    OperationKey(denied, "1"),
                    {"feed_id": FEED.identity, "producer_version": "1", "content_digest": "a" * 64},
                    "read",
                )
            assert isinstance(await fixture.facade.invoke(ALICE, envelope), Rejection)
            assert isinstance(
                await fixture.facade.invoke(replace(ALICE, subject="catalog-only"), envelope),
                Rejection,
            )
        finally:
            assert await fixture.facade.shutdown()
            await database.close()

    asyncio.run(exercise())
