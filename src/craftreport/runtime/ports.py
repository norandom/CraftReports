"""Injected exact publication decisions and principal-scoped queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from craftreport.application.service_values import Missing, ServiceUnavailable
from craftreport.data.ports import SnapshotReader

if TYPE_CHECKING:
    from craftreport.application.journal_values import (
        ReceiptUpdate,
        RecordResult,
        RetainedCommand,
    )
    from craftreport.application.ports import VersionConflict
    from craftreport.contracts import (
        EvidenceRef,
        ExpectedVersion,
        JsonObject,
        Principal,
    )
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

    async def save_binding(
        self,
        principal: Principal,
        expected: BindingState,
        candidate: BindingState,
    ) -> BindingState | Missing | VersionConflict | ServiceUnavailable: ...

    async def select_run(
        self,
        principal: Principal,
        expected: BindingState,
        pins: RunPins,
        *,
        attempt_at: str | None = None,
        latest_complete: SnapshotRef | None = None,
    ) -> RunPins | VersionConflict | ServiceUnavailable: ...

    async def observe_effect(
        self,
        principal: Principal,
        expected: BindingState,
        observation: EffectObservation,
        *,
        completed_at: str | None = None,
    ) -> BindingState | Missing | VersionConflict | ServiceUnavailable: ...

    async def list_recoverable(
        self, principal: Principal | None = None
    ) -> tuple[tuple[Principal, BindingState], ...] | ServiceUnavailable: ...

    async def read_decision(
        self, operation_id: str
    ) -> (
        tuple[BindingState, tuple[ExpectedVersion, ...], tuple[EvidenceRef, ...]]
        | Missing
        | ServiceUnavailable
    ): ...


class RecoveryJournal(Protocol):
    async def list_nonterminal(
        self, principal: Principal | None = None
    ) -> tuple[tuple[Principal, RetainedCommand], ...] | ServiceUnavailable: ...

    async def read_command(
        self, principal: Principal, operation_id: str
    ) -> RetainedCommand | Missing | ServiceUnavailable: ...

    async def record(
        self, operation_id: str, expected_revision: int, update: ReceiptUpdate
    ) -> RecordResult: ...


class RecoveryResults(Protocol):
    async def write(self, principal: Principal, operation_id: str, value: JsonObject) -> str: ...

    async def retain_reconciliation_fact(
        self, reference: EvidenceRef, canonical_fact: JsonObject
    ) -> EvidenceRef | ServiceUnavailable: ...


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
