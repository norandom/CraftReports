"""Reconciliation of interrupted operations, bindings and uncertain external effects."""

import asyncio
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete

from craftreport.adapters.binding_codecs import (
    BindingResultCodec,
    ReconcileResultCodec,
    bind_codec,
    reconcile_codec,
)
from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.snapshot_wire import publication_result_codec, snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.journal import DurableJournal
from craftreport.adapters.storage.providers import DurableResources
from craftreport.adapters.storage.results import DurableResults
from craftreport.adapters.storage.schema import evidence
from craftreport.application import ports
from craftreport.composition.settings import HostSettings
from craftreport.composition.snapshot_host import configure_snapshot, open_snapshot_application
from craftreport.contracts import (
    Availability,
    CommandIntent,
    EffectDisposition,
    EvidenceRef,
    ExpectedVersion,
    InvocationEnvelope,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    ResourceRef,
    RetryKey,
    StageResult,
    StageState,
)
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary
from craftreport.runtime.bindings import BindingRuntime
from craftreport.runtime.recovery import (
    ReconcileRequest,
    ReconcileResult,
    RecoveryUseCase,
    sweep_startup_orphans,
)
from craftreport.runtime.scheduler import BindingScheduler
from craftreport.runtime.values import (
    BindingState,
    BindRequest,
    ControlRequest,
    EffectObservation,
    InspectRequest,
    RunPins,
)
from tests.snapshot_runtime.test_binding_values import binding_spec
from tests.snapshot_runtime.test_bindings import (
    ALICE,
    BINDING,
    MemoryEvidenceReader,
    RetainedPreparer,
    StubAppCaller,
    bind,
)
from tests.snapshot_runtime.test_providers import FEED, provider, publish


def _make_recovery(
    database: Database,
    resources: DurableResources,
    scheduler: BindingScheduler,
    owner_ok: bool = True,
    target_ok: bool = True,
) -> RecoveryUseCase:
    return RecoveryUseCase(
        DurableJournal(database),
        DurableResults(database),
        DurableEvidence(database, resources.verify_binding),
        resources,
        resources.store,
        resources.bindings,
        scheduler,
        publication_result_codec(),
        BindingResultCodec(),
        lambda p: owner_ok and p == ALICE,
        lambda p, _t: target_ok and p == ALICE,
    )


def test_reconcile_request_and_result_wire_codecs() -> None:
    with pytest.raises(ValueError, match="requires an operation, binding or run"):
        ReconcileRequest()
    with pytest.raises(ValueError, match="expected_generation"):
        ReconcileRequest(binding_id="binding", expected_generation=0)
    with pytest.raises(ValueError, match="Unsupported reconciliation status"):
        ReconcileResult("invalid")  # type: ignore[arg-type]

    spec = binding_spec()
    obs = EffectObservation(
        "run_1",
        spec.target,
        1,
        EffectDisposition.APPLIED,
        (StageResult("applied", StageState.PASSED, "ok", ()),),
        (),
        True,
    )
    req = ReconcileRequest(
        operation_id="op-1", binding_id="binding", expected_generation=1, observation=obs
    )
    encoded_req = reconcile_codec().encode(req)
    assert reconcile_codec().decode(encoded_req) == req

    ev = EvidenceRef(
        "ev1",
        "reconciliation",
        "op-1",
        OperationKey("runtime.reconcile", "1"),
        (ExpectedVersion(BINDING, "1"),),
        "a" * 64,
    )
    res = ReconcileResult(
        "reconciled",
        "op-1",
        ReceiptState.COMPLETE,
        ev,
        (ev,),
        BindingState(spec, 1, 1),
    )
    codec = ReconcileResultCodec()
    assert codec.decode(codec.encode(res)) == res
    assert "properties" in codec.schema() or "$defs" in codec.schema()


def test_startup_sweep_marks_orphans_ambiguous_and_suspends_running_bindings(
    tmp_path: Path,
) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "sweep.sqlite3", ALICE.deployment_scope)
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        try:
            await publish(resources, database)
            spec = replace(binding_spec(), feed_id=FEED.identity)
            assert isinstance(
                await bind(resources, BindRequest(spec, 0), "absent"), ports.ResourceEffect
            )
            current = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(current, BindingState)
            running = await resources.bindings.save_binding(
                ALICE,
                current,
                replace(current, revision=2, intent="running", pause_pending=True),
            )
            assert isinstance(running, BindingState)

            key = OperationKey("runtime.control", "1")
            fp = CanonicalFingerprint()
            admitted = await DurableJournal(database).admit(
                CommandIntent(
                    RetryKey(ALICE.deployment_scope, ALICE.subject, key, uuid4().hex),
                    fp(key, {}, (BINDING,), (ExpectedVersion(BINDING, "2"),)),
                    fp.policy,
                    "control",
                    (),
                    (BINDING,),
                    (ExpectedVersion(BINDING, "2"),),
                )
            )
            assert isinstance(admitted, ports.Admitted)
            assert admitted.receipt.state is ReceiptState.ACCEPTED

            await sweep_startup_orphans(DurableJournal(database), resources.bindings)

            swept_cmd = await DurableJournal(database).read_command(
                ALICE, admitted.receipt.operation_id
            )
            assert isinstance(swept_cmd, ports.RetainedCommand)
            assert swept_cmd.receipt.state is ReceiptState.AMBIGUOUS

            swept_bind = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(swept_bind, BindingState)
            assert swept_bind.intent == "running"
            assert swept_bind.recovery_required is True
            assert swept_bind.pause_pending is False
        finally:
            await database.close()

    asyncio.run(exercise())


