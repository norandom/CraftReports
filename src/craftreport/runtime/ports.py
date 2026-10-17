"""Injected exact publication decisions and principal-scoped queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from craftreport.application.service_values import Missing, ServiceUnavailable
from craftreport.data.ports import SnapshotReader

if TYPE_CHECKING:
    from craftreport.application.ports import VersionConflict
    from craftreport.contracts import Principal
    from craftreport.data.values import SnapshotRef
    from craftreport.runtime.publication import LatestRequest, LatestSelection, PublicationDecision
    from craftreport.runtime.values import (
        BindingSpec,
        BindingState,
        CancellationObservation,
        EffectObservation,
        InspectRequest,
        PreparationIssue,
        PreparedRunInputs,
        RunPins,
    )


class PublicationDecisionReader(Protocol):
    async def read_decision(
        self, operation_id: str
    ) -> PublicationDecision | Missing | ServiceUnavailable: ...


class SnapshotQueries(SnapshotReader, Protocol):
    async def latest(
        self, request: LatestRequest
    ) -> LatestSelection | Missing | ServiceUnavailable: ...


class RuntimeStore(Protocol):
    async def inspect(
        self, principal: Principal, request: InspectRequest
    ) -> BindingState | RunPins | Missing | ServiceUnavailable: ...

    async def select_run(
        self, principal: Principal, expected: BindingState, pins: RunPins
    ) -> RunPins | VersionConflict | ServiceUnavailable: ...

    async def observe_effect(
        self,
        principal: Principal,
        expected: BindingState,
        observation: EffectObservation,
    ) -> BindingState | Missing | VersionConflict | ServiceUnavailable: ...


class RunPreparer(Protocol):
    async def prepare(
        self, binding: BindingSpec, snapshot: SnapshotRef
    ) -> PreparedRunInputs | PreparationIssue | ServiceUnavailable: ...


class AppOperationCaller(Protocol):
    async def start(self, run: RunPins) -> str | ServiceUnavailable: ...

    async def inspect(
        self, operation_id: str
    ) -> EffectObservation | Missing | ServiceUnavailable: ...

    async def cancel(
        self, operation_id: str
    ) -> CancellationObservation | Missing | ServiceUnavailable: ...
