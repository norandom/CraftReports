"""Independent decision proof rejects missing, mismatched and rewritten support."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import delete, update

from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.schema import evidence
from craftreport.adapters.storage.serialization import decode_object, encode_evidence, encode_object
from craftreport.application import ports
from craftreport.contracts import Availability, ExpectedVersion, StageState
from tests.snapshot_runtime.test_providers import FEED, provider, publish


@pytest.mark.parametrize("mode", ["missing_support", "wrong_pin", "wrong_op", "historical_status"])
def test_decision_reference_alone_requires_exact_support(tmp_path: Path, mode: str) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "evidence.sqlite3", "deployment-a")
        try:
            resources = provider(database)
            effect = await publish(resources, database)
            assert isinstance(effect, ports.ResourceEffect)
            persistence, decision = effect.evidence
            assert (await DurableEvidence(database).inspect((decision,)))[
                0
            ].verification is StageState.PASSED
            if mode == "missing_support":
                await database.transaction(
                    lambda c: c.execute(
                        delete(evidence).where(evidence.c.identity == persistence.identity)
                    )
                )
            elif mode == "historical_status":

                def corrupt(connection: object) -> None:
                    from sqlalchemy.engine import Connection

                    assert isinstance(connection, Connection)
                    row = (
                        connection.execute(
                            evidence.select().where(evidence.c.identity == decision.identity)
                        )
                        .mappings()
                        .one()
                    )
                    fact = {
                        **decode_object(row["fact_bytes"], row["fact_digest"]),
                        "status": "existing",
                    }
                    payload, digest = encode_object(fact)
                    rewritten = replace(decision, content_digest=digest)
                    ref_bytes, ref_digest = encode_evidence(rewritten)
                    connection.execute(
                        update(evidence)
                        .where(evidence.c.identity == decision.identity)
                        .values(
                            fact_bytes=payload,
                            fact_digest=digest,
                            reference_bytes=ref_bytes,
                            reference_digest=ref_digest,
                        )
                    )

                await database.transaction(corrupt)
            else:
                changed = (
                    replace(persistence, operation_id="foreign")
                    if mode == "wrong_op"
                    else replace(persistence, resource_versions=(ExpectedVersion(FEED, "99"),))
                )
                body, digest = encode_evidence(changed)
                await database.transaction(
                    lambda c: c.execute(
                        update(evidence)
                        .where(evidence.c.identity == persistence.identity)
                        .values(reference_bytes=body, reference_digest=digest)
                    )
                )
            observed = (await DurableEvidence(database).inspect((decision,)))[0]
            assert observed.availability is not Availability.AVAILABLE
            assert isinstance(
                await resources.store.read_decision(decision.operation_id), ports.ServiceUnavailable
            )
        finally:
            await database.close()

    asyncio.run(exercise())
