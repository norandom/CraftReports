"""Private, bounded controls for the installed synthetic deployment only."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Literal

from fixture_controls import Checkpoint
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from kernel_services import Providers


class ControlCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    command: Literal[
        "observe",
        "checkpoint",
        "wait_checkpoint",
        "release",
        "availability",
        "fault",
        "race",
        "unsupported",
    ]
    request_id: str = Field(min_length=1, max_length=64)
    result_ref: str | None = Field(default=None, max_length=128)
    checkpoint: Literal["before_effect", "after_effect", "initial_find"] = "before_effect"
    timeout: float = Field(default=40.0, ge=0.1, le=60)
    participants: int = Field(default=1, ge=1, le=40)
    service: Literal[
        "access", "journal", "resources", "effects", "guard", "evidence", "capabilities", "results"
    ] = "journal"
    available: bool = True
    health_only: bool = False
    fault: Literal[
        "skip_evidence", "evidence_after_effect", "journal_after_effect", "interrupt_after_effect"
    ] = "skip_evidence"
    enabled: bool = True


class FaultControls:
    def __init__(self) -> None:
        self.checkpoints: dict[str, Checkpoint] = {}
        self.health: dict[str, bool] = {}
        self.faults: set[str] = set()
        self.race: Checkpoint | None = None
        self.race_participants = 0
        self.race_arrivals = 0

    async def initial_find(self) -> None:
        if self.race is None or self.race_arrivals >= self.race_participants:
            return
        self.race_arrivals += 1
        if self.race_arrivals == self.race_participants:
            self.race.release()
        await self.race.wait()

    async def execute(self, providers: Providers, request: ControlCommand) -> dict[str, object]:
        command = request.command
        if command == "observe":
            return await providers.observe(request.result_ref)
        if command == "checkpoint":
            checkpoint = Checkpoint(request.timeout)
            self.checkpoints[request.checkpoint] = checkpoint
            setattr(providers.target, request.checkpoint, checkpoint)
        elif command == "wait_checkpoint":
            checkpoint = self.checkpoints[request.checkpoint]
            async with asyncio.timeout(request.timeout):
                await checkpoint.reached.wait()
                while checkpoint.waiters < request.participants:
                    await asyncio.sleep(0.005)
        elif command == "release":
            self.checkpoints[request.checkpoint].release()
        elif command == "race":
            self.race = Checkpoint(request.timeout)
            self.race_participants = request.participants
            self.race_arrivals = 0
            self.checkpoints["initial_find"] = self.race
        else:
            self.configure(providers, request)
        return {
            "ok": True,
            "admissions": providers.journal.admission_proofs(),
            "race_arrivals": self.race_arrivals,
        }

    def configure(self, providers: Providers, request: ControlCommand) -> None:
        if request.command == "fault":
            if request.enabled:
                self.faults.add(request.fault)
            else:
                self.faults.discard(request.fault)
            if request.fault == "interrupt_after_effect":
                providers.target.interrupt_after_effect = request.enabled
        elif request.command == "availability":
            if request.health_only:
                self.health[request.service] = request.available
            else:
                provider = {
                    "access": providers.access,
                    "journal": providers.journal,
                    "resources": providers.target,
                    "effects": providers.target,
                    "guard": providers.target,
                    "evidence": providers.evidence,
                    "capabilities": providers.capabilities,
                    "results": providers.results,
                }[request.service]
                provider.available = request.available
        elif request.command == "unsupported":
            for resource in providers.capabilities.resource_modes:
                providers.capabilities.resource_modes[resource] = (
                    "browser" if request.enabled else "native"
                )