def test_reconcile_interrupted_local_publication_and_binding_operations(tmp_path: Path) -> None:
    async def exercise() -> None:
        database = Database(tmp_path / "local-recon.sqlite3", ALICE.deployment_scope)
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        runtime = BindingRuntime(
            resources.bindings, resources.store.queries, RetainedPreparer(database)
        )
        scheduler = BindingScheduler(runtime)
        recovery = _make_recovery(database, resources, scheduler)
        try:
            # 1. Interrupted snapshot.publish where decision was committed
            pub_effect = await publish(resources, database)
            assert isinstance(pub_effect, ports.ResourceEffect)
            nonterm = await DurableJournal(database).list_nonterminal()
            assert isinstance(nonterm, tuple) and len(nonterm) == 1
            pub_op_id = nonterm[0][1].receipt.operation_id

            first = await recovery.reconcile_operation(ALICE, pub_op_id)
            assert isinstance(first, ReconcileResult)
            assert first.status == "reconciled"
            assert first.operation_state is ReceiptState.COMPLETE
            assert first.reconciliation_ref is not None
            assert len(first.prior_evidence) == len(pub_effect.evidence)

            # Second reconcile is idempotent and does not rewrite terminal evidence
            second = await recovery.reconcile_operation(ALICE, pub_op_id)
            assert isinstance(second, ReconcileResult)
            assert second.status == "already_terminal"
            assert second.operation_state is ReceiptState.COMPLETE
            assert second.reconciliation_ref is None

            # 2. Interrupted snapshot.publish where decision was NOT committed -> reconciles FAILED
            pub_key = OperationKey("snapshot.publish", "1")
            fp = CanonicalFingerprint()
            uncommitted_pub = await DurableJournal(database).admit(
                CommandIntent(
                    RetryKey(ALICE.deployment_scope, ALICE.subject, pub_key, uuid4().hex),
                    fp(pub_key, {"v": "2"}, (FEED,), (ExpectedVersion(FEED, "1"),)),
                    fp.policy,
                    "publish",
                    (),
                    (FEED,),
                    (ExpectedVersion(FEED, "1"),),
                )
            )
            assert isinstance(uncommitted_pub, ports.Admitted)
            pub2_op_id = uncommitted_pub.receipt.operation_id
            absent_pub = await recovery.reconcile_operation(ALICE, pub2_op_id)
            assert isinstance(absent_pub, ReconcileResult)
            assert absent_pub.status == "reconciled"
            assert absent_pub.operation_state is ReceiptState.FAILED
            assert absent_pub.reconciliation_ref is not None

            # 3. Interrupted runtime.bind where binding revision was committed -> COMPLETE
            spec = replace(binding_spec(), feed_id=FEED.identity)
            assert isinstance(
                await bind(resources, BindRequest(spec, 0), "absent"), ports.ResourceEffect
            )
            nonterm3 = await DurableJournal(database).list_nonterminal()
            assert isinstance(nonterm3, tuple) and len(nonterm3) == 1
            bind_op_id = nonterm3[0][1].receipt.operation_id
            bind_rec = await recovery.reconcile_operation(ALICE, bind_op_id)
            assert isinstance(bind_rec, ReconcileResult)
            assert bind_rec.status == "reconciled"
            assert bind_rec.operation_state is ReceiptState.COMPLETE
            assert bind_rec.binding is not None and bind_rec.binding.generation == 1

            # 4. Interrupted runtime.bind where binding revision is absent -> FAILED
            updated_spec = replace(spec, target=replace(spec.target, document_id="doc-2"))
            assert isinstance(
                await bind(resources, BindRequest(updated_spec, 1), "1"), ports.ResourceEffect
            )
            nonterm4 = await DurableJournal(database).list_nonterminal()
            assert isinstance(nonterm4, tuple) and len(nonterm4) == 1
            bind2_op_id = nonterm4[0][1].receipt.operation_id
            await database.transaction(
                lambda c: c.execute(delete(evidence).where(evidence.c.operation_id == bind2_op_id))
            )
            absent_bind = await recovery.reconcile_operation(ALICE, bind2_op_id)
            assert isinstance(absent_bind, ReconcileResult)
            assert absent_bind.status == "reconciled"
            assert absent_bind.operation_state is ReceiptState.FAILED
        finally:
            await scheduler.aclose()
            await database.close()

    asyncio.run(exercise())


