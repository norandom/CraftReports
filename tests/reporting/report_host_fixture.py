"""Real host fixture; only authentication grants are test-owned."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from test_pack_reader import write_pack

from craftreport.adapters.canonical import CanonicalFingerprint
from craftreport.adapters.pack_reader import PackSource
from craftreport.adapters.snapshot_wire import content_digest, snapshot_codec
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.providers import DurableResources
from craftreport.application import ports
from craftreport.composition.app import HostedApplication
from craftreport.composition.reporting import ReportingActivation, configure_reporting
from craftreport.composition.settings import HostSettings
from craftreport.composition.snapshot_host import configure_snapshot, open_snapshot_application
from craftreport.contracts import (
    ExpectedVersion,
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    Principal,
    Receipt,
    ReceiptState,
    ResourceRef,
)
from craftreport.contracts.outcomes import ResultReadback
from craftreport.data.values import Snapshot
from craftreport.interfaces.principal import PrincipalBoundary

ALICE = Principal("report-host", "alice", frozenset({"source", "artifact"}))


class Owner:
    def owns(self, principal: Principal) -> bool:
        return principal.deployment_scope == ALICE.deployment_scope and principal.subject == "alice"

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        return ports.AccessAllowed() if self.owns(principal) else ports.AccessDenied()


async def available() -> None:
    return None


@dataclass
class ReportHost:
    app: HostedApplication
    activation: ReportingActivation
    resources: DurableResources
    facade: ports.Facade

    async def invoke(
        self,
        name: str,
        payload: JsonObject,
        retry: str | None = None,
        principal: Principal = ALICE,
        versions: tuple[ExpectedVersion, ...] = (),
    ) -> Receipt:
        receipt = await self.facade.invoke(
            principal, InvocationEnvelope(OperationKey(name, "1"), payload, "test", retry, versions)
        )
        assert isinstance(receipt, Receipt), receipt
        return receipt

    async def result(self, receipt: Receipt) -> JsonObject:
        assert receipt.result_ref is not None, receipt
        result = await self.facade.read_result(ALICE, receipt.operation_id)
        assert isinstance(result, ResultReadback), result
        assert result.value is not None, result
        return result.value

    async def publish(self, snapshot: Snapshot) -> JsonObject:
        payload = {
            key: value
            for key, value in snapshot_codec()
            .encode(replace(snapshot, content_digest=content_digest(snapshot)))
            .items()
            if key not in ("content_digest", "received_at", "accepted_at")
        }
        receipt = await self.invoke(
            "snapshot.publish",
            payload,
            f"publish-{snapshot.producer_version}",
            versions=(ExpectedVersion(ResourceRef("feed", snapshot.feed_id), "absent"),),
        )
        assert receipt.state is ReceiptState.COMPLETE, receipt
        result = await self.result(receipt)
        return cast(JsonObject, result["requested"])


@asynccontextmanager
async def report_host(tmp_path: Path, assets: dict[str, bytes]) -> AsyncGenerator[ReportHost]:
    root = tmp_path / "pack"
    write_pack(root, assets)
    owner = Owner()
    activations: list[ReportingActivation] = []
    providers: list[DurableResources] = []

    def reporting(database: Database, resources: DurableResources) -> ReportingActivation:
        activation = configure_reporting(
            resources, (PackSource(root, "source", "artifact"),), owner_policy=owner.owns
        )
        activations.append(activation)
        providers.append(resources)
        return activation

    def settings(database: Database, resources: DurableResources) -> HostSettings:
        return HostSettings(
            "127.0.0.1",
            ("127.0.0.1",),
            (),
            database.deployment.epoch,
            database.deployment.retention_profile,
            PrincipalBoundary(ALICE.deployment_scope, policy=owner),
            (configure_snapshot(resources, owner_policy=owner.owns),),
        )

    fingerprint = CanonicalFingerprint()
    async with open_snapshot_application(
        tmp_path / "report.sqlite3",
        ALICE.deployment_scope,
        settings,
        codec=snapshot_codec(),
        fingerprint=fingerprint,
        normalization_policy=fingerprint.policy,
        owner_probes={"access": available, "capabilities": available},
        reporting=reporting,
    ) as app:
        facade = app._lifetime.execution  # pyright: ignore[reportPrivateUsage]
        yield ReportHost(app, activations[0], providers[0], facade)
