"""Real guarded binding persistence, immutable history and protected reopen."""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import update

from craftreport.adapters.binding_codecs import BindingResultCodec, bind_codec, requirements_digest
from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import DurableResources
from craftreport.adapters.storage.schema import bindings
from craftreport.application import ports
from craftreport.contracts import (
    Availability,
    CommandIntent,
    EffectDisposition,
    ExpectedVersion,
    OperationKey,
    Principal,
    ResourceRef,
    RetryKey,
)
from craftreport.data.requirements import DatasetRequirement, InputRequirements
from craftreport.data.values import SnapshotRef
from craftreport.runtime.bindings import BindingOperations, BindingRuntime
from craftreport.runtime.values import (
    BindingSpec,
    BindingState,
    BindRequest,
    InspectRequest,
    PreparationIssue,
    PreparedRunInputs,
)
from tests.snapshot_runtime.publication_fixture import EmptyCapabilities
from tests.snapshot_runtime.test_binding_values import binding_spec
from tests.snapshot_runtime.test_providers import FEED, provider, publish

ALICE = Principal("deployment-a", "alice", frozenset())
BINDING = ResourceRef("binding", "binding")


async def bind(
    resources: DurableResources, request: BindRequest, revision: str, subject: str = "alice"
) -> ports.ResourceEffectResult:
    key = OperationKey("runtime.bind", "1")
    pins = (ExpectedVersion(BINDING, revision), ExpectedVersion(FEED, "1"))
    fingerprint = CanonicalFingerprint()
    content = bind_codec().encode(request)
    admitted = await DurableJournal(resources.database).admit(
        CommandIntent(
            RetryKey("deployment-a", subject, key, uuid4().hex),
            fingerprint(key, content, (BINDING, FEED), pins),
            fingerprint.policy,
            "binding",
            (),
            (BINDING, FEED),
            pins,
        )
    )
    assert isinstance(admitted, ports.Admitted)
    async with resources.guard.acquire(pins) as guard:
        return await resources.apply(
            BINDING, {"operation_id": admitted.receipt.operation_id, "request": content}, guard
        )


def test_binding_generations_history_and_reopen(tmp_path: Path) -> None:
    async def exercise() -> None:
        path = tmp_path / "binding.sqlite3"
        database = Database(path, "deployment-a")
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        try:
            await publish(resources, database)
            spec = replace(binding_spec(), feed_id=FEED.identity)
            first = await bind(resources, BindRequest(spec, 0), "absent")
            assert isinstance(first, ports.ResourceEffect)
            state = await resources.bindings.inspect(ALICE, InspectRequest("binding", "binding"))
            assert isinstance(state, BindingState) and state.generation == state.revision == 1
            noop = await bind(resources, BindRequest(spec, 1), "1")
            assert isinstance(noop, ports.ResourceEffect) and noop.versions == first.versions
            updated = replace(spec, target=replace(spec.target, document_id="other"))
            second = await bind(resources, BindRequest(updated, 1), "1")
            assert isinstance(second, ports.ResourceEffect)
            stale = await bind(resources, BindRequest(spec, 1), "2")
            assert isinstance(stale, ports.VersionConflict)
            facts = await DurableEvidence(database, resources.verify_binding).inspect(
                (*first.evidence, *noop.evidence, *second.evidence)
            )
            assert all(f.availability is Availability.AVAILABLE for f in facts)
        finally:
            await database.close()
        reopened = Database(path, "deployment-a")
        try:
            reopened_resources = provider(reopened)
            reopened_resources.configure_bindings(bind_codec(), BindingResultCodec())
            store = reopened_resources.bindings
            current = await store.inspect(ALICE, InspectRequest("binding", "binding"))
            assert (
                isinstance(current, BindingState)
                and current.spec == updated
                and current.generation == 2
            )
            denied = await store.inspect(
                replace(ALICE, subject="bob"), InspectRequest("binding", "binding")
            )
            assert isinstance(denied, ports.ServiceUnavailable)
            assert isinstance(
                await store.inspect(ALICE, InspectRequest("binding", "missing")), ports.Missing
            )
            assert isinstance(
                await store.inspect(ALICE, InspectRequest("run", "missing")), ports.Missing
            )
            missing_verifier = await DurableEvidence(reopened).inspect(first.evidence)
            assert all(item.availability is Availability.UNAVAILABLE for item in missing_verifier)
            await reopened.transaction(
                lambda c: c.execute(update(bindings).values(binding_bytes=b"corrupt"))
            )
            assert isinstance(
                await store.inspect(ALICE, InspectRequest("binding", "binding")),
                ports.ServiceUnavailable,
            )
            historical = await DurableEvidence(reopened, reopened_resources.verify_binding).inspect(
                first.evidence
            )
            assert all(item.availability is Availability.AVAILABLE for item in historical)
        finally:
            await reopened.close()

    asyncio.run(exercise())


