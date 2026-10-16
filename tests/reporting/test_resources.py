"""Focused execution of prototype against actual pack and durable collaborators."""

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest
from test_pack_reader import assets as assets
from test_pack_reader import definition as definition
from test_pack_reader import theme as theme
from test_pack_reader import write_pack

from craftreport.adapters.pack_reader import ConfiguredPackReader, PackSource
from craftreport.adapters.report_codecs import decode_definition, encode_definition
from craftreport.adapters.report_resources import (
    PreparationFactWriter,
    ReportAccessPolicy,
    ReportResources,
)
from craftreport.adapters.storage.database import Database
from craftreport.adapters.storage.evidence import DurableEvidence
from craftreport.adapters.storage.guard import DurableGuard
from craftreport.adapters.storage.results import DurableResults
from craftreport.application import ports
from craftreport.contracts import Availability, EvidenceRef, OperationKey, Principal, ResourceRef
from craftreport.policies.values import CheckId, CheckOrigin, CheckStatus, ExternalStatement
from craftreport.reporting.ports import PreparationCheck, PreparationDecision, PreparationFact
from tests.snapshot_runtime.installed_host import OwnerPolicy
from tests.snapshot_runtime.test_evidence import reference
from tests.snapshot_runtime.test_providers import FEED, provider, publish


class StatementOwnerPolicy(OwnerPolicy):
    """Operator-owned visibility decision, independent of statement assurance."""

    def __init__(self, decision: ports.AccessDecision) -> None:
        self.decision = decision
        self.receipts: list[str] = []

    async def authorize(
        self, principal: Principal, action: ports.AccessAction
    ) -> ports.AccessDecision:
        original = await super().authorize(principal, action)
        if isinstance(original, ports.AccessAllowed) and isinstance(action, ports.ReceiptAccess):
            self.receipts.append(action.operation_id)
            return self.decision
        return original


@pytest.mark.parametrize(
    "decision", [ports.AccessAllowed(), ports.AccessDenied(), ports.ServiceUnavailable("access")]
)
def test_statement_reference_visibility(
    tmp_path: Path, assets: dict[str, bytes], decision: ports.AccessDecision
) -> None:
    ref = EvidenceRef(
        "external",
        "compliance",
        "external-operation",
        OperationKey("external.check", "1"),
        (),
        "a" * 64,
    )
    statement = ExternalStatement(
        "Private statement",
        "Supplied scope",
        "Issuer",
        (ref, replace(ref, identity="external-two")),
    )
    definition = replace(
        decode_definition(assets["definition.json"]), compliance_statement=statement
    )
    assets = {
        **assets,
        "definition.json": encode_definition(definition),
        "template.json": encode_definition(definition),
    }
    write_pack(tmp_path / "pack", assets)
    sources = (PackSource(tmp_path / "pack", "source", "artifact"),)

    async def exercise() -> None:
        database = Database(tmp_path / "statement.db", "installed-snapshot")
        resources = ReportResources(ConfiguredPackReader(sources), sources, provider(database))
        upstream = StatementOwnerPolicy(decision)
        policy = ReportAccessPolicy(upstream, resources)
        principal = Principal("installed-snapshot", "alice", frozenset({"source", "artifact"}))
        action = ports.OperationAccess(
            OperationKey("reports.prepare", "1"), tuple(resources.observations)
        )
        assert isinstance(
            await policy.authorize(replace(principal, subject="other"), action), ports.AccessDenied
        )
        assert upstream.receipts == []
        assert await policy.authorize(principal, action) == decision
        assert upstream.receipts == ["external-operation"]
        await database.close()

    asyncio.run(exercise())