def test_reconcile_binding_and_uncertain_external_effects_never_replays_blindly(
    tmp_path: Path,
) -> None:
    class CountingCaller(StubAppCaller):
        def __init__(self) -> None:
            super().__init__()
            self.starts = 0

        async def start(self, run: object) -> str:
            self.starts += 1
            return await super().start(run)

    async def exercise() -> None:
        database = Database(tmp_path / "ext-recon.sqlite3", ALICE.deployment_scope)
        resources = provider(database)
        resources.configure_bindings(bind_codec(), BindingResultCodec())
        ev_reader = MemoryEvidenceReader()
        app = CountingCaller()
        runtime = BindingRuntime(
            resources.bindings,
            resources.store.queries,
            RetainedPreparer(database),
            ev_reader,  # type: ignore[arg-type]
            app,  # type: ignore[arg-type]
        )
        scheduler = BindingScheduler(runtime)
        try:
            await publish(resources, database)
            spec = replace(binding_spec(), feed_id=FEED.identity)
            assert isinstance(
                await bind(resources, BindRequest(spec, 0), "absent"), ports.ResourceEffect
            )
            rec = _make_recovery(database, resources, scheduler)
            nonterm_init = await DurableJournal(database).list_nonterminal()
            assert isinstance(nonterm_init, tuple)
            for _, cmd in nonterm_init:
                await rec.reconcile_operation(ALICE, cmd.receipt.operation_id)

            run = await runtime.select(ALICE, spec.binding_id)
            assert isinstance(run, RunPins)
            state = await resources.bindings.inspect(
                ALICE, InspectRequest("binding", spec.binding_id)
            )
            assert isinstance(state, BindingState)

            key = OperationKey("runtime.control", "1")
            fp = CanonicalFingerprint()
            admitted = await DurableJournal(database).admit(
                CommandIntent(
                    RetryKey(ALICE.deployment_scope, ALICE.subject, key, uuid4().hex),
                    fp(key, {}, (BINDING,), (ExpectedVersion(BINDING, str(state.revision)),)),
                    fp.policy,
                    "control",
                    (),
                    (BINDING,),
                    (ExpectedVersion(BINDING, str(state.revision)),),
                )
            )
            assert isinstance(admitted, ports.Admitted)
            ext_op_id = admitted.receipt.operation_id

            state = await resources.bindings.save_binding(  # type: ignore[assignment]
                ALICE,
                state,
                replace(
                    state,
                    revision=state.revision + 1,
                    intent="running",
                    recovery_required=True,
                    pending_operation_id=ext_op_id,
                ),
            )
            assert isinstance(state, BindingState)

            # Scheduler start/resume refuses to bypass recovery_required while pending_operation_id
            blocked = await scheduler.control(ALICE, ControlRequest(spec.binding_id, "resume", 1))
            assert isinstance(blocked, ports.ServiceUnavailable)

            # Target policy denied keeps recovery_required=True
            denied_rec = _make_recovery(database, resources, scheduler, target_ok=False)
            denied_res = await denied_rec.reconcile(
                ALICE,
                ReconcileRequest(binding_id=spec.binding_id, expected_generation=1),
                "rec-denied",
            )
            assert isinstance(denied_res, ports.ServiceUnavailable)

            # Uncertain external observation stays AMBIGUOUS and never replays app.start
            unknown_obs = EffectObservation(
                run.run_id,
                spec.target,
                1,
                EffectDisposition.UNKNOWN,
                (StageResult("applied", StageState.PENDING, "uncertain", ()),),
                (),
                False,
            )
            ambig_res = await rec.reconcile(
                ALICE,
                ReconcileRequest(
                    operation_id=ext_op_id,
                    binding_id=spec.binding_id,
                    expected_generation=1,
                    run_id=run.run_id,
                    observation=unknown_obs,
                ),
                "rec-ambig",
            )
            assert isinstance(ambig_res, ReconcileResult)
            assert ambig_res.status == "ambiguous"
            assert ambig_res.operation_state is ReceiptState.AMBIGUOUS
            assert ambig_res.binding is not None and ambig_res.binding.recovery_required is True
            assert app.starts == 0

            # Verified complete external observation advances applied_run_id and clears recovery
            pins = (
                ExpectedVersion(ResourceRef("run", run.run_id), run.prepared_digest),
                ExpectedVersion(ResourceRef("gridcraft_document", spec.target.document_id), "1"),
            )
            ev_ref = EvidenceRef(
                "ev-complete",
                "app_applied",
                ext_op_id,
                OperationKey("gridcraft.apply", "1"),
                pins,
                "a" * 64,
            )
            ev_reader.verified.add("ev-complete")
            complete_obs = EffectObservation(
                run.run_id,
                spec.target,
                1,
                EffectDisposition.APPLIED,
                (StageResult("applied", StageState.PASSED, "verified", (ev_ref,)),),
                (ev_ref,),
                True,
            )
            ok_res = await rec.reconcile(
                ALICE,
                ReconcileRequest(
                    operation_id=ext_op_id,
                    binding_id=spec.binding_id,
                    expected_generation=1,
                    run_id=run.run_id,
                    observation=complete_obs,
                ),
                "rec-ok",
            )
            assert isinstance(ok_res, ReconcileResult)
            assert ok_res.status == "reconciled"
            assert ok_res.operation_state is ReceiptState.COMPLETE
            assert ok_res.reconciliation_ref is not None
            assert ok_res.binding is not None
            assert ok_res.binding.recovery_required is False
            assert ok_res.binding.pending_operation_id is None
            assert ok_res.binding.applied_run_id == run.run_id
            assert ok_res.binding.applied_snapshot == run.snapshot
            assert ok_res.run == run
        finally:
            await scheduler.aclose()
            await database.close()

    asyncio.run(exercise())