class ChangingPreparer:
    def __init__(self, resources: DurableResources, mode: str) -> None:
        self.resources, self.mode, self.calls = resources, mode, 0

    async def prepare(self, binding: BindingSpec, snapshot: SnapshotRef) -> PreparedRunInputs:
        self.calls += 1
        if self.mode == "stale":
            changed = replace(binding, target=replace(binding.target, document_id="new"))
            assert isinstance(
                await bind(self.resources, BindRequest(changed, 1), "1"), ports.ResourceEffect
            )
        return PreparedRunInputs(
            snapshot,
            binding.definition,
            binding.template,
            binding.theme,
            binding.pack,
            binding.resolved_parameters,
            binding.parameter_digest,
            "c" * 64 if self.mode == "mismatch" else binding.validation_scope,
            "not-retained",
            "not-retained",
            "d" * 64,
        )


def test_selection_excludes_incomplete_mismatch_and_stale_preparation(tmp_path: Path) -> None:
    async def exercise() -> None:
        for mode in ("incomplete", "mismatch", "stale", "unretained"):
            database = Database(tmp_path / (mode + ".sqlite3"), ALICE.deployment_scope)
            resources = provider(database)
            resources.configure_bindings(bind_codec(), BindingResultCodec())
            try:
                await publish(resources, database)
                spec = replace(binding_spec(), feed_id=FEED.identity)
                if mode == "incomplete":
                    requirements = InputRequirements((DatasetRequirement("absent", ()),), ())
                    spec = replace(
                        spec,
                        requirements=requirements,
                        requirements_digest=requirements_digest(requirements),
                    )
                assert isinstance(
                    await bind(resources, BindRequest(spec, 0), "absent"), ports.ResourceEffect
                )
                preparer = ChangingPreparer(resources, mode)
                selected = await BindingRuntime(
                    resources.bindings, resources.store.queries, preparer
                ).select(ALICE, spec.binding_id)
                if mode in ("incomplete", "mismatch"):
                    assert isinstance(selected, PreparationIssue)
                    assert selected.code == (
                        "incomplete_binding" if mode == "incomplete" else "preparation_mismatch"
                    )
                elif mode == "stale":
                    assert isinstance(selected, ports.VersionConflict)
                else:
                    assert isinstance(selected, ports.ServiceUnavailable)
                state = await resources.bindings.inspect(
                    ALICE, InspectRequest("binding", spec.binding_id)
                )
                assert (
                    isinstance(state, BindingState)
                    and state.selected_run_id is None
                    and state.intent == "stopped"
                )
                assert preparer.calls == (0 if mode == "incomplete" else 1)
            finally:
                await database.close()

    asyncio.run(exercise())


def test_post_commit_read_failure_retains_typed_unknown_and_real_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "readback.sqlite3", ALICE.deployment_scope)
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        try:
            await publish(resources, database)
            spec = replace(binding_spec(), feed_id=FEED.identity)
            request = BindRequest(spec, 0)
            key = OperationKey("runtime.bind", "1")
            pins = (ExpectedVersion(BINDING, "absent"), ExpectedVersion(FEED, "1"))
            fingerprint = CanonicalFingerprint()
            admitted = await DurableJournal(database).admit(
                CommandIntent(
                    RetryKey(ALICE.deployment_scope, ALICE.subject, key, uuid4().hex),
                    fingerprint(key, bind_codec().encode(request), (BINDING, FEED), pins),
                    fingerprint.policy,
                    "readback",
                    (),
                    (BINDING, FEED),
                    pins,
                )
            )
            assert isinstance(admitted, ports.Admitted)

            async def unavailable(
                principal: Principal, identity: InspectRequest
            ) -> ports.ServiceUnavailable:
                return ports.ServiceUnavailable("injected_read_failure")

            monkeypatch.setattr(resources.bindings, "inspect", unavailable)
            evidence = DurableEvidence(database, resources.verify_binding)
            reads = ports.ReadServices(evidence, EmptyCapabilities(), resources)
            handler = BindingOperations(
                resources.bindings, bind_codec(), lambda _: True, lambda _p, _t: True
            )
            async with resources.guard.acquire(pins) as guard:
                outcome = await handler.bind(
                    request,
                    ports.CommandContext(
                        admitted.receipt.operation_id,
                        ALICE,
                        guard,
                        ports.CommandServices(reads, resources),
                    ),
                )
            assert outcome.result == ports.ServiceUnavailable("binding_readback")
            assert outcome.effect is EffectDisposition.UNKNOWN and len(outcome.evidence) == 1
            assert all(
                status.availability is Availability.AVAILABLE
                for status in await evidence.inspect(outcome.evidence)
            )
            assert isinstance(await resources.read(BINDING), ports.ResourceSnapshot)
        finally:
            await database.close()

    asyncio.run(exercise())


