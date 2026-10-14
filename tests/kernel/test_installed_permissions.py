"""Installed authorization and malformed-request checks preserve target state."""

import asyncio
import json

import httpx
import pytest
from fixture_packaging import InstalledFixture
from installed_clients import discover, mcp_client, rest_client
from installed_journeys import envelope, invoke, read_result, record_case, rejected
from installed_process import InstalledProcess
from mcp.shared.exceptions import MCPError

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_installed_invalid_requests(installed_runtime: InstalledFixture, transport: str) -> None:
    with InstalledProcess(installed_runtime, "invalid-" + transport) as owner:
        discover(owner)
        record_case(
            owner,
            "Invalid values and denied resources have no effect",
            ["2.2", "2.3", "3.1", "3.2", "5.2", "5.6", "6.2", "6.4", "7.2"],
        )
        before = owner.observe().model_dump(exclude={"request_id"})
        cases = [
            (envelope(payload={"resource": "target-1", "value": 12}), "invalid_input"),
            (envelope(principal="alice"), "invalid_input"),
            (envelope(payload={"resource": "private-target", "value": "secret"}), "access_denied"),
            (
                envelope(contract_version="2"),
                "unsupported_operation" if transport == "rest" else "invalid_input",
            ),
        ]
        for request, code in cases:
            result = invoke(owner, transport, request)
            rejected(result, code)
            assert "private-target" not in json.dumps(result)
            assert "secret" not in json.dumps(result)
            assert owner.observe().model_dump(exclude={"request_id"}) == before


def test_installed_private_discovery_and_identity(installed_runtime: InstalledFixture) -> None:
    with InstalledProcess(installed_runtime, "privacy") as owner:
        discover(owner)
        record_case(
            owner,
            "Two principals, hidden schemas, foreign receipts and spoofed authority",
            ["2.1", "3.2", "5.2", "5.3", "5.6", "6.1", "6.3", "6.4"],
        )
        receipt = invoke(owner, "rest", envelope())
        before = owner.observe().model_dump(exclude={"request_id"})
        with rest_client(owner, "bob") as bob:
            catalog = bob.get("/v1/catalog")
            assert catalog.status_code == 200 and catalog.json()["operations"] == []
            assert "synthetic.write" not in catalog.text
            hidden = bob.post(
                "/v1/invoke",
                json=envelope(),
                headers={
                    "X-Principal": "alice",
                    "X-AI-Origin": "true",
                    "X-Forwarded-User": "alice",
                },
            )
            assert hidden.status_code == 404
            rejected(hidden.json(), "access_denied")
            denied_version = bob.post("/v1/invoke", json=envelope(contract_version="2"))
            assert denied_version.status_code == 404
            rejected(denied_version.json(), "access_denied")
            foreign = bob.get("/v1/operations/" + receipt["operation_id"])
            assert foreign.status_code == 404
            assert receipt["operation_id"] not in foreign.text
        for token in (None, "invalid"):
            headers = {} if token is None else {"Authorization": "Bearer " + token}
            with httpx.Client(base_url=owner.endpoint, headers=headers, trust_env=False) as client:
                assert client.get("/v1/catalog").status_code == 401
                rejection = client.post("/v1/invoke", json=envelope())
                assert rejection.status_code == 401
                assert "operation_id" not in rejection.json()
        asyncio.run(mcp_privacy(owner, receipt["operation_id"]))
        for transport in ("rest", "mcp"):
            denied = read_result(owner, transport, receipt["operation_id"], principal="bob")
            assert denied["diagnostic"]["code"] == "access_denied"
            assert denied["correlation_id"]
            assert not {"receipt", "value", "operation_id"}.intersection(denied)
            assert receipt["operation_id"] not in json.dumps(denied)
            assert "café" not in json.dumps(denied, ensure_ascii=False)
        assert owner.observe().model_dump(exclude={"request_id"}) == before


async def mcp_privacy(owner: InstalledProcess, operation_id: str) -> None:
    async with mcp_client(
        owner, "bob", headers={"X-Principal": "alice", "X-AI-Origin": "true"}
    ) as bob:
        listed = await bob.list_tools()
        assert all(not tool.name.startswith("synthetic") for tool in listed.tools)
        assert "synthetic.write" not in listed.model_dump_json()
        result = await bob.call_tool("craftreport.inspect.v1", {"operation_id": operation_id})
        assert result.is_error and result.structured_content is not None
        assert result.structured_content["diagnostic"]["code"] == "access_denied"
        assert operation_id not in result.model_dump_json()
        with pytest.raises(MCPError):
            await bob.call_tool("synthetic.write.v1", envelope())
    for token in ("", "invalid"):
        async with mcp_client(owner, token=token) as stranger:
            with pytest.raises(MCPError, match="Authentication required"):
                await stranger.list_tools()
    async with mcp_client(owner) as alice:
        with pytest.raises(MCPError):
            await alice.call_tool("synthetic.unknown.v1", envelope())
