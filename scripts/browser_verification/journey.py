"""Immediate acquisition ownership foundation; runtime orchestration follows later."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from . import browser, chart_interactions, interactions, persistence, visual, xlsx
from .config import Bounds, RunConfig
from .contracts import (
    ActionReceipt,
    ArtifactCheckSet,
    ArtifactIdentity,
    CheckSet,
    CleanupFinding,
    InspectedArtifact,
    Outcome,
    Rejected,
    Succeeded,
    TargetIdentity,
    Text,
    Value,
)
from .deployment import DeploymentLease
from .evidence import VideoEvidence
from .fixture import FixtureExpectation
from .visual_profile import ChartObservation, VisualProfile

ResourceKind = Literal["deployment", "process", "driver", "browser", "context", "connection"]
CloseState = Literal["pending", "graceful", "forced", "failed"]


class ResourceToken(Value):
    token_id: UUID
    kind: ResourceKind
    owner_run: UUID
    identity: Text
    acquisition: Literal["partial", "acquired"] = "partial"
    close_state: CloseState = "pending"


class ResourceRegistry:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self._tokens: dict[UUID, ResourceToken] = {}
        self._cancel_requested = False

    def register(self, kind: ResourceKind, identity: str) -> ResourceToken:
        """Call immediately on acquisition, before any setup or readiness await."""
        token = ResourceToken(token_id=uuid4(), kind=kind, owner_run=self.run_id, identity=identity)
        if any(item.kind == kind and item.identity == token.identity for item in self.tokens):
            raise ValueError("resource is already registered")
        self._tokens[token.token_id] = token
        return token

    @property
    def tokens(self) -> tuple[ResourceToken, ...]:
        return tuple(self._tokens.values())

    @property
    def pending_cleanup(self) -> tuple[ResourceToken, ...]:
        return tuple(
            item for item in reversed(self.tokens) if item.close_state in ("pending", "failed")
        )

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    def request_cancel(self) -> None:
        """Retain supported cancellation intent without discarding late acquisitions."""
        self._cancel_requested = True

    def mark_acquired(self, token_id: UUID) -> ResourceToken:
        token = self._tokens[token_id]
        if token.close_state != "pending":
            raise ValueError("closed or cleanup-attempted resource cannot become acquired")
        updated = ResourceToken.model_validate(token.model_dump() | {"acquisition": "acquired"})
        self._tokens[token_id] = updated
        return updated

    def record_close(
        self, token_id: UUID, state: Literal["graceful", "forced", "failed"]
    ) -> ResourceToken:
        token = self._tokens[token_id]
        if token.close_state in ("graceful", "forced"):
            raise ValueError("resource close is already finalized")
        updated = ResourceToken.model_validate(token.model_dump() | {"close_state": state})
        self._tokens[token_id] = updated
        return updated


class StartupResult(Value):
    """A readiness receipt, deliberately not a verified workbook journey."""

    run_id: UUID
    bounds: Bounds
    headed: bool
    readiness: Outcome[browser.ReadyPage]
    cleanup: tuple[CleanupFinding, ...]
    resources: tuple[ResourceToken, ...]
    video: VideoEvidence | None
    unexecuted: tuple[str, ...] = (
        "visible-mutation",
        "persistence",
        "byte-inspection",
        "browser-reopen",
    )


async def startup(
    config: RunConfig, lease: DeploymentLease, registry: ResourceRegistry
) -> StartupResult:
    """Exercise startup and retain evidence on either path; caller owns deployment."""
    state = browser.BrowserState(registry)
    config.run_directory.mkdir(parents=True, exist_ok=True)
    try:
        readiness = await browser.start(config, lease, state)
    finally:
        cleanup = await browser.close(config, state)
        if state.diagnostics:
            state.diagnostics.write(config.run_directory / "diagnostics.json")
    result = StartupResult(
        run_id=config.run_id,
        bounds=config.bounds,
        headed=config.headed,
        readiness=readiness,
        cleanup=cleanup,
        resources=registry.tokens,
        video=state.video,
    )
    (config.run_directory / "startup.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    return result


class RoundTripResult(Value):
    """Scoped roundtrip observations; final feature verdict remains a later gate."""

    artifact: Outcome[ArtifactIdentity] | None = None
    inspection: Outcome[ArtifactCheckSet] | None = None
    reopened: Outcome[TargetIdentity] | None = None
    charts: tuple[ChartObservation, ...] = ()
    checks: tuple[CheckSet, ...] = ()
    primary: Rejected | None = None
    cleanup: tuple[CleanupFinding, ...] = ()
    videos: tuple[VideoEvidence, ...] = ()
    readiness: tuple[Outcome[browser.ReadyPage], ...] = ()
    receipts: tuple[ActionReceipt, ...] = ()
    diagnostics: tuple[browser.Diagnostic, ...] = ()


async def chart_check(
    driver: interactions.BrowserDriver,
    target: TargetIdentity,
    phase: Literal["before", "after"],
    profile: VisualProfile,
    source: InspectedArtifact | None = None,
) -> tuple[Outcome[ChartObservation], CheckSet | None]:
    observed = await chart_interactions.observe_chart(driver, target, phase, profile)
    checks = (
        visual.compare_visual(observed.payload, profile, driver.expected, source)
        if isinstance(observed, Succeeded)
        else None
    )
    return observed, checks


def reopen_source(
    result: RoundTripResult, expected: FixtureExpectation
) -> InspectedArtifact | None:
    if not isinstance(result.artifact, Succeeded) or not isinstance(result.inspection, Succeeded):
        return None
    if not result.inspection.payload.passed:
        return None
    return InspectedArtifact(
        artifact=result.artifact.payload,
        inspection=result.inspection.payload,
        fixture_sha256=expected.fixture.sha256,
    )


async def workbook_stages(
    driver: interactions.BrowserDriver,
    result: RoundTripResult,
    fixture: Path,
    profile: VisualProfile,
    reopening: bool,
) -> RoundTripResult:
    expected = driver.expected
    source = reopen_source(result, expected)
    artifact = source.artifact if source else None
    opened = await driver.open(artifact.destination if artifact else fixture, source)
    if isinstance(opened, Rejected):
        return result.model_copy(update={"primary": opened})
    if reopening:
        result = result.model_copy(update={"reopened": opened})
    else:
        observed, checks = await chart_check(driver, opened.payload, "before", profile)
        result = add_chart(result, observed, checks)
        if result.primary or not all(i.passed for i in result.checks):
            return result
        edited = await driver.edit(
            interactions.CellEdit(
                target=opened.payload,
                address="B3",
                before=expected.edit.before,
                after=expected.edit.after,
                dispatch_id=uuid4(),
            )
        )
        if isinstance(edited, Rejected):
            return result.model_copy(update={"primary": edited})
    observed, checks = await chart_check(driver, opened.payload, "after", profile, source)
    result = add_chart(result, observed, checks)
    if reopening:
        await driver.reopened_checkpoint(opened.payload)
        return result
    if result.primary or not all(i.passed for i in result.checks):
        return result
    saved = await persistence.save(driver, opened.payload)
    result = result.model_copy(update={"artifact": saved})
    if isinstance(saved, Rejected):
        return result.model_copy(update={"primary": saved})
    inspected = xlsx.inspect_artifact(saved.payload, expected)
    return result.model_copy(
        update={
            "inspection": inspected,
            "primary": inspected if isinstance(inspected, Rejected) else None,
        }
    )


def add_chart(
    result: RoundTripResult, observed: Outcome[ChartObservation], checks: CheckSet | None
) -> RoundTripResult:
    if isinstance(observed, Rejected):
        return result.model_copy(update={"primary": observed})
    assert checks
    return result.model_copy(
        update={"charts": (*result.charts, observed.payload), "checks": (*result.checks, checks)}
    )


async def recorded_workbook(
    config: RunConfig,
    lease: DeploymentLease,
    registry: ResourceRegistry,
    fixture: Path,
    expected: FixtureExpectation,
    profile: VisualProfile,
    result: RoundTripResult,
    reopening: bool,
    state: browser.BrowserState,
) -> RoundTripResult:
    config.run_directory.mkdir(parents=True, exist_ok=True)
    driver: interactions.BrowserDriver | None = None
    try:
        ready = await browser.start(config, lease, state)
        result = result.model_copy(update={"readiness": (*result.readiness, ready)})
        if isinstance(ready, Rejected):
            result = result.model_copy(update={"primary": ready})
        else:
            driver = interactions.BrowserDriver(config, state, ready.payload, expected)
            result = await workbook_stages(driver, result, fixture, profile, reopening)
    finally:
        cleanup = await browser.close(
            config,
            state,
            retain_browser=not reopening
            and isinstance(result.inspection, Succeeded)
            and result.inspection.payload.passed,
        )
        if not reopening and any(i.status != "graceful" for i in cleanup):
            cleanup += await browser.close(config, state)
        result = result.model_copy(
            update={
                "cleanup": (*result.cleanup, *cleanup),
                "videos": (*result.videos, state.video) if state.video else result.videos,
            }
        )
        if state.diagnostics:
            result = result.model_copy(
                update={"diagnostics": (*result.diagnostics, *state.diagnostics.events)}
            )
            state.diagnostics.write(config.run_directory / "diagnostics.json")
        if driver:
            result = result.model_copy(update={"receipts": (*result.receipts, *driver.receipts)})
            (config.run_directory / "interactions.json").write_text(
                json.dumps(
                    {
                        "receipts": [i.model_dump(mode="json") for i in driver.receipts],
                        "observations": [i.model_dump(mode="json") for i in driver.observations],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        (config.run_directory / "roundtrip.json").write_text(
            result.model_dump_json(indent=2), encoding="utf-8"
        )
    return result


async def roundtrip(
    config: RunConfig,
    lease: DeploymentLease,
    registry: ResourceRegistry,
    fixture: Path,
    expected: FixtureExpectation,
    profile: VisualProfile,
) -> RoundTripResult:
    """Coordinate real adapters with separate initial/reopen recording contexts."""
    state = browser.BrowserState(registry)
    result = await recorded_workbook(
        config, lease, registry, fixture, expected, profile, RoundTripResult(), False, state
    )
    if (
        result.primary
        or not isinstance(result.inspection, Succeeded)
        or not result.inspection.payload.passed
        or not all(i.status == "graceful" for i in result.cleanup)
    ):
        return result
    state.next_context()
    reopen_config = config.model_copy(update={"output_root": config.run_directory / "reopen"})
    result = await recorded_workbook(
        reopen_config, lease, registry, fixture, expected, profile, result, True, state
    )
    (config.run_directory / "roundtrip.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8"
    )
    return result
