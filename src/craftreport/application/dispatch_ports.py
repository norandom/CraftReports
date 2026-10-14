"""Fixed dispatcher boundaries; no handler receives health or result writers."""

from dataclasses import dataclass
from typing import Protocol

from craftreport.application.service_values import ServiceUnavailable
from craftreport.contracts import (
    Availability,
    InvocationEnvelope,
    JsonObject,
    OperationLimits,
    Principal,
)
from craftreport.contracts.values import freeze_object, require_enum, require_text


class WireFailure(ValueError):
    """Conversion failure fields still require dispatcher disclosure filtering."""

    def __init__(
        self, code: str, *, location: tuple[str | int, ...] = (), limit: str | None = None
    ) -> None:
        self.code = code
        self.location = location
        self.limit = limit
        super().__init__(code)


class InvocationLimits(Protocol):
    def check(self, request: InvocationEnvelope, limits: OperationLimits) -> None: ...

    def check_result(self, value: JsonObject, limits: OperationLimits) -> None: ...


class ServiceHealth(Protocol):
    """Probe operator-allowlisted providers now; absent names fail closed.

    Names select configured health probes only, never imports or container lookups.
    Success is an actual current provider observation, not static object presence.
    """

    async def check(self, required: tuple[str, ...]) -> ServiceUnavailable | None: ...


@dataclass(frozen=True, slots=True)
class RetainedResult:
    reference: str
    availability: Availability
    value: JsonObject | None = None

    def __post_init__(self) -> None:
        require_text(self.reference, "result reference")
        require_enum(self.availability, Availability)
        if (self.availability is Availability.AVAILABLE) != (self.value is not None):
            raise ValueError("Available result requires retained content")
        if self.value is not None:
            object.__setattr__(self, "value", freeze_object(self.value))


class ResultStore(Protocol):
    """Opaque references bound to operation and trusted principal/deployment.

    Write does not prove retention: dispatcher reads back exact immutable content.
    Read distinguishes missing, inaccessible and unavailable without regenerating.
    Provider failures may raise ServiceUnavailableError. No durability is implied.
    """

    async def write(self, principal: Principal, operation_id: str, value: JsonObject) -> str: ...

    async def read(
        self, principal: Principal, operation_id: str, reference: str
    ) -> RetainedResult: ...
