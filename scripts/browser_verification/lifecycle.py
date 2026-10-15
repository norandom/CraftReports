"""Exact public SDK ownership; no native browser-process inference."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID, uuid4

from playwright.async_api import Browser, BrowserContext, Playwright

from .contracts import SDK_IDENTITY, SDK_LIMITATION, CleanupFinding, CloseState, ResourceKind

SDKKind = Literal["driver", "browser", "context", "decode-context"]
Handle = Playwright | Browser | BrowserContext


class Token(Protocol):
    @property
    def token_id(self) -> UUID: ...
    @property
    def acquisition_id(self) -> UUID | None: ...


class Registry(Protocol):
    @property
    def run_id(self) -> UUID: ...
    def register(self, kind: ResourceKind, identity: str) -> Token: ...
    def mark_acquired(self, token_id: UUID) -> object: ...
    def record_finding(self, finding: CleanupFinding) -> None: ...
    def begin_close(self, token_id: UUID, close_id: UUID) -> None: ...
    def update_video(self, token_id: UUID, state: Literal["unfinished", "finalized"]) -> None: ...
    @property
    def findings(self) -> tuple[CleanupFinding, ...]: ...
    @property
    def cancel_requested(self) -> bool: ...
    def request_cancel(self) -> None: ...


async def protected[T](operation: Awaitable[T], on_cancel: Callable[[], None] | None = None) -> T:
    """A single retained finalizer survives repeated caller cancellation."""
    task = asyncio.ensure_future(operation)
    while True:
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if on_cancel:
                on_cancel()
            if task.cancelled():
                raise


@dataclass
class Acquisition:
    kind: SDKKind
    identity: str
    token: UUID
    acquisition_id: UUID
    task: asyncio.Future[Handle]
    close_task: asyncio.Future[None] | None = None
    close_id: UUID | None = None
    finding: CleanupFinding | None = None


def task_state[T](
    task: asyncio.Future[T] | None,
) -> Literal["not-started", "pending", "succeeded", "failed", "cancelled"]:
    if task is None:
        return "not-started"
    if not task.done():
        return "pending"
    return "cancelled" if task.cancelled() else "failed" if task.exception() else "succeeded"


class SDKResources:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.entries: list[Acquisition] = []
        self.unexpected_disconnect = False
        self.expected_disconnect = False

    async def acquire(self, kind: SDKKind, identity: str, operation: Awaitable[Handle]) -> Handle:
        token = self.registry.register(kind, identity)
        assert token.acquisition_id
        entry = Acquisition(
            kind, identity, token.token_id, token.acquisition_id, asyncio.ensure_future(operation)
        )
        self.entries.append(entry)
        if self.registry.cancel_requested and kind != "decode-context":
            raise asyncio.CancelledError
        handle = await asyncio.shield(entry.task)
        self.registry.mark_acquired(entry.token)
        if isinstance(handle, Browser):
            handle.on("disconnected", self.disconnected)
        return handle

    def disconnected(self, _: Browser) -> None:
        if not self.expected_disconnect:
            self.unexpected_disconnect = True

    async def close_one(self, entry: Acquisition, deadline: float) -> CleanupFinding:
        if entry.finding:
            return entry.finding
        started, close_id = time.monotonic(), uuid4()
        entry.close_id = close_id
        self.registry.begin_close(entry.token, close_id)
        status: CloseState = "sdk-closed"
        acquired: Literal["acquired", "failed", "unsettled"] = "unsettled"
        try:
            await self.settle(entry.task, deadline)
            handle = entry.task.result()
            valid = (
                (entry.kind == "driver" and isinstance(handle, Playwright))
                or (entry.kind == "browser" and isinstance(handle, Browser))
                or (
                    entry.kind in ("context", "decode-context")
                    and isinstance(handle, BrowserContext)
                )
            )
            if not valid:
                raise ValueError("sdk-handle-kind-mismatch")
            acquired = "acquired"
            self.registry.mark_acquired(entry.token)
            if entry.kind == "browser":
                if not isinstance(handle, Browser) or not handle.is_connected():
                    self.unexpected_disconnect = True
                self.expected_disconnect = True
            operation = handle.stop() if isinstance(handle, Playwright) else handle.close()
            entry.close_task = asyncio.ensure_future(operation)
            await self.settle(entry.close_task, deadline)
            entry.close_task.result()
        except TimeoutError:
            status = "timed-out"
        except (Exception, asyncio.CancelledError):
            status = "failed"
            if acquired != "acquired":
                acquired = "failed"
        entry.finding = CleanupFinding(
            resource_id=entry.token,
            owner_run=self.registry.run_id,
            identity=entry.identity,
            resource_kind=entry.kind,
            status=status,
            acquisition_id=entry.acquisition_id,
            close_id=close_id,
            mechanism="public-close",
            started=started,
            deadline=deadline,
            finished=time.monotonic(),
            acquisition_state=acquired,
            acquisition_task_state=task_state(entry.task),
            close_task_state=task_state(entry.close_task),
            unexpected_disconnect=self.unexpected_disconnect,
            sdk_identity=SDK_IDENTITY,
            declared_limitations=(SDK_LIMITATION,),
            final_video_state="not-required",
        )
        self.registry.record_finding(entry.finding)
        return entry.finding

    async def settle[T](self, task: asyncio.Future[T], deadline: float) -> None:
        done, _ = await asyncio.wait((task,), timeout=max(0, deadline - time.monotonic()))
        if not done:
            raise TimeoutError("owned-operation-unsettled")

    async def close_all(self, bound: float, *, deadline: float | None = None) -> None:
        deadline = deadline if deadline is not None else time.monotonic() + bound
        for kind in ("context", "decode-context", "browser", "driver"):
            for entry in self.entries:
                if entry.kind == kind:
                    await self.close_one(entry, deadline)
