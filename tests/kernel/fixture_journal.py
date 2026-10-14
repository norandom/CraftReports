"""Test-only temporary journal; no production fallback or restart guarantee."""

import asyncio
from dataclasses import replace
from uuid import uuid4

from fixture_controls import Checkpoint

from craftreport.application import ports
from craftreport.contracts import CommandIntent, Principal, Receipt, ReceiptState, RetryKey


class FixtureJournal:
    def __init__(self) -> None:
        self.epoch = str(uuid4())
        self.retention_profile = "synthetic-temporary-no-eviction"
        self.available = True
        self.lose_admission_ack = False
        self.lose_record_ack = False
        self.before_admit: Checkpoint | None = None
        self._lock = asyncio.Lock()
        self._commands: dict[RetryKey, CommandIntent] = {}
        self._identities: dict[RetryKey, str] = {}
        self._receipts: dict[str, Receipt] = {}
        self.owners: dict[str, tuple[str, str]] = {}

    def _require_available(self) -> None:
        if not self.available:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("journal"))

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        async with self._lock:
            self._require_available()
            if key not in self._commands:
                return ports.Missing()
            return ports.RetainedCommand(self._commands[key], self._receipts[self._identities[key]])

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        if self.before_admit is not None:
            await self.before_admit.wait()
        async with self._lock:
            if not self.available:
                return ports.ServiceUnavailable("journal")
            key = intent.retry_key
            if key in self._commands:
                previous = self._commands[key]
                if (
                    replace(
                        previous,
                        correlation_id=intent.correlation_id,
                        capability_versions=intent.capability_versions,
                    )
                    != intent
                ):
                    return ports.AdmissionConflict()
                return ports.Existing(
                    ports.RetainedCommand(previous, self._receipts[self._identities[key]])
                )
            operation_id = f"{self.epoch}:{uuid4()}"
            receipt = Receipt(
                operation_id,
                key.operation,
                intent.correlation_id,
                1,
                ReceiptState.ACCEPTED,
                intent.capability_versions,
                intent.resources,
                intent.expected_versions,
                None,
                None,
                (),
                (),
                (),
                self.epoch,
                self.retention_profile,
            )
            self._commands[key] = intent
            self._identities[key] = operation_id
            self._receipts[operation_id] = receipt
            self.owners[operation_id] = (key.deployment_scope, key.subject)
            if self.lose_admission_ack:
                self.lose_admission_ack = False
                return ports.ServiceUnavailable("journal")
            return ports.Admitted(receipt)

    async def read(self, operation_id: str) -> ports.ReceiptRead:
        async with self._lock:
            self._require_available()
            return self._receipts.get(operation_id, ports.Missing())

    async def record(
        self, operation_id: str, expected_revision: int, update: ports.ReceiptUpdate
    ) -> ports.RecordResult:
        async with self._lock:
            self._require_available()
            current = self._receipts.get(operation_id)
            if current is None:
                raise ports.ReceiptMissingError(operation_id)
            if current.revision != expected_revision:
                return ports.RevisionConflict(current.revision)
            _check_transition(current, update)
            updated = _append(current, update)
            self._receipts[operation_id] = updated
            if self.lose_record_ack:
                self.lose_record_ack = False
                raise ports.ServiceUnavailableError(ports.ServiceUnavailable("journal"))
            return updated

    async def record_query(self, observation: ports.QueryObservation) -> Receipt:
        async with self._lock:
            self._require_available()
            if observation.operation_id in self._receipts:
                raise ValueError("Query observation identity already retained")
            receipt = Receipt(
                observation.operation_id,
                observation.operation,
                observation.correlation_id,
                1,
                observation.update.state,
                observation.capability_versions,
                observation.resources,
                observation.expected_versions,
                observation.input_ref,
                observation.update.result_ref,
                observation.update.stages,
                observation.update.diagnostics,
                observation.update.evidence,
                self.epoch,
                self.retention_profile,
                observation.update.result_availability,
            )
            self._receipts[receipt.operation_id] = receipt
            principal: Principal = observation.principal
            self.owners[receipt.operation_id] = (principal.deployment_scope, principal.subject)
            return receipt


def _append(current: Receipt, update: ports.ReceiptUpdate) -> Receipt:
    return replace(
        current,
        revision=current.revision + 1,
        state=update.state,
        stages=current.stages + update.stages,
        diagnostics=current.diagnostics + update.diagnostics,
        evidence=current.evidence + update.evidence,
        result_ref=update.result_ref,
        result_availability=update.result_availability,
    )


def _check_transition(current: Receipt, update: ports.ReceiptUpdate) -> None:
    """Storage invariants only; dispatcher remains owner of outcome/evidence policy."""
    if current.state in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
        raise ValueError("Terminal receipt is immutable")
    if update.state is ReceiptState.ACCEPTED:
        raise ValueError("Cannot regress to accepted")
    if current.state is ReceiptState.PENDING and update.state is ReceiptState.PENDING:
        raise ValueError("Pending requires a terminal observation")
    if current.state is ReceiptState.AMBIGUOUS:
        previous = {ref.identity for ref in current.evidence}
        previous.update(ref.identity for stage in current.stages for ref in stage.evidence)
        if update.state not in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
            raise ValueError("Ambiguity requires terminal reconciliation")
        if not any(
            ref.scope == "reconciliation" and ref.identity not in previous
            for ref in update.evidence
        ):
            raise ValueError("New reconciliation evidence required")
