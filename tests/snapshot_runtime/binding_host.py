"""Installed-test selection of real retained report content; no app effects."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import Connection

from craftreport.adapters.binding_codecs import parameter_digest
from craftreport.adapters.report_codecs import preparation_result_codec, validation_scope_identifier
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import DurableResources
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import commands, evidence
from craftreport.adapters.storage.serialization import decode_object
from craftreport.application import ports
from craftreport.contracts import Availability, Principal, ReceiptState, StageState
from craftreport.data.values import SnapshotRef
from craftreport.reporting.ports import PreparationResult
from craftreport.runtime.bindings import BindingRuntime
from craftreport.runtime.values import (
    BindingSpec,
    BindingState,
    InspectRequest,
    PreparedRunInputs,
    RunPins,
)


def retained_inputs(
    connection: Connection, database: Database, principal: Principal
) -> PreparedRunInputs:
    row = (
        connection.execute(
            select(commands).where(
                commands.c.operation_name == "reports.prepare",
                commands.c.subject == principal.subject,
            )
        )
        .mappings()
        .one()
    )
    retained = DurableJournal(database).retained(connection, row)
    assert isinstance(retained, ports.RetainedCommand)
    receipt = retained.receipt
    assert receipt.state in (ReceiptState.COMPLETE, ReceiptState.FAILED)
    assert receipt.result_availability is Availability.AVAILABLE and receipt.result_ref
    stored = DurableResults(database).read_retained(
        connection, principal, receipt.operation_id, receipt.result_ref
    )
    assert stored.availability is Availability.AVAILABLE and stored.value is not None
    result = preparation_result_codec().decode(stored.value)
    assert isinstance(result, PreparationResult)
    prepared = result.prepared
    stages = [stage for stage in receipt.stages if stage.stage == "prepared"]
    assert len(stages) == 1 and stages[0].state is StageState.PASSED
    refs = [ref for ref in stages[0].evidence if ref.scope == "prepared"]
    assert len(refs) == 1
    reference = refs[0]
    status = DurableEvidence(database).inspect_one(connection, reference)
    assert status.availability is Availability.AVAILABLE
    assert status.verification is StageState.PASSED
    fact_row = (
        connection.execute(select(evidence).where(evidence.c.identity == reference.identity))
        .mappings()
        .one()
    )
    fact = decode_object(fact_row["fact_bytes"], fact_row["fact_digest"])
    scope = validation_scope_identifier(prepared.release_policy)
    assert fact["prepared_digest"] == prepared.content_digest
    assert fact["validation_scope_digest"] == scope
    return PreparedRunInputs(
        prepared.snapshot,
        prepared.definition,
        prepared.template,
        prepared.theme,
        prepared.pack.version_pin,
        prepared.resolved_parameters,
        parameter_digest(prepared.resolved_parameters),
        scope,
        receipt.operation_id,
        receipt.result_ref,
        prepared.content_digest,
    )


@dataclass(frozen=True)
class StoredPreparer:
    database: Database
    principal: Principal

    async def prepare(self, binding: BindingSpec, snapshot: SnapshotRef) -> PreparedRunInputs:
        value = await self.database.transaction(
            lambda connection: retained_inputs(connection, self.database, self.principal)
        )
        assert value.snapshot == snapshot and snapshot.feed_id == binding.feed_id
        return value


async def seed(database: Database, resources: DurableResources) -> None:
    """Select once on an explicitly requested test restart; reuse an existing run."""
    principal = Principal(database.deployment.identity, "alice", frozenset())
    state = await resources.bindings.inspect(
        principal, InspectRequest("binding", "prepared-binding")
    )
    assert isinstance(state, BindingState)
    if state.selected_run_id is not None:
        assert isinstance(
            await resources.bindings.inspect(
                principal, InspectRequest("run", state.selected_run_id)
            ),
            RunPins,
        )
        return
    runtime = BindingRuntime(
        resources.bindings, resources.store.queries, StoredPreparer(database, principal)
    )
    selected = await runtime.select(principal, state.spec.binding_id)
    assert isinstance(selected, RunPins)
    assert selected.target == state.spec.target and selected.snapshot.feed_id == state.spec.feed_id
