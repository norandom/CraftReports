"""Retained-read provider failures and schema guarantees at the shared boundary."""

import json
from dataclasses import replace
from typing import Protocol, cast

import pytest
from fixture_admission import AdmissionFixture
from fixture_dispatch import ALICE
from fixture_execution import executor
from fixture_journal import FixtureJournal
from jsonschema import Draft202012Validator
from test_mcp import connection
from test_result_readback import ReadProbe, seed_result
from test_transport_parity import client

from craftreport.adapters.transport_wire import TransportWireAdapter
from craftreport.application import ports
from craftreport.contracts import (
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
    ResultReadback,
)


class AllowReceipt:
    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        return ports.AccessAllowed()


class MissingJournal(FixtureJournal):
    async def read(self, operation_id: str) -> Receipt | ports.Missing:
        return ports.Missing()


@pytest.mark.anyio
async def test_authorized_missing_receipt_is_not_a_successful_empty_result() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    probe = ReadProbe()
    owner.inspection = replace(
        owner.inspection, access=AllowReceipt(), journal=MissingJournal(), results=probe
    )
    result = await owner.read_result(ALICE, "missing")
    assert isinstance(result, Rejection)
    assert result.diagnostic.code == "receipt_missing"
    assert result.correlation_id and not probe.lookups
    assert not fixture.journal.owners and fixture.calls == 0


@pytest.mark.anyio
@pytest.mark.parametrize("provider", ["access", "journal"])
async def test_unavailable_authorization_or_journal_never_reads_content(provider: str) -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await seed_result(fixture, ReceiptState.COMPLETE)
    probe = ReadProbe()
    owner.inspection = replace(owner.inspection, results=probe)
    if provider == "access":
        fixture.access.available = False
    else:
        fixture.journal.available = False
    result = await owner.read_result(ALICE, receipt.operation_id)
    assert isinstance(result, Rejection)
    assert result.diagnostic.code == "service_unavailable"
    assert not probe.lookups and fixture.calls == 0


class SchemaValidator(Protocol):
    def is_valid(self, instance: object) -> bool: ...


@pytest.mark.anyio
async def test_shared_and_published_schemas_preserve_exact_retained_json() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await seed_result(fixture, ReceiptState.COMPLETE)
    result = await owner.read_result(ALICE, receipt.operation_id)
    assert isinstance(result, ResultReadback)
    wire = TransportWireAdapter()
    encoded = json.loads(wire.canonical_bytes(wire.encode_result_readback(result)))
    assert encoded["value"] == {
        "nested": [None, True, "9007199254740993", "1.2300", {"unicode": "€"}],
        "empty": {},
    }
    validator = cast(
        SchemaValidator,
        Draft202012Validator(json.loads(wire.canonical_bytes(wire.result_readback_schema()))),
    )
    assert validator.is_valid(encoded)
    assert not validator.is_valid({"receipt": encoded["receipt"]})
    assert not validator.is_valid({**encoded, "extra": True})
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        schemas = (await rest.get("/openapi.json")).json()
        schema = schemas["paths"]["/v1/operations/{operation_id}/result"]["get"]["responses"][
            "200"
        ]["content"]["application/json"]["schema"]
        assert cast(SchemaValidator, Draft202012Validator(schema)).is_valid(encoded)
        tool = next(t for t in (await mcp.list_tools()).tools if t.name == "craftreport.result.v1")
        assert tool.output_schema is not None
        assert cast(SchemaValidator, Draft202012Validator(tool.output_schema)).is_valid(encoded)


@pytest.mark.anyio
async def test_missing_result_and_unauthenticated_rest_return_structured_rejections() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await seed_result(fixture, ReceiptState.FAILED, absent=True)
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        response = await rest.get(f"/v1/operations/{receipt.operation_id}/result")
        result = await mcp.call_tool(
            "craftreport.result.v1", {"operation_id": receipt.operation_id}
        )
        assert response.status_code == 503
        assert response.json()["diagnostic"]["code"] == "result_missing"
        assert result.is_error and result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "result_missing"
        rest.headers.clear()
        response = await rest.get(f"/v1/operations/{receipt.operation_id}/result")
        assert response.status_code == 401
        assert response.json()["diagnostic"]["code"] == "unauthenticated"
        assert "value" not in response.json() and fixture.calls == 0
