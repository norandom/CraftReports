"""Bounded local ownership and explicitly temporary restart epochs over sockets."""

import time

import pytest
from fixture_packaging import InstalledFixture
from installed_clients import discover, rest_client
from installed_failures import inspect, terminal
from installed_journeys import envelope, invoke, record_case, rejected
from installed_process import ChildCleanup, InstalledProcess

pytestmark = pytest.mark.integration


def test_capacity_rejects_new_key_but_retained_identity_is_inspectable(
    installed_runtime: InstalledFixture,
) -> None:
    with InstalledProcess(
        installed_runtime, "capacity-one", concurrent_operations=1, response_seconds=0.2
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Full capacity permits retained retry/inspection; rejected key is not journaled",
            ["4.1", "5.1", "7.2"],
        )
        owner.configure_checkpoint("before_effect")
        pending = invoke(owner, "rest", envelope())
        owner.wait_checkpoint("before_effect")
        rejected(invoke(owner, "mcp", envelope(retry_key="capacity-rejected")), "capacity")
        assert invoke(owner, "mcp", envelope()) == pending
        assert inspect(owner, "rest", pending["operation_id"]) == pending
        assert len(owner.observe().admissions) == 1 and owner.observe().effect_count == 0
        owner.release_checkpoint("before_effect")
        assert terminal(owner, "mcp", pending["operation_id"])["state"] == "complete"
        request = envelope(
            retry_key="capacity-rejected",
            expected_versions=[
                {"resource": {"kind": "synthetic", "identity": "target-1"}, "version": "2"}
            ],
        )
        assert invoke(owner, "rest", request)["state"] == "complete"
        assert owner.observe().effect_count == 2


@pytest.mark.parametrize("checkpoint,effects", [("before_effect", 0), ("after_effect", 1)])
def test_bounded_shutdown_records_interrupted_operation(
    installed_runtime: InstalledFixture, checkpoint: str, effects: int
) -> None:
    with InstalledProcess(
        installed_runtime, "shutdown-" + checkpoint, response_seconds=0.2, shutdown_seconds=0.6
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Bounded shutdown records ambiguous interruption in final cleanup observation",
            ["4.5", "5.1", "7.2", "7.4"],
        )
        owner.configure_checkpoint(checkpoint)
        pending = invoke(owner, "rest", envelope())
        owner.wait_checkpoint(checkpoint)
        assert owner.observe().effect_count == effects
        started = time.monotonic()
        owner.close()
        assert time.monotonic() - started < 8
        assert owner.cleanup["status"] == "passed" and not owner.cleanup["forced_termination"]
        assert owner.process is not None and owner.process.poll() == 0
        final = ChildCleanup.model_validate(owner.cleanup["providers"])
        assert final.effect_count == effects
        assert final.receipts[0]["operation_id"] == pending["operation_id"]
        assert final.receipts[0]["state"] == "ambiguous"
        assert final.final_target["version"] == str(1 + effects)


def test_new_process_has_new_epoch_and_no_durable_retry_claim(
    installed_runtime: InstalledFixture,
) -> None:
    with InstalledProcess(installed_runtime, "epoch-original") as first:
        discover(first)
        record_case(
            first, "Temporary journal and target are scoped to an installed process epoch", ["7.4"]
        )
        receipt = invoke(first, "rest", envelope())
        original_epoch = first.observe().epoch
        assert receipt["state"] == "complete"
    with InstalledProcess(installed_runtime, "epoch-restarted") as second:
        catalog = discover(second)
        assert catalog.verification == "pending"
        record_case(
            second,
            "New epoch has absent prior temporary state; this is not restart durability",
            ["7.4"],
        )
        observed = second.observe()
        assert observed.epoch != original_epoch and observed.effect_count == 0
        assert observed.value == "before" and observed.version == "1"
        with rest_client(second) as client:
            response = client.get("/v1/operations/" + receipt["operation_id"])
            assert response.status_code == 404
            assert "operation_id" not in response.json()
        new = invoke(second, "mcp", envelope())
        assert new["operation_id"] != receipt["operation_id"]
        assert second.observe().effect_count == 1
