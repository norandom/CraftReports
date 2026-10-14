"""Explicit temporary providers for the installed kernel acceptance process."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from craftreport_kernel_fixture import factory
from craftreport_kernel_fixture.lifecycle import FixtureServices
from craftreport_kernel_fixture.models import SETTINGS, Settings
from fixture_dispatch import FixtureHealth, FixtureResults
from fixture_execution import FixtureHandoffs
from fixture_journal import FixtureJournal
from fixture_services import (
    AccessGrant,
    CapabilitySupport,
    FixtureAccessPolicy,
    FixtureCapabilities,
    FixtureEvidence,
)
from fixture_target import SyntheticTarget
from kernel_faults import FaultControls

from craftreport.application import ports
from craftreport.application.capabilities import CapabilityFactory
from craftreport.composition.settings import GuaranteeProviders, HostSettings, configure
from craftreport.contracts import (
    Availability,
    CapabilityVersion,
    CommandIntent,
    EffectDisposition,
    EvidenceRef,
    EvidenceStatus,
    JsonObject,
    OperationKey,
    Receipt,
    ResourceRef,
    RetryKey,
    StageState,
)
from craftreport.contracts.capabilities import ExecutionLimits
from craftreport.interfaces.principal import AuthenticatedIdentity, PrincipalBoundary

RESOURCE = ResourceRef("synthetic", "target-1")


class LeaseJournal(FixtureJournal):
    """Pin a newly admitted receipt to the exact target-owned execution lease."""

    def __init__(self, target: SyntheticTarget, controls: FaultControls) -> None:
        super().__init__()
        self.target = target
        self.controls = controls
        self.admissions: dict[ports.GuardLease, Receipt] = {}

    async def find(self, key: RetryKey) -> ports.RetainedCommand | ports.Missing:
        result = await super().find(key)
        await self.controls.initial_find()
        return result

    def admission_proofs(self) -> list[dict[str, object]]:
        return [
            {
                "operation_id": receipt.operation_id,
                "revision": receipt.revision,
                "epoch": receipt.deployment_epoch,
                "lease_id": str(id(lease)),
                "lease_active": lease is self.target.active_lease,
            }
            for lease, receipt in self.admissions.items()
        ]

    def receipts(self) -> list[dict[str, object]]:
        return [
            {
                "operation_id": receipt.operation_id,
                "revision": receipt.revision,
                "state": receipt.state.value,
                "epoch": receipt.deployment_epoch,
            }
            for receipt in self._receipts.values()
        ]

    async def admit(self, intent: CommandIntent) -> ports.Admission:
        result = await super().admit(intent)
        if isinstance(result, ports.Admitted):
            lease = self.target.active_lease
            if lease is None:
                raise RuntimeError("Admission requires an active synthetic lease")
            self.admissions[lease] = result.receipt
        return result


class ReadbackEffects:
    def __init__(self, journal: LeaseJournal, evidence: FixtureEvidence) -> None:
        self.journal = journal
        self.target = journal.target
        self.evidence = evidence

    async def apply(
        self, resource: ResourceRef, change: JsonObject, guard: ports.GuardLease
    ) -> ports.ResourceEffectResult:
        receipt = self.journal.admissions.get(guard)
        if receipt is None or resource not in receipt.resources:
            return ports.GuardLost()
        observed = await self.target.apply(resource, change, guard)
        if not isinstance(observed, ports.ResourceEffect):
            return observed
        if observed.effect is not EffectDisposition.APPLIED:
            return observed
        snapshot = await self.target.read(resource)
        if not isinstance(snapshot, ports.ResourceSnapshot) or snapshot.content != change:
            raise RuntimeError("Synthetic readback disagrees with effect")
        digest = sha256(json.dumps(dict(snapshot.content), sort_keys=True).encode()).hexdigest()
        reference = EvidenceRef(
            "fixture-readback",
            "synthetic-temporary",
            receipt.operation_id,
            receipt.operation,
            observed.versions,
            digest,
        )
        faults = self.journal.controls.faults
        if "skip_evidence" not in faults:
            self.evidence.retain(
                EvidenceStatus(reference, Availability.AVAILABLE, StageState.PASSED)
            )
        if "evidence_after_effect" in faults:
            self.evidence.available = False
        if "journal_after_effect" in faults:
            self.journal.available = False
        return replace(observed, evidence=(reference,))


class Providers:
    def __init__(
        self,
        run_dir: Path,
        failure: str | None,
        *,
        boundary_probe: bool = False,
        capability_probe: bool = False,
        execution: ExecutionLimits = ExecutionLimits(),
        guard_timeout: float = 2.0,
    ) -> None:
        self.boundary_probe = boundary_probe
        self.capability_probe = capability_probe
        self.execution = execution
        self.controls = FaultControls()
        self.run_dir = run_dir
        self.failure = failure
        self.events: list[str] = []
        self.closed = False
        self.final_target: dict[str, object] = {}
        self.target = SyntheticTarget({RESOURCE: {"value": "before"}})
        self.target.acquisition_timeout = guard_timeout
        self.journal = LeaseJournal(self.target, self.controls)
        self.evidence = FixtureEvidence()
        self.capabilities = FixtureCapabilities(
            (
                CapabilitySupport(
                    CapabilityVersion("synthetic-target", "1.0.0"), frozenset({"native"})
                ),
            ),
            {RESOURCE: "native"},
        )
        self.results = FixtureResults()
        self.handoffs = FixtureHandoffs()
        scopes = frozenset({"read", "write", "catalog", "inspect"})
        self.identities = (
            AuthenticatedIdentity("alice", scopes),
            AuthenticatedIdentity("bob", frozenset({"catalog", "inspect"})),
        )
        self.access = FixtureAccessPolicy(
            self.journal,
            tuple(
                AccessGrant(
                    "deployment",
                    identity.subject,
                    identity.permitted_scopes,
                    frozenset({RESOURCE}) if identity.subject == "alice" else frozenset(),
                    True,
                )
                for identity in self.identities
            ),
            {
                OperationKey("synthetic.read", "1"): "read",
                OperationKey("synthetic.write", "1"): "write",
                OperationKey("synthetic.probe", "1"): "write",
                # Authorize resolution of an unsupported version independently of visibility denial.
                OperationKey("synthetic.write", "2"): "write",
            },
        )

    async def observe(self, result_ref: str | None = None) -> dict[str, object]:
        snapshot = await self.target.read(RESOURCE)
        if not isinstance(snapshot, ports.ResourceSnapshot):
            raise RuntimeError("Independent target unavailable")
        value = snapshot.content["value"]
        if not isinstance(value, str):
            raise RuntimeError("Independent target value invalid")
        return {
            "admissions": self.journal.admission_proofs(),
            "receipts": self.journal.receipts(),
            "epoch": self.journal.epoch,
            "resource": RESOURCE.identity,
            "value": value,
            "version": snapshot.version.version,
            "effect_count": self.target.effect_count,
            "result": next(
                (
                    dict(value)
                    for key, value in self.results.values.items()
                    if key[:2] == ("deployment", "alice") and key[3] == result_ref
                ),
                None,
            ),
        }

    def record(self, capability: str, event: str) -> None:
        self.events.append(event)

    def adapt(self, loaded: object) -> CapabilityFactory[FixtureServices, Settings]:
        if loaded is not factory:
            raise TypeError("Unexpected installed fixture entry point")
        return factory(boundary_probe=self.boundary_probe, capability_probe=self.capability_probe)

    def settings(self, port: int) -> tuple[HostSettings, dict[str, str]]:
        principal, credentials = PrincipalBoundary.conformance(
            "127.0.0.1", "deployment", self.identities, self.access
        )
        selection = configure(
            "craftreport-kernel-fixture",
            "synthetic",
            self.adapt,
            FixtureServices(self),
            SETTINGS,
            {
                "resource_kind": "synthetic",
                "fail_open": self.failure == "startup",
                "fail_close": self.failure == "cleanup",
            },
        )
        settings = HostSettings(
            "127.0.0.1",
            (f"127.0.0.1:{port}",),
            (f"http://127.0.0.1:{port}",),
            self.journal.epoch,
            self.journal.retention_profile,
            principal,
            (selection,),
            execution=self.execution,
        )
        return settings, {item.identity.subject: item.token for item in credentials}

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[GuaranteeProviders]:
        health = FixtureHealth(
            {
                "access": lambda: self.access.available,
                "journal": lambda: self.journal.available,
                "resources": lambda: self.target.available,
                "effects": lambda: self.target.available,
                "guard": lambda: self.target.available,
                "evidence": lambda: self.evidence.available,
                "capabilities": lambda: self.capabilities.available,
                "results": lambda: self.results.available,
            }
        )
        for name, probe in tuple(health.probes.items()):
            health.probes[name] = lambda name=name, probe=probe: self.controls.health.get(
                name, probe()
            )
        try:
            yield GuaranteeProviders(
                self.journal,
                self.target,
                self.evidence,
                self.capabilities,
                self.target,
                ReadbackEffects(self.journal, self.evidence),
                self.results,
                self.handoffs,
                health,
            )
        finally:
            if self.target.available:
                self.final_target = {"availability": "available", **await self.observe()}
            else:
                self.final_target = {
                    "availability": "unavailable",
                    "epoch": self.journal.epoch,
                    "resource": RESOURCE.identity,
                    "effect_count": self.target.effect_count,
                }
            self.closed = True

    def write_cleanup(self, code: int) -> None:
        payload = {
            "providers_closed": self.closed,
            "receipts": self.journal.receipts(),
            "admissions": self.journal.admission_proofs(),
            "final_target": self.final_target,
            "plugin_events": self.events,
            "effect_count": self.target.effect_count,
            "status": "closed" if code == 0 else "failed",
            "code": code,
        }
        (self.run_dir / "cleanup.json").write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8"
        )
