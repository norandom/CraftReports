"""One atomic command/query journal with exact retained receipt observations."""

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy import update as sql_update
from sqlalchemy.engine import Connection, RowMapping

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.schema import commands, observations
from craftreport.adapters.storage.serialization import (
    decode_intent,
    decode_receipt,
    encode_intent,
    encode_receipt,
)
from craftreport.application import ports
from craftreport.application.outcomes import validate_recorded_update
from craftreport.contracts import CommandIntent, Receipt, ReceiptState, RetryKey


def _check_transition(current: Receipt, change: ports.ReceiptUpdate, prior: str | None) -> None:
    if current.state in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
        raise ValueError("Terminal receipt is immutable")
    if change.state is ReceiptState.ACCEPTED:
        raise ValueError("Cannot regress to accepted")
    if current.state is ReceiptState.PENDING and change.state is ReceiptState.PENDING:
        if prior is None or change.handoff_ref in (None, prior):
            raise ValueError("Pending requires a new execution owner")
    if current.state is ReceiptState.AMBIGUOUS:
        previous = {ref.identity for ref in current.evidence}
        previous.update(ref.identity for stage in current.stages for ref in stage.evidence)
        if change.state not in (ReceiptState.COMPLETE, ReceiptState.PARTIAL, ReceiptState.FAILED):
            raise ValueError("Ambiguity requires terminal reconciliation")
        if not any(
            ref.scope == "reconciliation" and ref.identity not in previous
            for ref in change.evidence
        ):
            raise ValueError("New reconciliation evidence required")


def _append(current: Receipt, change: ports.ReceiptUpdate) -> Receipt:
    candidate = replace(
        current,
        revision=current.revision + 1,
        state=change.state,
        stages=current.stages + change.stages,
        diagnostics=current.diagnostics + change.diagnostics,
        evidence=current.evidence + change.evidence,
        result_ref=change.result_ref,
        result_availability=change.result_availability,
    )
    validate_recorded_update(current, candidate, change)
    return candidate


