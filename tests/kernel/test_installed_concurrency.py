"""Admission remains owned after real clients stop receiving responses."""

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from fixture_packaging import InstalledFixture
from installed_clients import discover
from installed_failures import admission_id, disconnect_mcp, disconnect_rest, inspect, terminal
from installed_journeys import envelope, invoke, read_result, record_case, rejected
from installed_process import InstalledProcess

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_disconnect_after_proven_admission(
    installed_runtime: InstalledFixture, transport: str
) -> None:
    with InstalledProcess(
        installed_runtime, "disconnect-" + transport, response_seconds=10
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Client disconnect after atomic admission; new client resolves retained operation",
            ["4.1", "5.1", "6.5", "7.4"],
        )
        owner.configure_checkpoint("before_effect")
        operation_id = (
            disconnect_rest(owner) if transport == "rest" else asyncio.run(disconnect_mcp(owner))
        )
        assert owner.observe().effect_count == 0
        other = "mcp" if transport == "rest" else "rest"
        pending = inspect(owner, other, operation_id)
        assert pending["state"] == "pending"
        assert invoke(owner, other, envelope())["operation_id"] == operation_id
        assert owner.observe().effect_count == 0
        owner.release_checkpoint("before_effect")
        completed = terminal(owner, other, operation_id)
        assert completed["state"] == "complete"
        assert invoke(owner, transport, envelope()) == completed
        observed = owner.observe()
        assert (observed.value, observed.version, observed.effect_count) == ("café ☃", "2", 1)
        assert read_result(owner, other, operation_id)["value"] == {
            "value": observed.value,
            "version": observed.version,
        }


def test_twenty_equivalent_socket_commands(installed_runtime: InstalledFixture) -> None:
    with InstalledProcess(
        installed_runtime,
        "twenty-concurrent",
        concurrent_operations=24,
        response_seconds=30,
        guard_timeout=40,
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Twenty initial absent lookups race through real clients to one admission",
            ["4.1", "4.3", "7.2"],
        )
        owner.configure_race(participants=20)
        with ThreadPoolExecutor(max_workers=20) as clients:
            futures = [
                clients.submit(
                    invoke,
                    owner,
                    "rest" if index % 2 else "mcp",
                    envelope(correlation_id=f"racer-{index}"),
                )
                for index in range(20)
            ]
            receipts = [future.result(timeout=45) for future in futures]
        assert len({receipt["operation_id"] for receipt in receipts}) == 1
        operation_id = receipts[0]["operation_id"]
        assert terminal(owner, "rest", operation_id)["state"] == "complete"
        observed = owner.observe()
        assert observed.effect_count == 1 and observed.version == "2"
        assert observed.value == "café ☃"
        assert len(observed.admissions) == 1
        assert owner.control_request("release", checkpoint="initial_find").race_arrivals == 20


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_conflicts_while_winner_holds_lease(
    installed_runtime: InstalledFixture, transport: str
) -> None:
    with InstalledProcess(
        installed_runtime, "held-conflict-" + transport, response_seconds=0.2
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Held winner rejects changed content/preconditions; new stale key rejected",
            ["4.2", "4.4", "7.2"],
        )
        owner.configure_checkpoint("before_effect")
        pending = invoke(owner, transport, envelope())
        proof = owner.wait_checkpoint("before_effect")
        assert admission_id(proof.admissions, owner) == pending["operation_id"]
        changesets: list[dict[str, object]] = [
            {"payload": {"resource": "target-1", "value": "different"}},
            {"expected_versions": []},
        ]
        for changes in changesets:
            rejected(invoke(owner, transport, envelope(**changes)), "retry_conflict")
        assert owner.observe().effect_count == 0
        owner.release_checkpoint("before_effect")
        assert terminal(owner, transport, pending["operation_id"])["state"] == "complete"
        rejected(
            invoke(owner, transport, envelope(retry_key="fresh-stale-key")), "version_conflict"
        )
        observed = owner.observe()
        assert observed.effect_count == 1 and len(observed.admissions) == 1
