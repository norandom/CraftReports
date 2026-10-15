"""Owned immutable result retention through the existing kernel protocol."""

from uuid import uuid4

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection, RowMapping

from craftreport.adapters.storage.database import Database, StorageUnavailable
from craftreport.adapters.storage.evidence import DurableEvidence, preparation_command
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.schema import commands, evidence, results
from craftreport.adapters.storage.serialization import (
    decode_object,
    encode_evidence,
    encode_object,
    validate_preparation,
)
from craftreport.application import ports
from craftreport.application.dispatch_ports import RetainedResult
from craftreport.contracts import Availability, EvidenceRef, JsonObject, Principal, ReceiptState
from craftreport.contracts.values import require_text

_RESULT_LIMIT = 8_388_608
_STORAGE_FAILURES = (
    StorageUnavailable,
    ValueError,
    TypeError,
    KeyError,
    OverflowError,
    RecursionError,
)


class DurableResults:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.journal = DurableJournal(database)

    def _command(
        self, connection: Connection, principal: Principal, operation_id: str
    ) -> RowMapping | None:
        if principal.deployment_scope != self.database.deployment.identity:
            raise ValueError("Result deployment mismatch")
        row = (
            connection.execute(select(commands).where(commands.c.operation_id == operation_id))
            .mappings()
            .one_or_none()
        )
        if row is not None:
            if (
                row["deployment_scope"] != principal.deployment_scope
                or row["subject"] != principal.subject
            ):
                raise ValueError("Result ownership mismatch")
            self.journal.retained(connection, row)
        return row

    async def write(self, principal: Principal, operation_id: str, value: JsonObject) -> str:
        try:
            require_text(operation_id, "operation_id")
            payload, digest = encode_object(value, max_bytes=_RESULT_LIMIT)

            def write(connection: Connection) -> str:
                command = self._command(connection, principal, operation_id)
                found = (
                    connection.execute(
                        select(results).where(results.c.operation_id == operation_id)
                    )
                    .mappings()
                    .one_or_none()
                )
                if found is not None:
                    readback = self.read_retained(
                        connection, principal, operation_id, found["identity"]
                    )
                    if readback.availability is not Availability.AVAILABLE or (
                        found["result_bytes"],
                        found["result_digest"],
                    ) != (payload, digest):
                        raise ValueError("Immutable result differs")
                    return found["identity"]
                reference = uuid4().hex
                connection.execute(
                    insert(results).values(
                        identity=reference,
                        operation_id=operation_id,
                        command_operation_id=operation_id if command is not None else None,
                        deployment_scope=principal.deployment_scope,
                        subject=principal.subject,
                        result_bytes=payload,
                        result_digest=digest,
                    )
                )
                return reference

            return await self.database.transaction(write)
        except _STORAGE_FAILURES as error:
            raise ports.ServiceUnavailableError(ports.ServiceUnavailable("results")) from error

    async def read(self, principal: Principal, operation_id: str, reference: str) -> RetainedResult:
        try:
            return await self.database.transaction(
                lambda c: self.read_retained(c, principal, operation_id, reference)
            )
        except _STORAGE_FAILURES:
            return RetainedResult(reference, Availability.UNAVAILABLE)

    def read_retained(
        self, connection: Connection, principal: Principal, operation_id: str, reference: str
    ) -> RetainedResult:
        row = (
            connection.execute(select(results).where(results.c.identity == reference))
            .mappings()
            .one_or_none()
        )
        if row is None:
            return RetainedResult(reference, Availability.MISSING)
        if (row["deployment_scope"], row["subject"], row["operation_id"]) != (
            principal.deployment_scope,
            principal.subject,
            operation_id,
        ) or principal.deployment_scope != self.database.deployment.identity:
            return RetainedResult(reference, Availability.INACCESSIBLE)
        command = self._command(connection, principal, operation_id)
        if row["command_operation_id"] is not None:
            if command is None or row["command_operation_id"] != operation_id:
                raise ValueError("Result command link unavailable")
            retained = self.journal.retained(connection, command)
            receipt = retained.receipt if isinstance(retained, ports.RetainedCommand) else retained
            if receipt.result_ref not in (None, reference):
                raise ValueError("Receipt result reference differs")
        elif command is not None:
            raise ValueError("Unlinked retained result")
        value = decode_object(row["result_bytes"], row["result_digest"], max_bytes=_RESULT_LIMIT)
        return RetainedResult(reference, Availability.AVAILABLE, value)

    async def retain_preparation_fact(
        self, reference: EvidenceRef, canonical_fact: JsonObject
    ) -> EvidenceRef | ports.ServiceUnavailable:
        try:
            payload, digest = validate_preparation(canonical_fact, reference)
            reference_bytes, reference_digest = encode_evidence(reference)

            def retain(connection: Connection) -> EvidenceRef:
                retained = preparation_command(connection, self.journal, reference)
                row = (
                    connection.execute(
                        select(evidence).where(evidence.c.identity == reference.identity)
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    if retained.receipt.state not in (ReceiptState.ACCEPTED, ReceiptState.PENDING):
                        raise ValueError("Preparation command is terminal")
                    connection.execute(
                        insert(evidence).values(
                            identity=reference.identity,
                            operation_id=reference.operation_id,
                            reference_bytes=reference_bytes,
                            reference_digest=reference_digest,
                            fact_bytes=payload,
                            fact_digest=digest,
                        )
                    )
                row = (
                    connection.execute(
                        select(evidence).where(evidence.c.identity == reference.identity)
                    )
                    .mappings()
                    .one()
                )
                if (
                    row["reference_bytes"],
                    row["reference_digest"],
                    row["fact_bytes"],
                    row["fact_digest"],
                ) != (reference_bytes, reference_digest, payload, digest):
                    raise ValueError("Preparation fact identity collision")
                verified = DurableEvidence(self.database).inspect_one(connection, reference)
                if verified.availability is not Availability.AVAILABLE:
                    raise ValueError("Preparation fact readback unavailable")
                return reference

            return await self.database.transaction(retain)
        except _STORAGE_FAILURES:
            return ports.ServiceUnavailable("evidence")
