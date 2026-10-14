"""Authorized result reads through real execution and ordinary adapters."""

import json
from dataclasses import replace

import pytest
from fixture_admission import AdmissionFixture
from fixture_dispatch import ALICE, BOB, KEY, RESOURCE, FixtureResults
from fixture_execution import executor
from mcp.types import TextContent
from test_mcp import connection
from test_transport_parity import client, envelope

from craftreport.application import ports
from craftreport.application.dispatch_ports import RetainedResult
from craftreport.application.registry import ImmutableOperationRegistry
from craftreport.contracts import (
    Availability,
    Principal,
    Receipt,
    ReceiptState,
    Rejection,
    ResultReadback,
)


@pytest.mark.anyio
async def test_result_readback_preserves_exact_receipt_and_does_not_execute() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await owner.invoke(ALICE, fixture.request())
    assert isinstance(receipt, Receipt)
    before = await fixture.target.read(RESOURCE)
    owners = dict(fixture.journal.owners)
    result = await owner.read_result(ALICE, receipt.operation_id)
    assert isinstance(result, ResultReadback)
    assert result.receipt == receipt
    assert result.value == {"value": "changed"}
    assert await fixture.target.read(RESOURCE) == before
    assert fixture.journal.owners == owners
    assert fixture.target.effect_count == 1


@pytest.mark.anyio
async def test_rest_mcp_readback_share_canonical_content() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        receipt = (await rest.post("/v1/invoke", json=envelope())).json()
        identity = receipt["operation_id"]
        response = await rest.get(f"/v1/operations/{identity}/result")
        assert response.status_code == 200
        result = await mcp.call_tool("craftreport.result.v1", {"operation_id": identity})
        assert not result.is_error
        assert (
            result.structured_content
            == response.json()
            == {"receipt": receipt, "value": {"value": "changed"}}
        )
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text) == response.json()
        assert fixture.target.effect_count == 1


def query_fixture() -> AdmissionFixture:
    fixture = AdmissionFixture()
    fixture.registry = ImmutableOperationRegistry((fixture.binding.bind(),))
    fixture.guards = replace(fixture.guards, registry=fixture.registry)
    fixture.admission = replace(fixture.admission, guards=fixture.guards)
    fixture.catalog = replace(fixture.catalog, operations=fixture.registry.describe())
    fixture.access.operation_scopes[KEY] = "read"
    return fixture


@pytest.mark.anyio
@pytest.mark.parametrize("mcp_first", [False, True])
async def test_query_retrieval_in_both_transport_orders_is_read_only(mcp_first: bool) -> None:
    fixture = query_fixture()
    owner = executor(fixture)
    before = await fixture.target.read(RESOURCE)
    request = envelope(
        operation="fixture.read", payload={"target": "target"}, retry_key=None, expected_versions=[]
    )
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        if mcp_first:
            called = await mcp.call_tool("fixture.read.v1", request)
            receipt = called.structured_content
        else:
            receipt = (await rest.post("/v1/invoke", json=request)).json()
        assert receipt is not None
        identity = receipt["operation_id"]
        mcp_result = await mcp.call_tool("craftreport.result.v1", {"operation_id": identity})
        rest_result = await rest.get(f"/v1/operations/{identity}/result")
        assert rest_result.status_code == 200
        assert (
            mcp_result.structured_content
            == rest_result.json()
            == {"receipt": receipt, "value": {"value": "retained"}}
        )
        assert await fixture.target.read(RESOURCE) == before
        assert fixture.target.effect_count == 0
        assert fixture.calls == 1
        assert len(fixture.journal.owners) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("state", list(ReceiptState))
async def test_readback_preserves_current_noncomplete_state_and_mcp_errors(
    state: ReceiptState,
) -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    current = await seed_result(fixture, state)
    receipt = current
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        result = await mcp.call_tool(
            "craftreport.result.v1", {"operation_id": receipt.operation_id}
        )
        assert result.structured_content is not None
        assert result.structured_content["receipt"]["state"] == state.value
        assert result.structured_content["receipt"]["revision"] == current.revision
        assert result.is_error == (
            state in (ReceiptState.PARTIAL, ReceiptState.AMBIGUOUS, ReceiptState.FAILED)
        )
        response = await rest.get(f"/v1/operations/{receipt.operation_id}/result")
        assert response.status_code == (
            202 if state in (ReceiptState.ACCEPTED, ReceiptState.PENDING) else 200
        )
        assert response.json() == result.structured_content
        assert await fixture.journal.read(receipt.operation_id) == current
        assert fixture.target.effect_count == 0


