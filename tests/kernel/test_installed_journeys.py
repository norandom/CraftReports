"""Installed bidirectional invocation and retry with independent target inspection."""

import pytest
from fixture_packaging import InstalledFixture
from installed_clients import discover, rest_client
from installed_journeys import envelope, invoke, read_result, record_case, rejected
from installed_process import InstalledProcess

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("first,second", [("rest", "mcp"), ("mcp", "rest")])
def test_installed_cross_transport_retry(
    installed_runtime: InstalledFixture, first: str, second: str
) -> None:
    with InstalledProcess(installed_runtime, "retry-" + first) as owner:
        record_case(
            owner,
            "Discovery, query immutability and retained equivalent retry",
            ["2.1", "3.1", "3.6", "4.1", "4.2", "5.3", "6.1", "6.2", "6.3"],
        )
        assert discover(owner).verification == "pending"
        before = owner.observe()
        receipt = invoke(owner, first, envelope())
        assert receipt["state"] == "complete" and receipt["evidence"]
        changed = owner.observe().model_dump(exclude={"request_id"})
        assert (changed["value"], changed["version"], changed["effect_count"]) == ("café ☃", "2", 1)
        assert before.effect_count == 0
        query = envelope(
            operation="synthetic.read",
            payload={"resource": "target-1"},
            retry_key=None,
            expected_versions=[],
        )
        read = invoke(owner, second, query)
        assert read["state"] == "complete"
        for result in (receipt, read):
            independent = owner.observe(result["result_ref"]).result
            assert independent == {"value": "café ☃", "version": "2"}
            for transport in (first, second):
                public = read_result(owner, transport, result["operation_id"])
                assert public == {"receipt": result, "value": independent}
                assert public["value"] == {"value": changed["value"], "version": changed["version"]}
        assert owner.observe().model_dump(exclude={"request_id"}) == changed
        retry = envelope(
            correlation_id="another-correlation",
            payload={"value": "café ☃", "resource": "target-1"},
        )
        assert invoke(owner, second, retry) == receipt
        with rest_client(owner) as client:
            assert client.get("/v1/operations/" + receipt["operation_id"]).json() == receipt
        for request in (
            envelope(payload={"resource": "target-1", "value": "different"}),
            envelope(
                expected_versions=[
                    {"resource": {"kind": "synthetic", "identity": "target-1"}, "version": "2"}
                ]
            ),
        ):
            rejected(invoke(owner, second, request), "retry_conflict")
        assert owner.observe().model_dump(exclude={"request_id"}) == changed