class DurableJournal:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def _transaction[T](self, action: Callable[[Connection], T]) -> T:
        try:
            return await self._database.transaction(action)
        except StorageUnavailable as error:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("journal")) from error

    def _scope(self, deployment_scope: str) -> None:
        if deployment_scope != self._database.deployment.identity:
            raise StorageUnavailable("Journal deployment mismatch")

    def retained(self, connection: Connection, row: RowMapping) -> ports.RetainedCommand | Receipt:
        try:
            receipt = decode_receipt(row["receipt_bytes"], row["receipt_digest"])
            self._scope(row["deployment_scope"])
            if (
                receipt.operation_id != row["operation_id"]
                or receipt.revision != row["revision"]
                or receipt.operation.name != row["operation_name"]
                or receipt.operation.contract_version != row["contract_version"]
                or receipt.deployment_epoch != self._database.deployment.epoch
                or receipt.retention_profile != self._database.deployment.retention_profile
                or not isinstance(row["subject"], str)
                or not row["subject"].strip()
            ):
                raise ValueError("Retained receipt identity mismatch")
            history = (
                connection.execute(
                    select(observations).where(
                        observations.c.operation_id == receipt.operation_id,
                        observations.c.revision == receipt.revision,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if history is None or any(
                history[field] != row[field]
                for field in ("receipt_bytes", "receipt_digest", "handoff_ref")
            ):
                raise ValueError("Current receipt observation mismatch")
            if row["record_kind"] == "query":
                return receipt
            intent = decode_intent(row["intent_bytes"], row["intent_digest"])
            key = intent.retry_key
            if (
                key.deployment_scope,
                key.subject,
                key.operation.name,
                key.operation.contract_version,
                key.caller_key,
            ) != (
                row["deployment_scope"],
                row["subject"],
                row["operation_name"],
                row["contract_version"],
                row["caller_key"],
            ):
                raise ValueError("Retained intent identity mismatch")
            return ports.RetainedCommand(intent, receipt)
        except (ValueError, TypeError) as error:
            raise StorageUnavailable("Retained journal content invalid") from error

    def _find(self, connection: Connection, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        self._scope(key.deployment_scope)
        row = (
            connection.execute(
                select(commands).where(
                    commands.c.record_kind == "command",
                    commands.c.deployment_scope == key.deployment_scope,
                    commands.c.subject == key.subject,
                    commands.c.operation_name == key.operation.name,
                    commands.c.contract_version == key.operation.contract_version,
                    commands.c.caller_key == key.caller_key,
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return ports.Missing()
        retained = self.retained(connection, row)
        if not isinstance(retained, ports.RetainedCommand):
            raise StorageUnavailable("Retained command kind mismatch")
        return retained

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        return await self._transaction(lambda connection: self._find(connection, key))

    def _insert(
        self,
        connection: Connection,
        receipt: Receipt,
        scope: str,
        subject: str,
        intent: CommandIntent | None,
        handoff: str | None = None,
    ) -> None:
        self._scope(scope)
        payload, digest = encode_receipt(receipt)
        intent_bytes, intent_digest = (None, None) if intent is None else encode_intent(intent)
        connection.execute(
            insert(commands).values(
                operation_id=receipt.operation_id,
                record_kind="query" if intent is None else "command",
                deployment_scope=scope,
                subject=subject,
                operation_name=receipt.operation.name,
                contract_version=receipt.operation.contract_version,
                caller_key=None if intent is None else intent.retry_key.caller_key,
                intent_bytes=intent_bytes,
                intent_digest=intent_digest,
                revision=receipt.revision,
                receipt_bytes=payload,
                receipt_digest=digest,
                handoff_ref=handoff,
            )
        )
        connection.execute(
            insert(observations).values(
                operation_id=receipt.operation_id,
                revision=receipt.revision,
                receipt_bytes=payload,
                receipt_digest=digest,
                handoff_ref=handoff,
            )
        )

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        def admission(connection: Connection) -> ports.Admission:
            found = self._find(connection, intent.retry_key)
            if isinstance(found, ports.RetainedCommand):
                equivalent = replace(
                    found.intent,
                    correlation_id=intent.correlation_id,
                    capability_versions=intent.capability_versions,
                )
                return ports.Existing(found) if equivalent == intent else ports.AdmissionConflict()
            deployment = self._database.deployment
            receipt = Receipt(
                f"{deployment.epoch}:{uuid4()}",
                intent.retry_key.operation,
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
                deployment.epoch,
                deployment.retention_profile,
            )
            self._insert(
                connection,
                receipt,
                intent.retry_key.deployment_scope,
                intent.retry_key.subject,
                intent,
            )
            return ports.Admitted(receipt)

        try:
            return await self._transaction(admission)
        except ports.ServiceUnavailableError as error:
            return error.reason

    async def read(self, operation_id: str) -> ports.ReceiptRead:
        def read(connection: Connection) -> ports.ReceiptRead:
            row = (
                connection.execute(select(commands).where(commands.c.operation_id == operation_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                return ports.Missing()
            retained = self.retained(connection, row)
            return retained.receipt if isinstance(retained, ports.RetainedCommand) else retained

        return await self._transaction(read)

    async def record(
        self, operation_id: str, expected_revision: int, update: ports.ReceiptUpdate
    ) -> ports.RecordResult:
        def record(connection: Connection) -> ports.RecordResult:
            row = (
                connection.execute(select(commands).where(commands.c.operation_id == operation_id))
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ports.ReceiptMissingError(operation_id)
            retained = self.retained(connection, row)
            current = retained.receipt if isinstance(retained, ports.RetainedCommand) else retained
            if current.revision != expected_revision:
                return ports.RevisionConflict(current.revision)
            _check_transition(current, update, row["handoff_ref"])
            candidate = _append(current, update)
            payload, digest = encode_receipt(candidate)
            handoff = update.handoff_ref or row["handoff_ref"]
            changed = connection.execute(
                sql_update(commands)
                .where(
                    commands.c.operation_id == operation_id,
                    commands.c.revision == expected_revision,
                )
                .values(
                    revision=candidate.revision,
                    receipt_bytes=payload,
                    receipt_digest=digest,
                    handoff_ref=handoff,
                )
            )
            if changed.rowcount != 1:
                raise StorageUnavailable("Retained receipt changed during conditional update")
            connection.execute(
                insert(observations).values(
                    operation_id=operation_id,
                    revision=candidate.revision,
                    receipt_bytes=payload,
                    receipt_digest=digest,
                    handoff_ref=handoff,
                )
            )
            saved = (
                connection.execute(select(commands).where(commands.c.operation_id == operation_id))
                .mappings()
                .one()
            )
            observed = self.retained(connection, saved)
            readback = observed.receipt if isinstance(observed, ports.RetainedCommand) else observed
            validate_recorded_update(current, readback, update)
            return readback

        return await self._transaction(record)

    async def record_query(self, observation: ports.QueryObservation) -> Receipt:
        def record(connection: Connection) -> Receipt:
            deployment = self._database.deployment
            change = observation.update
            receipt = Receipt(
                observation.operation_id,
                observation.operation,
                observation.correlation_id,
                1,
                change.state,
                observation.capability_versions,
                observation.resources,
                observation.expected_versions,
                observation.input_ref,
                change.result_ref,
                change.stages,
                change.diagnostics,
                change.evidence,
                deployment.epoch,
                deployment.retention_profile,
                change.result_availability,
            )
            self._insert(
                connection,
                receipt,
                observation.principal.deployment_scope,
                observation.principal.subject,
                None,
                change.handoff_ref,
            )
            return receipt

        return await self._transaction(record)
