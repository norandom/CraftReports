"""Real retained report evidence must survive independent kernel readback."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from report_host_fixture import ALICE, ReportHost, report_host
from sqlalchemy import update
from sqlalchemy.engine import Connection
from test_pack_reader import assets as assets
from test_prepare import definition as definition
from test_prepare import snapshot as snapshot
from test_themes import theme as theme

from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import evidence
from craftreport.adapters.storage.serialization import encode_evidence
from craftreport.application.ports import ServiceUnavailable
from craftreport.application.service_values import ResourceSnapshot
from craftreport.contracts import (
    Availability,
    EvidenceRef,
    EvidenceStatus,
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    Receipt,
    ReceiptState,
    Rejection,
    StageState,
)
from craftreport.data.values import Snapshot

PACK = {"namespace": "public", "name": "example", "version": "1.0.0"}


def inject_fault(monkeypatch: pytest.MonkeyPatch, fault: str) -> list[EvidenceRef]:
    retained: list[EvidenceRef] = []
    original = DurableResults.retain_preparation_fact
    inspect = DurableEvidence.inspect

    async def retain(
        self: DurableResults, reference: EvidenceRef, canonical_fact: JsonObject
    ) -> EvidenceRef | ServiceUnavailable:
        result = await original(self, reference, canonical_fact)
        if isinstance(result, ServiceUnavailable):
            return result
        retained.append(result)
        if fault not in ("omitted", "altered"):
            return result
        pins = reference.resource_versions
        if fault == "omitted":
            pins = tuple(pin for pin in pins if pin.resource.kind != "report_pack_source")
        else:
            pins = tuple(
                replace(pin, version="0" * 64) if pin.resource.kind == "report_pack_source" else pin
                for pin in pins
            )
        encoded, digest = encode_evidence(replace(reference, resource_versions=pins))

        def corrupt(connection: Connection) -> None:
            connection.execute(
                update(evidence)
                .where(evidence.c.identity == reference.identity)
                .values(reference_bytes=encoded, reference_digest=digest)
            )

        await self.database.transaction(corrupt)
        return result

    async def unavailable(
        self: DurableEvidence, refs: tuple[EvidenceRef, ...]
    ) -> tuple[EvidenceStatus, ...]:
        actual = await inspect(self, refs)
        return tuple(
            EvidenceStatus(item.reference, Availability.UNAVAILABLE)
            if item.reference.scope in ("prepared", "quality_evaluated") and fault == "unavailable"
            else item
            for item in actual
        )

    monkeypatch.setattr(DurableResults, "retain_preparation_fact", retain)
    monkeypatch.setattr(DurableEvidence, "inspect", unavailable)
    return retained


async def check_public_readback(
    host: ReportHost, receipt: Receipt, payload: JsonObject, fault: str
) -> None:
    result = await host.facade.read_result(ALICE, receipt.operation_id)
    retry = await host.facade.invoke(
        ALICE,
        InvocationEnvelope(OperationKey("reports.prepare", "1"), payload, "retry", "fault-test"),
    )
    inspected = await host.facade.inspect(ALICE, receipt.operation_id)
    if fault in ("omitted", "altered"):
        for response in (result, retry, inspected):
            assert isinstance(response, Rejection)
            assert response.diagnostic.code == "evidence_inaccessible"
    else:
        assert not isinstance(result, Rejection)
        assert retry == receipt and inspected == receipt
    assert await DurableJournal(host.resources.database).read(receipt.operation_id) == receipt


@pytest.mark.parametrize("fault", ["healthy", "omitted", "altered", "unavailable"])
def test_real_full_pin_evidence_gate_and_restart(
    tmp_path: Path,
    assets: dict[str, bytes],
    snapshot: Snapshot,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            reference = await host.publish(snapshot)
            payload: JsonObject = {"pack": PACK, "snapshot": reference}
            with monkeypatch.context() as patch:
                retained = inject_fault(patch, fault)
                receipt = await host.invoke("reports.prepare", payload, "fault-test")
            assert len(retained) == 2
            assert receipt.state is (
                ReceiptState.COMPLETE if fault == "healthy" else ReceiptState.FAILED
            ), receipt
            assert receipt.evidence == tuple(retained)
            assert all(len(ref.resource_versions) == 3 for ref in retained)
            assert {pin.resource for pin in retained[0].resource_versions} == set(receipt.resources)
            for pin in retained[0].resource_versions:
                actual = await host.activation.resources.read(pin.resource)
                assert isinstance(actual, ResourceSnapshot) and actual.version == pin
            assert all(stage.state is StageState.PASSED for stage in receipt.stages) is (
                fault == "healthy"
            )
            if fault != "healthy":
                expected = (
                    "evidence_unavailable" if fault == "unavailable" else "evidence_inaccessible"
                )
                assert all(stage.reason_code == expected for stage in receipt.stages)
            assert receipt.result_ref is not None
            result = await DurableResults(host.resources.database).read(
                ALICE, receipt.operation_id, receipt.result_ref
            )
            assert result.availability is Availability.AVAILABLE
            await check_public_readback(host, receipt, payload, fault)
        async with report_host(tmp_path, assets) as reopened:
            await check_public_readback(reopened, receipt, payload, fault)
            assert (
                await DurableResults(reopened.resources.database).read(
                    ALICE, receipt.operation_id, receipt.result_ref
                )
                == result
            )
            statuses = await DurableEvidence(reopened.resources.database).inspect(receipt.evidence)
            expected = (
                Availability.INACCESSIBLE
                if fault in ("omitted", "altered")
                else Availability.AVAILABLE
            )
            assert all(status.availability is expected for status in statuses)

    asyncio.run(exercise())
