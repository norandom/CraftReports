"""Required guarantees fail closed and post-effect uncertainty never replays."""

import pytest
from fixture_packaging import InstalledFixture
from installed_clients import discover
from installed_failures import inspect
from installed_journeys import envelope, invoke, read_result, record_case, rejected
from installed_process import InstalledProcess

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize(
    "service",
    ["access", "journal", "resources", "effects", "guard", "evidence", "capabilities", "results"],
)
def test_unavailable_guarantee_before_effect(
    installed_runtime: InstalledFixture, transport: str, service: str
) -> None:
    with InstalledProcess(installed_runtime, f"unavailable-{service}-{transport}") as owner:
        discover(owner)
        record_case(
            owner,
            "Unavailable required guarantee rejects before admission and target effect",
            ["3.4", "7.2"],
        )
        owner.set_availability(service, False, health_only=True)
        rejected(invoke(owner, transport, envelope()), "service_unavailable")
        observed = owner.observe()
        assert observed.effect_count == 0 and observed.version == "1" and not observed.admissions
        owner.set_availability(service, True, health_only=True)
        assert invoke(owner, transport, envelope())["state"] == "complete"
        assert owner.observe().effect_count == 1


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_selected_target_mode_is_required(
    installed_runtime: InstalledFixture, transport: str
) -> None:
    with InstalledProcess(
        installed_runtime, "unsupported-target-" + transport, capability_probe=True
    ) as owner:
        discover(owner)
        record_case(
            owner,
            "Selected native target requirement rejects unsupported mode before effect",
            ["3.3", "7.2"],
        )
        owner.control_request("unsupported", enabled=True)
        rejected(invoke(owner, transport, envelope()), "unsupported_capability")
        assert owner.observe().effect_count == 0 and not owner.observe().admissions
        owner.control_request("unsupported", enabled=False)
        assert invoke(owner, transport, envelope())["state"] == "complete"
        assert owner.observe().effect_count == 1


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize(
    "fault,state",
    [
        ("skip_evidence", "partial"),
        ("evidence_after_effect", "partial"),
        ("interrupt_after_effect", "ambiguous"),
    ],
)
def test_post_effect_uncertainty_never_replays(
    installed_runtime: InstalledFixture, transport: str, fault: str, state: str
) -> None:
    with InstalledProcess(installed_runtime, f"uncertain-{fault}-{transport}") as owner:
        discover(owner)
        record_case(
            owner,
            "One mutation with incomplete evidence or unknown outcome; retry retains identity",
            ["4.5", "5.1", "5.4", "5.5", "7.2"],
        )
        owner.configure_fault(fault)
        receipt = invoke(owner, transport, envelope())
        assert receipt["state"] == state
        expected_code = {
            "skip_evidence": "evidence_missing",
            "evidence_after_effect": "evidence_unavailable",
            "interrupt_after_effect": "effect_unknown",
        }[fault]
        assert any(
            item["code"] == expected_code and item["stage"] == "effect"
            for item in receipt["diagnostics"]
        )
        assert receipt["stages"]
        observed = owner.observe()
        assert (observed.value, observed.version, observed.effect_count) == ("café ☃", "2", 1)
        if fault == "evidence_after_effect":
            owner.set_availability("evidence", True)
        for current in ("rest", "mcp"):
            inspected = inspect(owner, current, receipt["operation_id"])
            retried = invoke(owner, current, envelope())
            if fault == "skip_evidence":
                assert inspected["diagnostic"]["code"] == "evidence_missing"
                assert retried["diagnostic"]["code"] == "evidence_missing"
            else:
                assert inspected["state"] == state
                assert retried["operation_id"] == receipt["operation_id"]
            retained = owner.observe()
            assert retained.effect_count == 1
            assert retained.receipts[0]["operation_id"] == receipt["operation_id"]
            assert retained.receipts[0]["state"] == state


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_post_effect_journal_outage_retains_pending_identity(
    installed_runtime: InstalledFixture, transport: str
) -> None:
    with InstalledProcess(installed_runtime, "journal-after-" + transport) as owner:
        discover(owner)
        record_case(
            owner,
            "Journal outage after mutation with restoration of the same temporary journal",
            ["4.1", "5.5", "7.2", "7.4"],
        )
        owner.configure_fault("journal_after_effect")
        rejected(invoke(owner, transport, envelope()), "service_unavailable")
        observed = owner.observe()
        assert observed.effect_count == 1 and observed.version == "2"
        assert len(observed.admissions) == 1
        operation_id = str(observed.admissions[0]["operation_id"])
        owner.set_availability("journal", True)
        for current in ("rest", "mcp"):
            retained = inspect(owner, current, operation_id)
            assert retained["state"] == "pending"
            assert invoke(owner, current, envelope()) == retained
        assert owner.observe().effect_count == 1


@pytest.mark.parametrize("service", ["evidence", "results"])
def test_retained_content_outage_after_complete(
    installed_runtime: InstalledFixture, service: str
) -> None:
    with InstalledProcess(installed_runtime, "retained-outage-" + service) as owner:
        discover(owner)
        record_case(
            owner,
            "Unavailable retained content cannot manufacture successful readback",
            ["5.5", "4.1"],
        )
        receipt = invoke(owner, "rest", envelope())
        assert receipt["state"] == "complete"
        owner.set_availability(service, False)
        expected = "evidence_unavailable" if service == "evidence" else "result_unavailable"
        for transport in ("rest", "mcp"):
            assert (
                inspect(owner, transport, receipt["operation_id"])["diagnostic"]["code"] == expected
            )
            assert (
                read_result(owner, transport, receipt["operation_id"])["diagnostic"]["code"]
                == expected
            )
            rejected(invoke(owner, transport, envelope()), "service_unavailable")
            assert owner.observe().effect_count == 1
        owner.set_availability(service, True)
        assert invoke(owner, "mcp", envelope()) == receipt
        assert owner.observe().effect_count == 1
