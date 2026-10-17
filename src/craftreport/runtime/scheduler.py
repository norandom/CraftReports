"""Single-binding cadence, per-binding start fence and lifecycle controls."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from uuid import uuid4

from craftreport.application import ports
from craftreport.contracts import (
    EffectDisposition,
    ExpectedVersion,
    Principal,
    ResourceRef,
    StageResult,
    StageState,
)
from craftreport.data.values import SnapshotRef
from craftreport.runtime.bindings import BindingRuntime
from craftreport.runtime.publication import LatestRequest, LatestSelection
from craftreport.runtime.values import (
    BindingState,
    ControlRequest,
    EffectObservation,
    InspectRequest,
    PreparationIssue,
    PreparedRunInputs,
    RunPins,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _BindingSlot:
    principal: Principal
    fence: asyncio.Lock
    wake: asyncio.Event
    in_flight: bool = False
    task: asyncio.Task[None] | None = None


class BindingScheduler:
    def __init__(
        self,
        runtime: BindingRuntime,
        *,
        interval_seconds: float = 10.0,
        clock: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        self.runtime = runtime
        self.interval_seconds = interval_seconds
        self.clock = clock
        self.monotonic = monotonic
        self.sleep = sleep
        self._slots: dict[str, _BindingSlot] = {}
        self._closed = False

    def fence_for(self, binding_id: str, principal: Principal) -> _BindingSlot:
        slot = self._slots.get(binding_id)
        if slot is None:
            slot = _BindingSlot(principal, asyncio.Lock(), asyncio.Event())
            self._slots[binding_id] = slot
        else:
            slot.principal = principal
        return slot

    def notify(self, binding_id: str) -> None:
        slot = self._slots.get(binding_id)
        if slot is not None:
            slot.wake.set()

    async def control(
        self,
        principal: Principal,
        request: ControlRequest,
    ) -> BindingState | ports.Missing | ports.VersionConflict | ports.ServiceUnavailable:
        slot = self.fence_for(request.binding_id, principal)
        async with slot.fence:
            current = await self.runtime.store.inspect(
                principal, InspectRequest("binding", request.binding_id)
            )
            if not isinstance(current, BindingState):
                return (
                    current
                    if isinstance(current, (ports.Missing, ports.ServiceUnavailable))
                    else ports.ServiceUnavailable("binding_control")
                )
            res = ResourceRef("binding", request.binding_id)
            if current.generation != request.expected_generation:
                return ports.VersionConflict(
                    (ExpectedVersion(res, str(request.expected_generation)),),
                    (ExpectedVersion(res, str(current.generation)),),
                )
            if (
                request.action in ("start", "resume")
                and current.recovery_required
                and current.pending_operation_id is not None
            ):
                return ports.ServiceUnavailable("recovery_required")
            updated, pending_op = self._transition_control(current, request.action, slot.in_flight)
            saved = await self.runtime.store.save_binding(principal, current, updated)
            if not isinstance(saved, BindingState):
                return saved
            if request.action in ("start", "resume"):
                self.resume_recovered(request.binding_id, slot)
            elif request.action == "stop":
                self.cancel_loop(slot)
        if request.action == "stop" and pending_op is not None:
            await self.runtime.cancel_operation(principal, saved, pending_op)
            refreshed = await self.runtime.store.inspect(
                principal, InspectRequest("binding", request.binding_id)
            )
            if isinstance(refreshed, BindingState):
                return refreshed
        return saved

    def _transition_control(
        self, current: BindingState, action: str, in_flight: bool
    ) -> tuple[BindingState, str | None]:
        active = in_flight or current.pending_operation_id is not None
        if action in ("start", "resume"):
            return (
                replace(
                    current,
                    revision=current.revision + 1,
                    intent="running",
                    pause_pending=False,
                    recovery_required=False,
                ),
                None,
            )
        if action == "pause":
            return (
                replace(
                    current,
                    revision=current.revision + 1,
                    intent="paused",
                    pause_pending=active,
                ),
                None,
            )
        return (
            replace(
                current,
                generation=current.generation + 1,
                revision=current.revision + 1,
                intent="stopped",
                selected_run_id=None,
                pause_pending=False,
                recovery_required=False,
                pending_operation_id=None,
            ),
            current.pending_operation_id,
        )

    def resume_recovered(self, binding_id: str, slot: _BindingSlot) -> None:
        self._ensure_loop(binding_id, slot)
        slot.wake.set()

    def _ensure_loop(self, binding_id: str, slot: _BindingSlot) -> None:
        if self._closed:
            return
        if slot.task is None or slot.task.done():
            slot.task = asyncio.create_task(self._loop(binding_id, slot))

    def cancel_loop(self, slot: _BindingSlot) -> None:
        if slot.task is not None and not slot.task.done():
            slot.task.cancel()
        slot.task = None

    async def _wait_tick(self, slot: _BindingSlot, remaining: float) -> None:
        async def wait_wake() -> None:
            await slot.wake.wait()

        async def wait_sleep() -> None:
            await self.sleep(remaining)

        waiter = asyncio.create_task(wait_wake())
        sleeper = asyncio.create_task(wait_sleep())
        _, pending = await asyncio.wait({waiter, sleeper}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _loop(self, binding_id: str, slot: _BindingSlot) -> None:
        while not self._closed:
            slot.wake.clear()
            started = self.monotonic()
            keep_running = await self.step(slot.principal, binding_id)
            if not keep_running or self._closed:
                break
            elapsed = max(0.0, self.monotonic() - started)
            remaining = max(0.0, self.interval_seconds - elapsed)
            if remaining > 0 and not slot.wake.is_set():
                await self._wait_tick(slot, remaining)

    async def step(self, principal: Principal, binding_id: str) -> bool:
        slot = self.fence_for(binding_id, principal)
        if slot.in_flight:
            return True
        state = await self.runtime.store.inspect(principal, InspectRequest("binding", binding_id))
        if not isinstance(state, BindingState):
            return False
        if state.intent != "running" or state.recovery_required:
            return False
        slot.in_flight = True
        try:
            await self._execute_cycle(principal, slot, state)
        finally:
            slot.in_flight = False
        after = await self.runtime.store.inspect(principal, InspectRequest("binding", binding_id))
        return (
            isinstance(after, BindingState)
            and after.intent == "running"
            and not after.recovery_required
        )

    async def _execute_cycle(
        self, principal: Principal, slot: _BindingSlot, initial: BindingState
    ) -> None:
        selection = await self.runtime.queries(principal).latest(
            LatestRequest(initial.spec.feed_id, initial.spec.requirements)
        )
        if not isinstance(selection, LatestSelection):
            return
        if selection.highest_complete is None:
            await self.runtime.store.save_binding(
                principal,
                initial,
                replace(
                    initial,
                    revision=initial.revision + 1,
                    last_attempt_at=self.clock().isoformat(),
                    last_error="incomplete_binding",
                ),
            )
            return
        target_snap = selection.highest_complete
        if await self._already_selected(principal, initial, target_snap):
            if initial.latest_complete_snapshot != target_snap:
                await self.runtime.store.save_binding(
                    principal,
                    initial,
                    replace(
                        initial,
                        revision=initial.revision + 1,
                        latest_complete_snapshot=target_snap,
                    ),
                )
            return
        prepared = await self.runtime.preparer.prepare(initial.spec, target_snap)
        if not isinstance(prepared, PreparedRunInputs):
            code = (
                prepared.code
                if isinstance(prepared, PreparationIssue)
                else "preparation_unavailable"
            )
            current = await self.runtime.store.inspect(
                principal, InspectRequest("binding", initial.spec.binding_id)
            )
            if isinstance(current, BindingState) and current.generation == initial.generation:
                await self.runtime.store.save_binding(
                    principal,
                    current,
                    replace(
                        current,
                        revision=current.revision + 1,
                        last_attempt_at=self.clock().isoformat(),
                        last_error=code,
                        latest_complete_snapshot=target_snap,
                    ),
                )
            return
        if not self._matches_spec(initial, target_snap, prepared):
            await self.runtime.store.save_binding(
                principal,
                initial,
                replace(
                    initial,
                    revision=initial.revision + 1,
                    last_attempt_at=self.clock().isoformat(),
                    last_error="preparation_mismatch",
                    latest_complete_snapshot=target_snap,
                ),
            )
            return
        await self._start_and_observe(principal, slot, initial, target_snap, prepared)

    async def _already_selected(
        self, principal: Principal, state: BindingState, snapshot: SnapshotRef
    ) -> bool:
        if state.applied_snapshot == snapshot and state.pending_operation_id is None:
            return True
        if state.selected_run_id is None:
            return False
        run = await self.runtime.store.inspect(
            principal, InspectRequest("run", state.selected_run_id)
        )
        return (
            isinstance(run, RunPins)
            and run.binding_generation == state.generation
            and run.snapshot == snapshot
            and (state.applied_run_id == run.run_id or state.pending_operation_id is not None)
        )

    def _matches_spec(
        self, state: BindingState, snapshot: SnapshotRef, prepared: PreparedRunInputs
    ) -> bool:
        shared = (
            "definition",
            "template",
            "theme",
            "pack",
            "resolved_parameters",
            "parameter_digest",
            "validation_scope",
        )
        return prepared.snapshot == snapshot and all(
            getattr(prepared, name) == getattr(state.spec, name) for name in shared
        )

    async def _start_and_observe(
        self,
        principal: Principal,
        slot: _BindingSlot,
        initial: BindingState,
        snapshot: SnapshotRef,
        prepared: PreparedRunInputs,
    ) -> None:
        async with slot.fence:
            current = await self.runtime.store.inspect(
                principal, InspectRequest("binding", initial.spec.binding_id)
            )
            if (
                not isinstance(current, BindingState)
                or current.generation != initial.generation
                or current.intent != "running"
                or current.pause_pending
                or current.recovery_required
            ):
                return
            values = {f.name: getattr(prepared, f.name) for f in fields(prepared)}
            pins = RunPins(
                run_id=uuid4().hex,
                binding_id=current.spec.binding_id,
                binding_generation=current.generation,
                target=current.spec.target,
                **values,
            )
            attempt_iso = self.clock().isoformat()
            selected = await self.runtime.store.select_run(
                principal,
                current,
                pins,
                attempt_at=attempt_iso,
                latest_complete=snapshot,
            )
            if not isinstance(selected, RunPins):
                return
            after_select = await self.runtime.store.inspect(
                principal, InspectRequest("binding", current.spec.binding_id)
            )
            if not isinstance(after_select, BindingState) or self.runtime.app is None:
                return
            try:
                started = await self.runtime.app.start(selected)
            except Exception:
                await self._record_ambiguous_start(principal, after_select, selected)
                return
            if isinstance(started, ports.ServiceUnavailable):
                await self._record_failed_start(principal, after_select, selected, started.service)
                return
            await self.runtime.store.save_binding(
                principal,
                after_select,
                replace(
                    after_select,
                    revision=after_select.revision + 1,
                    pending_operation_id=started,
                ),
            )
        await self._inspect_started(principal, initial.spec.binding_id, selected, started)

    async def _record_ambiguous_start(
        self, principal: Principal, state: BindingState, run: RunPins
    ) -> None:
        obs = EffectObservation(
            run.run_id,
            run.target,
            run.binding_generation,
            EffectDisposition.UNKNOWN,
            (StageResult("app_start", StageState.FAILED, "start_exception", ()),),
            (),
            False,
        )
        await self.runtime.store.observe_effect(principal, state, obs)

    async def _record_failed_start(
        self, principal: Principal, state: BindingState, run: RunPins, reason: str
    ) -> None:
        obs = EffectObservation(
            run.run_id,
            run.target,
            run.binding_generation,
            EffectDisposition.NONE,
            (StageResult("app_start", StageState.FAILED, reason, ()),),
            (),
            False,
        )
        await self.runtime.store.observe_effect(principal, state, obs)

    async def _inspect_started(
        self, principal: Principal, binding_id: str, run: RunPins, operation_id: str
    ) -> None:
        observed = await self.runtime.app.inspect(operation_id) if self.runtime.app else None
        current = await self.runtime.store.inspect(principal, InspectRequest("binding", binding_id))
        if not isinstance(current, BindingState):
            return
        if isinstance(observed, EffectObservation):
            verified = await self.runtime.verify_observation(observed)
            await self.runtime.store.observe_effect(
                principal,
                current,
                verified,
                completed_at=self.clock().isoformat() if verified.verified_complete else None,
            )
            return
        obs = EffectObservation(
            run.run_id,
            run.target,
            run.binding_generation,
            EffectDisposition.UNKNOWN,
            (StageResult("app_inspect", StageState.FAILED, "inspect_unavailable", ()),),
            (),
            False,
        )
        await self.runtime.store.observe_effect(principal, current, obs)

    async def aclose(self) -> None:
        self._closed = True
        tasks = [
            slot.task
            for slot in self._slots.values()
            if slot.task is not None and not slot.task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for binding_id, slot in list(self._slots.items()):
            current = await self.runtime.store.inspect(
                slot.principal, InspectRequest("binding", binding_id)
            )
            if (
                isinstance(current, BindingState)
                and current.pending_operation_id is not None
                and current.selected_run_id is not None
            ):
                obs = EffectObservation(
                    current.selected_run_id,
                    current.spec.target,
                    current.generation,
                    EffectDisposition.UNKNOWN,
                    (StageResult("shutdown", StageState.FAILED, "host_shutdown", ()),),
                    (),
                    False,
                )
                await self.runtime.store.observe_effect(slot.principal, current, obs)
        self._slots.clear()
        return None
