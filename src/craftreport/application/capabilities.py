"""Typed capability author boundary; activation policy lives elsewhere."""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol

from craftreport.application.registry import BoundOperation
from craftreport.contracts import CapabilityManifest


@dataclass(frozen=True, slots=True)
class CapabilityInstance:
    """Bindings and one idempotent closer also owned by open's context manager.

    Explicit close followed by context exit releases once. Cleanup failures
    propagate; instances do not decide activation readiness.
    """

    bindings: tuple[BoundOperation, ...]
    aclose: Callable[[], Awaitable[None]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", tuple(self.bindings))


class CapabilityFactory[Services, Settings](Protocol):
    """A declared service bundle and validated settings, never a global container."""

    def describe(self) -> CapabilityManifest: ...

    def open(
        self, services: Services, settings: Settings
    ) -> AbstractAsyncContextManager[CapabilityInstance]: ...