def test_open_snapshot_application_exposes_runtime_reconcile_end_to_end(tmp_path: Path) -> None:
    class Policy:
        def owns(self, principal: Principal) -> bool:
            return principal == ALICE

        async def authorize(
            self, principal: Principal, action: ports.AccessAction
        ) -> ports.AccessDecision:
            _ = action
            return ports.AccessAllowed() if self.owns(principal) else ports.AccessDenied()

        async def probe(self) -> None:
            return None

    async def exercise() -> None:
        db_path = tmp_path / "host-reconcile.sqlite3"
        policy = Policy()
        boundary, _ = PrincipalBoundary.conformance(
            "127.0.0.1",
            ALICE.deployment_scope,
            (AuthenticatedIdentity("alice", frozenset()),),
            policy,
        )
        fp = CanonicalFingerprint()
        holder: list[tuple[Database, DurableResources]] = []

        def settings(database: Database, resources: DurableResources) -> HostSettings:
            holder.append((database, resources))
            return HostSettings(
                "127.0.0.1",
                ("127.0.0.1",),
                (),
                database.deployment.epoch,
                database.deployment.retention_profile,
                boundary,
                (
                    configure_snapshot(
                        resources,
                        owner_policy=policy.owns,
                        target_policy=lambda p, _t: policy.owns(p),
                    ),
                ),
            )

        async with open_snapshot_application(
            db_path,
            ALICE.deployment_scope,
            settings,
            codec=snapshot_codec(),
            fingerprint=fp,
            normalization_policy=fp.policy,
            owner_probes={"access": policy.probe, "capabilities": policy.probe},
        ) as app:
            database, resources = holder[0]
            await publish(resources, database)
            facade = app._lifetime.execution  # pyright: ignore[reportPrivateUsage]
            catalog = await facade.catalog(ALICE)
            assert "runtime.reconcile" in {op.key.name for op in catalog.operations}
            spec = replace(binding_spec(), feed_id=FEED.identity)
            bind_receipt = await facade.invoke(
                ALICE,
                InvocationEnvelope(
                    OperationKey("runtime.bind", "1"),
                    bind_codec().encode(BindRequest(spec, 0)),
                    "corr-1",
                    "bind-1",
                    (
                        ExpectedVersion(ResourceRef("binding", spec.binding_id), "absent"),
                        ExpectedVersion(FEED, "1"),
                    ),
                ),
            )
            assert isinstance(bind_receipt, Receipt)
            assert bind_receipt.state is ReceiptState.COMPLETE

            rec_req = ReconcileRequest(
                operation_id=bind_receipt.operation_id,
                binding_id=spec.binding_id,
                expected_generation=1,
            )
            rec_receipt = await facade.invoke(
                ALICE,
                InvocationEnvelope(
                    OperationKey("runtime.reconcile", "1"),
                    reconcile_codec().encode(rec_req),
                    "corr-2",
                    "recon-1",
                    (ExpectedVersion(ResourceRef("binding", spec.binding_id), "1"),),
                ),
            )
            assert isinstance(rec_receipt, Receipt)
            assert rec_receipt.state is ReceiptState.COMPLETE
            assert rec_receipt.result_availability is Availability.AVAILABLE

    asyncio.run(exercise())