class ReadProbe(FixtureResults):
    def __init__(self, mode: str = "normal") -> None:
        super().__init__()
        self.mode = mode
        self.lookups: list[tuple[Principal, str, str]] = []

    async def read(self, principal: Principal, operation_id: str, reference: str) -> RetainedResult:
        self.lookups.append((principal, operation_id, reference))
        if self.mode == "exception":
            raise RuntimeError("private-provider-secret")
        if self.mode == "mismatch":
            return RetainedResult(
                "foreign-reference", Availability.AVAILABLE, {"secret": "foreign"}
            )
        return await super().read(principal, operation_id, reference)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode,code",
    [
        ("missing", "result_missing"),
        ("inaccessible", "result_inaccessible"),
        ("unavailable", "result_unavailable"),
        ("mismatch", "result_unavailable"),
        ("exception", "service_unavailable"),
    ],
)
async def test_failed_retained_lookup_never_discloses_or_regenerates(mode: str, code: str) -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await owner.invoke(ALICE, fixture.request())
    assert isinstance(receipt, Receipt)
    results = ReadProbe(mode)
    if mode in ("missing", "inaccessible", "unavailable"):
        results.read_availability = Availability(mode)
    owner.inspection = replace(owner.inspection, results=results)
    async with client(fixture, owner=owner) as rest, connection(fixture, owner) as mcp:
        response = await rest.get(f"/v1/operations/{receipt.operation_id}/result")
        result = await mcp.call_tool(
            "craftreport.result.v1", {"operation_id": receipt.operation_id}
        )
        assert result.is_error and result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == code
        assert response.json()["diagnostic"]["code"] == code
        assert "value" not in response.json() and "receipt" not in response.json()
        assert "secret" not in response.text and "foreign" not in response.text
        assert fixture.calls == fixture.target.effect_count == 1
        assert len(fixture.journal.owners) == 1
        assert all(
            item == (ALICE, receipt.operation_id, receipt.result_ref) for item in results.lookups
        )


@pytest.mark.anyio
async def test_authorization_precedes_result_lookup_and_foreign_clients_get_no_content() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await owner.invoke(ALICE, fixture.request())
    assert isinstance(receipt, Receipt)
    probe = ReadProbe()
    owner.inspection = replace(owner.inspection, results=probe)
    denied = await owner.read_result(BOB, receipt.operation_id)
    assert isinstance(denied, Rejection) and denied.diagnostic.code == "access_denied"
    async with connection(fixture, owner, identity=BOB) as mcp:
        result = await mcp.call_tool(
            "craftreport.result.v1", {"operation_id": receipt.operation_id}
        )
        assert result.is_error and result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "access_denied"
        assert "value" not in result.structured_content
    async with client(fixture, owner=owner) as rest:
        fixture.access.grants = ()
        response = await rest.get(f"/v1/operations/{receipt.operation_id}/result")
        assert response.status_code == 404
        assert response.json()["diagnostic"]["code"] == "access_denied"
    assert not probe.lookups
    assert fixture.calls == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"operation_id": " "},
        {"operation_id": "identity", "result_ref": "private"},
        {"operation_id": "identity", "principal": "alice"},
    ],
)
async def test_mcp_result_accepts_only_operation_identity(arguments: dict[str, object]) -> None:
    fixture = AdmissionFixture()
    async with connection(fixture) as mcp:
        result = await mcp.call_tool("craftreport.result.v1", arguments)
        assert result.is_error and result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "invalid_input"
        assert not fixture.journal.owners and fixture.calls == 0


async def seed_result(
    fixture: AdmissionFixture, state: ReceiptState, *, absent: bool = False
) -> Receipt:
    reference = (
        None
        if absent
        else await fixture.results.write(
            ALICE,
            "retained-id",
            {"nested": [None, True, "9007199254740993", "1.2300", {"unicode": "€"}], "empty": {}},
        )
    )
    return await fixture.journal.record_query(
        ports.QueryObservation(
            "retained-id",
            ALICE,
            KEY,
            "retained-correlation",
            (),
            (RESOURCE,),
            (),
            ports.ReceiptUpdate(
                state,
                result_ref=reference,
                result_availability=Availability.MISSING if absent else Availability.AVAILABLE,
            ),
        )
    )


@pytest.mark.anyio
async def test_absent_result_is_rejected_without_lookup_and_inspect_is_unchanged() -> None:
    fixture = AdmissionFixture()
    owner = executor(fixture)
    receipt = await seed_result(fixture, ReceiptState.FAILED, absent=True)
    probe = ReadProbe()
    owner.inspection = replace(owner.inspection, results=probe)
    assert await owner.inspect(ALICE, receipt.operation_id) == receipt
    result = await owner.read_result(ALICE, receipt.operation_id)
    assert isinstance(result, Rejection) and result.diagnostic.code == "result_missing"
    assert not probe.lookups and fixture.calls == 0
    assert fixture.target.effect_count == 0
