"""Publication decision evidence and principal-bound immutable query acceptance."""

import asyncio
import sqlite3
from pathlib import Path

import pytest

from craftreport.adapters.storage.database import Database
from craftreport.application import ports
from craftreport.contracts import EffectDisposition, ExpectedVersion, JsonObject
from tests.snapshot_runtime.test_providers import FEED, admitted, provider, publish


def test_current_operation_decisions_for_accept_duplicate_stale(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "publication.sqlite3", "deployment-a")
        try:
            resources = provider(database)
            accepted = await publish(resources, database, 3)
            duplicate = await publish(resources, database, 3, "1")
            stale = await publish(resources, database, 2, "1")
            assert isinstance(accepted, ports.ResourceEffect)
            assert {ref.scope for ref in accepted.evidence} == {
                "snapshot_persisted",
                "publication_decided",
            }
            for outcome in (duplicate, stale):
                assert isinstance(outcome, ports.ResourceEffect)
                assert outcome.effect is EffectDisposition.NONE
                assert [ref.scope for ref in outcome.evidence] == ["publication_decided"]
                assert outcome.evidence[0].operation_id != accepted.evidence[0].operation_id
        finally:
            await database.close()

    asyncio.run(exercise())


def _publication_rows(path: Path) -> dict[str, list[tuple[object, ...]]]:
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute("SELECT * FROM " + table).fetchall()
            for table in ("feeds", "snapshots", "evidence")
        }


def test_finalized_byte_overflow_preserves_prior_content_and_facts(tmp_path: Path) -> None:
    from craftreport.adapters.canonical import canonical_bytes
    from craftreport.adapters.snapshot_wire import snapshot_codec
    from craftreport.data.values import Snapshot

    normal = snapshot_codec()

    class FaultyFinalEncoding:
        """Inject a service-field serialization defect after normal codec validation."""

        def decode(self, value: JsonObject) -> Snapshot:
            return normal.decode(value)

        def encode(self, value: Snapshot) -> JsonObject:
            encoded = normal.encode(value)
            if value.producer_version == 2:
                encoded = {**encoded, "received_at": "x" * 1_048_576}
                assert len(canonical_bytes(encoded)) > 1_048_576
            return encoded

        def schema(self) -> JsonObject:
            return normal.schema()

    async def exercise() -> None:
        database = Database(tmp_path / "final-bound.sqlite3", "deployment-a")
        try:
            resources = provider(database)
            assert isinstance(await publish(resources, database), ports.ResourceEffect)
            before = _publication_rows(database.path)
            operation_id, change = await admitted(database, 2, "1")
            resources.store.codec = FaultyFinalEncoding()
            async with resources.guard.acquire((ExpectedVersion(FEED, "1"),)) as guard:
                result = await resources.apply(FEED, change, guard)
            assert isinstance(result, ports.ServiceUnavailable)
            assert _publication_rows(database.path) == before
            assert isinstance(await resources.store.read_decision(operation_id), ports.Missing)
            resources.store.codec = normal
            current = await resources.read(FEED)
            assert isinstance(current, ports.ResourceSnapshot)
            assert current.version.version == "1" and current.content["high_water"] == "1"
        finally:
            await database.close()
        assert _publication_rows(database.path) == before

    asyncio.run(exercise())


def test_accepted_result_cannot_claim_missing_content() -> None:
    from craftreport.contracts import Availability
    from craftreport.data.values import SnapshotRef
    from craftreport.runtime.publication import PublicationResult

    ref = SnapshotRef("feed", 1, "a" * 64)
    with pytest.raises(ValueError):
        PublicationResult("accepted", ref, ref, ref, Availability.MISSING, None)


def test_decision_readback_preserves_original_high_water(tmp_path: Path) -> None:
    async def exercise() -> None:
        from craftreport.runtime.publication import PublicationDecision

        database = Database(tmp_path / "history.sqlite3", "deployment-a")
        try:
            resources = provider(database)
            first = await publish(resources, database)
            assert isinstance(first, ports.ResourceEffect)
            await publish(resources, database, 2, "1")
            decision = await resources.store.read_decision(first.evidence[0].operation_id)
            assert isinstance(decision, PublicationDecision)
            assert decision.result.latest_accepted.producer_version == 1
            assert decision.result.summary is not None
            assert decision.evidence == first.evidence
        finally:
            await database.close()

    asyncio.run(exercise())


def test_principal_bound_exact_and_latest(tmp_path: Path) -> None:
    async def exercise() -> None:
        from craftreport.contracts import Principal
        from craftreport.data.requirements import InputRequirements
        from craftreport.runtime.publication import (
            LatestRequest,
            LatestSelection,
            PublicationDecision,
        )

        database = Database(tmp_path / "queries.sqlite3", "deployment-a")
        try:
            resources = provider(database)
            first = await publish(resources, database)
            assert isinstance(first, ports.ResourceEffect)
            decision = await resources.store.read_decision(first.evidence[0].operation_id)
            assert isinstance(decision, PublicationDecision)
            queries = resources.store.queries(Principal("deployment-a", "alice", frozenset()))
            ref = decision.result.requested
            result = await queries.latest(LatestRequest(ref.feed_id, InputRequirements((), ())))
            assert isinstance(result, LatestSelection) and result.highest_complete == ref
            from craftreport.data.values import Snapshot

            readback = await queries.read(ref)
            assert isinstance(readback, Snapshot) and readback.content_digest == ref.content_digest
            denied = resources.store.queries(Principal("deployment-a", "bob", frozenset()))
            assert isinstance(await denied.read(ref), ports.ServiceUnavailable)
        finally:
            await database.close()

    asyncio.run(exercise())