class RetainedPreparer:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def prepare(self, binding: BindingSpec, snapshot: SnapshotRef) -> PreparedRunInputs:
        from craftreport.adapters.storage.results import DurableResults
        from craftreport.contracts import ReceiptState, StageResult, StageState
        from tests.snapshot_runtime.test_evidence import fact, reference

        ref = await reference(self.database)
        results = DurableResults(self.database)
        assert await results.retain_preparation_fact(ref, fact()) == ref
        result_ref = await results.write(ALICE, ref.operation_id, {"prepared_digest": "d" * 64})
        journal = DurableJournal(self.database)
        stage = StageResult("prepared", StageState.PASSED, "prepared", (ref,))
        from craftreport.contracts import Receipt

        updated = await journal.record(
            ref.operation_id,
            1,
            ports.ReceiptUpdate(
                ReceiptState.COMPLETE,
                result_ref=result_ref,
                result_availability=Availability.AVAILABLE,
                stages=(stage,),
                evidence=(ref,),
            ),
        )
        assert isinstance(updated, Receipt)
        return PreparedRunInputs(
            snapshot,
            binding.definition,
            binding.template,
            binding.theme,
            binding.pack,
            binding.resolved_parameters,
            binding.parameter_digest,
            binding.validation_scope,
            ref.operation_id,
            result_ref,
            "d" * 64,
        )


class MemoryEvidenceReader:
    def __init__(self) -> None:
        self.verified: set[str] = set()

    async def inspect(self, refs: tuple[object, ...]) -> tuple[object, ...]:
        from craftreport.contracts import EvidenceRef, EvidenceStatus, StageState

        typed_refs = tuple(r for r in refs if isinstance(r, EvidenceRef))
        return tuple(
            EvidenceStatus(ref, Availability.AVAILABLE, StageState.PASSED)
            if ref.identity in self.verified
            else EvidenceStatus(ref, Availability.UNAVAILABLE, StageState.PENDING)
            for ref in typed_refs
        )


class StubAppCaller:
    def __init__(self) -> None:
        from craftreport.runtime.values import CancellationObservation, EffectObservation

        self.observations: dict[str, EffectObservation] = {}
        self.cancellations: dict[str, CancellationObservation] = {}

    async def start(self, run: object) -> str:
        return "op-1"

    async def inspect(self, operation_id: str) -> object:
        return self.observations.get(operation_id, ports.Missing())

    async def cancel(self, operation_id: str) -> object:
        return self.cancellations.get(operation_id, ports.Missing())


