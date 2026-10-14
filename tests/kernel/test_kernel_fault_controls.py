"""Private fixture synchronization is bounded and rejects untyped requests."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "fixtures"))
from kernel_faults import ControlCommand, FaultControls  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def test_private_command_bounds() -> None:
    with pytest.raises(ValidationError):
        ControlCommand(command="race", request_id="id", participants=41)
    with pytest.raises(ValidationError):
        ControlCommand(command="wait_checkpoint", request_id="id", timeout=61.0)
    with pytest.raises(ValidationError):
        ControlCommand.model_validate({"command": "shutdown", "request_id": "id"})
    with pytest.raises(ValidationError):
        ControlCommand.model_validate({"command": "race", "request_id": "id", "extra": True})


@pytest.mark.anyio
async def test_initial_lookup_race_collects_twenty() -> None:
    from fixture_controls import Checkpoint

    controls = FaultControls()
    controls.race = Checkpoint(1)
    controls.race_participants = 20
    tasks = [asyncio.create_task(controls.initial_find()) for _ in range(19)]
    await asyncio.sleep(0)
    assert controls.race_arrivals == 19
    assert not any(task.done() for task in tasks)
    await controls.initial_find()
    await asyncio.gather(*tasks)
    assert controls.race_arrivals == 20


@pytest.mark.anyio
async def test_unfilled_lookup_barrier_times_out_without_waiter_leak() -> None:
    from fixture_controls import Checkpoint

    controls = FaultControls()
    controls.race = Checkpoint(0.01)
    controls.race_participants = 2
    with pytest.raises(TimeoutError):
        await controls.initial_find()
    assert controls.race.waiters == 0


def test_control_installs_and_releases_real_target_checkpoint(tmp_path: Path) -> None:
    from fixture_packaging import ROOT, build_fixture

    installed = build_fixture(tmp_path)
    code = """
import asyncio
import sys
from pathlib import Path
sys.path.extend(PATHS)
from kernel_faults import ControlCommand
from kernel_services import Providers

async def exercise():
    providers = Providers(Path.cwd(), None)
    await providers.controls.execute(providers, ControlCommand(
        command="checkpoint", request_id="configure", checkpoint="before_effect"))
    checkpoint = providers.target.before_effect
    assert checkpoint is not None, "Control must install a real target checkpoint"
    waiting = asyncio.create_task(checkpoint.wait())
    try:
        await providers.controls.execute(providers, ControlCommand(
            command="wait_checkpoint", request_id="wait", checkpoint="before_effect"))
        assert not waiting.done()
        await providers.controls.execute(providers, ControlCommand(
            command="release", request_id="release", checkpoint="before_effect"))
        await waiting
        assert checkpoint.waiters == 0
    finally:
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)

asyncio.run(exercise())
print("actual target checkpoint configured, reached and released")
""".replace("PATHS", repr([str(ROOT / "tests/fixtures"), str(ROOT / "tests/kernel")]))
    assert "actual target checkpoint" in installed.probe(code)
