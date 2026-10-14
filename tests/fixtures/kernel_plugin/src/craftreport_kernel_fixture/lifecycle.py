"""Purpose-specific test lifecycle instrumentation, with one owned closer."""

from dataclasses import dataclass
from typing import Protocol


class LifecycleObserver(Protocol):
    def record(self, capability: str, event: str) -> None: ...


@dataclass(frozen=True, slots=True)
class FixtureServices:
    lifecycle: LifecycleObserver


class ResourceScope:
    def __init__(self, identity: str, services: FixtureServices, fail_close: bool) -> None:
        self.identity = identity
        self.services = services
        self.fail_close = fail_close
        self.closed = False
        self.services.lifecycle.record(identity, "acquired")

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.services.lifecycle.record(self.identity, "released")
        if self.fail_close:
            self.services.lifecycle.record(self.identity, "close_failed")
            raise RuntimeError("Synthetic cleanup failure after release")