def test_verified_observations_advance_applied_while_partial_and_stale_stay_historical(
    tmp_path: Path,
) -> None:
    from craftreport.contracts import EvidenceRef, StageResult, StageState
    from craftreport.runtime.values import CancellationObservation, EffectObservation, RunPins

    async def exercise() -> None:
        path = tmp_path / "observations.sqlite3"
        database = Database(path, ALICE.deployment_scope)
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        evidence = MemoryEvidenceReader()
        caller = StubAppCaller()
        try:
            await publish(resources, database)
            spec = replace(binding_spec(), feed_id=FEED.identity)
            assert isinstance(
                await bind(resources, BindRequest(spec, 0), "absent"), ports.ResourceEffect
            )
            runtime = BindingRuntime(
                resources.bindings,
                resources.store.queries,
                RetainedPreparer(database),
                evidence,  # type: ignore[arg-type]
                caller,  # type: ignore[arg-type]
            )
            run1 = await runtime.select(ALICE, spec.binding_id)
            assert isinstance(run1, RunPins)
            state1 = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(state1, BindingState) and state1.selected_run_id == run1.run_id
            assert state1.applied_run_id is None

            pins1 = (
                ExpectedVersion(ResourceRef("run", run1.run_id), run1.prepared_digest),
                ExpectedVersion(ResourceRef("gridcraft_document", spec.target.document_id), "1"),
            )
            ref_unverified = EvidenceRef(
                "ev-unverified",
                "app_applied",
                "op-unverified",
                OperationKey("gridcraft.apply", "1"),
                pins1,
                "a" * 64,
            )
            obs_unverified = EffectObservation(
                run1.run_id,
                spec.target,
                1,
                EffectDisposition.APPLIED,
                (StageResult("applied", StageState.PASSED, "ok", (ref_unverified,)),),
                (ref_unverified,),
                True,
            )
            after_unverified = await runtime.observe_effect(ALICE, state1, obs_unverified)
            assert isinstance(after_unverified, BindingState)
            assert after_unverified.applied_run_id is None
            assert after_unverified.observations[-1].verified_complete is False

            ref_verified = replace(ref_unverified, identity="ev-verified", operation_id="op-ok")
            evidence.verified.add("ev-verified")
            obs_verified = EffectObservation(
                run1.run_id,
                spec.target,
                1,
                EffectDisposition.APPLIED,
                (StageResult("applied", StageState.PASSED, "ok", (ref_verified,)),),
                (ref_verified,),
                True,
            )
            caller.observations["op-ok"] = obs_verified
            after_verified = await runtime.observe_operation(ALICE, after_unverified, "op-ok")
            assert isinstance(after_verified, BindingState)
            assert after_verified.applied_run_id == run1.run_id
            assert after_verified.applied_snapshot == run1.snapshot
            assert after_verified.last_effect is EffectDisposition.APPLIED
            assert after_verified.last_error is None
            assert after_verified.observations[-1].verified_complete is True

            run2 = await runtime.select(ALICE, spec.binding_id)
            assert isinstance(run2, RunPins) and run2.run_id != run1.run_id
            state2 = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(state2, BindingState) and state2.selected_run_id == run2.run_id
            assert state2.applied_run_id == run1.run_id

            pins2 = (
                ExpectedVersion(ResourceRef("run", run2.run_id), run2.prepared_digest),
                ExpectedVersion(ResourceRef("gridcraft_document", spec.target.document_id), "2"),
            )
            ref_partial = EvidenceRef(
                "ev-partial",
                "app_applied",
                "op-partial",
                OperationKey("gridcraft.apply", "1"),
                pins2,
                "b" * 64,
            )
            evidence.verified.add("ev-partial")
            obs_partial = EffectObservation(
                run2.run_id,
                spec.target,
                1,
                EffectDisposition.PARTIAL,
                (StageResult("applied", StageState.FAILED, "edit_conflict", (ref_partial,)),),
                (ref_partial,),
                True,
            )
            caller.cancellations["op-cancel"] = CancellationObservation(
                "op-cancel", "uncertain", EffectDisposition.PARTIAL, obs_partial
            )
            cancelled = await runtime.cancel_operation(ALICE, state2, "op-cancel")
            assert isinstance(cancelled, CancellationObservation)
            after_partial = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(after_partial, BindingState)
            assert after_partial.applied_run_id == run1.run_id
            assert after_partial.last_effect is EffectDisposition.PARTIAL
            assert after_partial.last_error == "edit_conflict"
            assert after_partial.observations[-1].verified_complete is False

            changed_spec = replace(spec, target=replace(spec.target, document_id="doc-2"))
            assert isinstance(
                await bind(resources, BindRequest(changed_spec, 1), str(after_partial.revision)),
                ports.ResourceEffect,
            )
            state_gen2 = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(state_gen2, BindingState) and state_gen2.generation == 2
            assert state_gen2.selected_run_id is None
            assert state_gen2.applied_run_id == run1.run_id

            ref_stale = replace(ref_partial, identity="ev-stale", operation_id="op-stale")
            evidence.verified.add("ev-stale")
            obs_stale = EffectObservation(
                run2.run_id,
                spec.target,
                1,
                EffectDisposition.APPLIED,
                (StageResult("applied", StageState.PASSED, "ok", (ref_stale,)),),
                (ref_stale,),
                True,
            )
            conflict = await runtime.observe_effect(ALICE, state_gen2, obs_stale)
            assert isinstance(conflict, ports.VersionConflict)
            final_state = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(final_state, BindingState)
            assert final_state.applied_run_id == run1.run_id
            assert final_state.observations[-1].run_id == run2.run_id
            assert final_state.observations[-1].verified_complete is False
        finally:
            await database.close()

        reopened = Database(path, ALICE.deployment_scope)
        try:
            reopened_resources = provider(reopened)
            reopened_resources.configure_bindings(bind_codec(), BindingResultCodec())
            reopened_state = await reopened_resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert reopened_state == final_state
        finally:
            await reopened.close()

    asyncio.run(exercise())