def test_pack_and_original_guard(tmp_path: Path, assets: dict[str, bytes]) -> None:
    root = tmp_path / "pack"
    write_pack(root, assets)

    async def exercise() -> None:
        database = Database(tmp_path / "packs.db", "deployment-a")
        sources = (PackSource(root, "source", "artifact"),)
        resources = ReportResources(ConfiguredPackReader(sources), sources, provider(database))
        assert len(resources.observations) == 2
        assert await resources.health() is None
        pins = tuple(value.version for value in resources.observations.values())
        guard = DurableGuard(database, resources.combined_read)
        resources.upstream.guard = guard
        async with guard.acquire(pins) as lease:
            assert guard.capture("original-operation", pins) is lease
            assert isinstance(await lease.assert_current(), ports.GuardCurrent)
        with pytest.raises(ports.GuardAcquisitionError):
            async with guard.acquire((replace(pins[0], version="changed"),)):
                pytest.fail("Changed pack pin acquired")
        for resource, observed in resources.observations.items():
            assert await resources.read(resource) == observed
            assert str(root) not in str(observed.content)
        assert isinstance(
            await resources.read(ResourceRef("report_pack_source", "absent")), ports.Missing
        )
        assert isinstance(await resources.read(ResourceRef("snapshot", "absent:1")), ports.Missing)
        (root / "theme.json").write_bytes(b"changed")
        assert await resources.health() is None
        assert tuple(value.version for value in resources.observations.values()) == pins
        with pytest.raises(TypeError):
            resources.observations[pins[0].resource] = resources.observations[pins[1].resource]  # pyright: ignore[reportIndexIssue]
        assert isinstance(await publish(resources.upstream, database), ports.ResourceEffect)
        snapshot = ResourceRef("snapshot", FEED.identity + ":1")
        assert await resources.read(snapshot) == await resources.upstream.read(snapshot)
        with pytest.raises(TypeError):
            resources.observations[pins[0].resource].content["pack"] = {}  # pyright: ignore[reportIndexIssue]
        nested = resources.observations[pins[0].resource].content["pack"]
        assert isinstance(nested, Mapping)
        with pytest.raises(TypeError):
            nested["identity"] = "changed"  # pyright: ignore[reportIndexIssue]
        empty = ReportResources(ConfiguredPackReader(()), (), resources.upstream)
        assert await empty.health() == ports.ServiceUnavailable("report_packs")
        await database.close()
        assert isinstance(await resources.read(snapshot), ports.ServiceUnavailable)

    asyncio.run(exercise())


def test_separate_pack_scope_grants(tmp_path: Path, assets: dict[str, bytes]) -> None:
    write_pack(tmp_path / "pack", assets)
    sources = (PackSource(tmp_path / "pack", "source", "artifact"),)

    async def exercise() -> None:
        database = Database(tmp_path / "grants.db", "installed-snapshot")
        resources = ReportResources(ConfiguredPackReader(sources), sources, provider(database))
        policy = ReportAccessPolicy(OwnerPolicy(), resources)
        principal = Principal("installed-snapshot", "alice", frozenset({"source", "artifact"}))
        action = ports.OperationAccess(
            OperationKey("reports.prepare", "1"), tuple(resources.observations)
        )
        assert isinstance(await policy.authorize(principal, action), ports.AccessAllowed)
        for scopes in (frozenset({"source"}), frozenset({"artifact"}), frozenset[str]()):
            assert isinstance(
                await policy.authorize(replace(principal, permitted_scopes=scopes), action),
                ports.AccessDenied,
            )
        assert isinstance(
            await policy.authorize(replace(principal, subject="other"), action), ports.AccessDenied
        )
        assert isinstance(
            await policy.authorize(
                principal,
                replace(action, resources=(ResourceRef("report_pack_source", "unknown"),)),
            ),
            ports.AccessDenied,
        )
        assert isinstance(
            await policy.authorize(principal, ports.CatalogAccess()), ports.AccessAllowed
        )
        for resource in action.resources:
            scope = "source" if resource.kind == "report_pack_source" else "artifact"
            assert isinstance(
                await policy.authorize(
                    replace(principal, permitted_scopes=frozenset({scope})),
                    replace(action, resources=(resource,)),
                ),
                ports.AccessAllowed,
            )
        await database.close()

    asyncio.run(exercise())


@pytest.mark.parametrize("stage", ["prepared", "quality_evaluated"])
@pytest.mark.parametrize("preconditions", [True, False])
def test_fact_readback_and_restart(
    tmp_path: Path, stage: Literal["prepared", "quality_evaluated"], preconditions: bool
) -> None:
    async def exercise() -> None:
        path = tmp_path / "facts.db"
        database = Database(path, "deployment-a")
        original = await reference(database, stage, preconditions=preconditions)
        count = 3 if stage == "prepared" else 9
        checks = tuple(
            PreparationCheck(
                check,
                CheckStatus.PASSED if index < 3 else CheckStatus.UNEVALUATED,
                CheckOrigin.CRAFTREPORT,
                "observed",
            )
            for index, check in enumerate(tuple(CheckId)[:count])
        )
        decision = (
            None
            if stage == "prepared"
            else PreparationDecision("validated", True, False, (CheckId.LAYOUT_FIT,))
        )
        fact = PreparationFact(
            original.operation_id,
            original.operation,
            original.resource_versions,
            "1",
            stage,
            "d" * 64,
            "e" * 64,
            checks,
            decision,
        )
        writer = PreparationFactWriter(DurableResults(database))
        stored = await writer.record(fact)
        assert not isinstance(stored, ports.ServiceUnavailable)
        assert stored.content_digest == original.content_digest
        assert stored.resource_versions == original.resource_versions
        assert isinstance(
            await writer.record(replace(fact, resource_versions=fact.resource_versions[:2])),
            ports.ServiceUnavailable,
        )
        await database.close()
        reopened = Database(path, "deployment-a")
        statuses = await DurableEvidence(reopened).inspect((stored,))
        assert statuses[0].availability is Availability.AVAILABLE
        await reopened.close()

    asyncio.run(exercise())
