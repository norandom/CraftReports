"""Installed disposable defects must fail the same oracle restored wiring passes."""

import pytest
from fixture_packaging import InstalledFixture
from installed_journeys import envelope, invoke, record_case
from installed_process import InstalledProcess
from installed_sensitivity import EFFECT_ASSERTION, QUERY_ASSERTION, run_assertion

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize(
    "variant,check,marker",
    [
        ("disconnected", "effect", EFFECT_ASSERTION),
        ("mutating-query", "query", QUERY_ASSERTION),
    ],
)
def test_installed_disproof_and_restoration(
    installed_runtime: InstalledFixture,
    transport: str,
    variant: str,
    check: str,
    marker: str,
) -> None:
    for selected in (variant, "normal"):
        name = f"sensitivity-{transport}-{variant}-{selected}"
        with InstalledProcess(installed_runtime, name, sensitivity_variant=selected) as owner:
            record_case(
                owner,
                f"{selected} {check} sensitivity through {transport}",
                ["2.5", "3.6", "7.1", "7.2", "7.3"],
            )
            before = owner.observe().model_dump()
            request = (
                envelope()
                if check == "effect"
                else envelope(
                    operation="synthetic.read",
                    payload={"resource": "target-1"},
                    retry_key=None,
                    expected_versions=[],
                )
            )
            response = invoke(owner, transport, request)
            assert "operation_id" in response
            after = owner.observe().model_dump()
            result = run_assertion(
                installed_runtime.python,
                owner.directory,
                {
                    "variant": selected,
                    "transport": transport,
                    "check": check,
                    "before": before,
                    "after": after,
                    "response": response,
                },
            )
            if selected == "normal":
                assert result["exit_code"] == 0, result["stderr"]
                assert result["status"] == "passed"
                assert response["state"] == "complete"
            else:
                assert result["exit_code"] == 1, result
                assert result["status"] == "failed"
                assert result["stderr"].rstrip().endswith("AssertionError: " + marker)
        assert owner.cleanup["status"] == "passed"
        assert owner.process is not None and owner.process.poll() == 0
