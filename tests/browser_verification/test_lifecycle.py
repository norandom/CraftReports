"""Resource-specific closure and retained SDK lifetime regressions."""

import asyncio
import json
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from playwright.async_api import Browser, BrowserContext, Playwright

from scripts.browser_verification import browser, contracts, journey, packet
from scripts.browser_verification.lifecycle import Handle, SDKKind, SDKResources, protected
from scripts.browser_verification.visual_profile import VisualProfile

from .test_artifacts import EXPECTED
from .test_packet import inputs_for


def closed(**changes: object) -> contracts.CleanupFinding:
    return contracts.CleanupFinding.model_validate(
        dict(
            resource_id=uuid4(),
            owner_run=uuid4(),
            identity="exact-context",
            resource_kind="context",
            status="sdk-closed",
            acquisition_state="acquired",
            acquisition_task_state="succeeded",
            close_task_state="succeeded",
            acquisition_id=uuid4(),
            close_id=uuid4(),
            mechanism="public-close",
            started=1.0,
            deadline=5.0,
            finished=2.0,
            sdk_identity="playwright==1.64.0",
            declared_limitations=("playwright_internal_force_unobservable",),
            final_video_state="finalized",
        )
        | changes
    )


def test_v2_acceptance_is_resource_specific() -> None:
    assert closed().accepted
    for change in (
        {"resource_kind": "process"},
        {"resource_kind": None},
        {"status": "graceful"},
        {"requested_force": True},
        {"observed_force": True},
        {"unexpected_disconnect": True},
        {"acquisition_state": "unsettled"},
        {"close_id": None},
        {"acquisition_id": None},
        {"sdk_identity": None},
        {"declared_limitations": ()},
        {"finished": None},
        {"finished": 6.0},
        {"final_video_state": "unfinished"},
    ):
        assert not closed(**change).accepted, change


def test_native_exit_cannot_use_sdk_evidence() -> None:
    native = closed(
        resource_kind="process",
        native_pid=123,
        status="graceful",
        exit_status=0,
        mechanism="observed-exit",
        sdk_identity=None,
        declared_limitations=(),
    )
    assert native.accepted
    assert not native.model_copy(update={"exit_status": None}).accepted


def test_cancelled_late_acquisition_and_repeated_cancel_are_settled() -> None:
    async def exercise() -> None:
        registry = journey.ResourceRegistry(uuid4())
        owner = SDKResources(registry)
        release = asyncio.Event()
        handle = cast(BrowserContext, AsyncMock(spec=BrowserContext))

        async def acquire() -> BrowserContext:
            await release.wait()
            return handle

        task = asyncio.create_task(owner.acquire("context", "late-context", acquire()))
        await asyncio.sleep(0)
        assert registry.tokens[0].acquisition == "partial"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        cleanup = asyncio.create_task(protected(owner.close_all(2)))
        await asyncio.sleep(0)
        for _ in range(4):
            cleanup.cancel()
            await asyncio.sleep(0)
        await cleanup
        assert registry.tokens[0].close_state == "sdk-closed"
        assert registry.findings[0].accepted
        cast(AsyncMock, handle.close).assert_awaited_once()

    asyncio.run(exercise())


@pytest.mark.parametrize("fault", ["acquire", "close", "kind", "disconnect", "exception"])
def test_unsettled_or_failed_sdk_work_cannot_be_rehabilitated(fault: str) -> None:
    async def exercise() -> None:
        registry = journey.ResourceRegistry(uuid4())
        owner = SDKResources(registry)
        released = asyncio.Event()
        handle = cast(BrowserContext, AsyncMock(spec=BrowserContext))

        async def operation() -> BrowserContext:
            if fault == "acquire":
                await released.wait()
            return handle

        async def closing() -> None:
            if fault == "exception":
                raise ValueError("safe-failure")
            if fault == "close":
                await released.wait()

        cast(AsyncMock, handle.close).side_effect = closing
        acquisition = asyncio.create_task(
            owner.acquire("browser" if fault == "kind" else "context", "exact-handle", operation())
        )
        await asyncio.sleep(0)
        if fault == "acquire":
            acquisition.cancel()
            with pytest.raises(asyncio.CancelledError):
                await acquisition
        else:
            await acquisition
        if fault == "disconnect":
            owner.unexpected_disconnect = True
        await protected(owner.close_all(0.01))
        finding = registry.findings[0]
        assert not finding.accepted
        assert owner.entries[0].task is not None and owner.entries[0].close_id
        released.set()
        await asyncio.sleep(0)
        await owner.close_all(1)
        assert registry.findings == (finding,)
        if fault in ("acquire", "close"):
            assert finding.status == "timed-out"
        else:
            assert finding.status == "failed" or finding.unexpected_disconnect

    asyncio.run(exercise())


def test_cleanup_order_and_independent_failure() -> None:
    async def exercise() -> None:
        registry = journey.ResourceRegistry(uuid4())
        owner = SDKResources(registry)
        order: list[str] = []
        for kind, cls in (
            ("driver", Playwright),
            ("browser", Browser),
            ("decode-context", BrowserContext),
            ("context", BrowserContext),
        ):
            handle = AsyncMock(spec=cls)
            if kind == "browser":
                handle.is_connected.return_value = True

            async def result(h: Handle = cast(Handle, handle)) -> Handle:
                return h

            async def close(k: str = kind) -> None:
                order.append(k)
                if k == "context":
                    raise ValueError("context-close-failed")

            (handle.stop if kind == "driver" else handle.close).side_effect = close
            await owner.acquire(cast(SDKKind, kind), kind, result())
        await protected(owner.close_all(2))
        assert order == ["context", "decode-context", "browser", "driver"]
        assert registry.findings[0].status == "failed"
        assert all(f.accepted for f in registry.findings[1:])

    asyncio.run(exercise())


def test_packet_requires_exact_identity_and_retains_v1_semantics(tmp_path: Path) -> None:
    inputs = inputs_for(tmp_path)
    registry = journey.ResourceRegistry(inputs.config.run_id)
    token = registry.register("context", "exact-context")
    registry.mark_acquired(token.token_id)
    finding = closed(
        resource_id=token.token_id, owner_run=registry.run_id, acquisition_id=token.acquisition_id
    )
    registry.record_finding(finding)
    result = journey.RoundTripResult(cleanup=(finding,))
    packet.reconcile_cleanup(inputs, result, registry.tokens)
    for change in (
        {"close_id": uuid4()},
        {"acquisition_id": uuid4()},
        {"resource_kind": "driver"},
        {"resource_id": uuid4()},
    ):
        with pytest.raises(ValueError):
            packet.reconcile_cleanup(
                inputs,
                result.model_copy(update={"cleanup": (finding.model_copy(update=change),)}),
                registry.tokens,
            )
    final = packet.finalize(inputs, result, registry.tokens)
    assert final.schema_version == 2 and final.declared_limitations
    old = contracts.RunResult.model_validate(final.model_dump() | {"schema_version": 1})
    assert old.lifecycle_contract == "historical-v1" and old.declared_limitations == ()


def test_journey_keeps_primary_cancellation_and_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs = inputs_for(tmp_path)
    registry = journey.ResourceRegistry(inputs.config.run_id)
    failure = closed(owner_run=registry.run_id, status="failed")
    count = 0

    async def cancel(*_: object) -> contracts.Outcome[browser.ReadyPage]:
        raise asyncio.CancelledError

    async def cleanup(*_: object, **__: object) -> tuple[contracts.CleanupFinding, ...]:
        nonlocal count
        count += 1
        return (failure,) if count == 1 else ()

    monkeypatch.setattr(browser, "start", cancel)
    monkeypatch.setattr(browser, "close", cleanup)
    result = asyncio.run(
        journey.recorded_workbook(
            inputs.config,
            inputs.deployment,
            registry,
            tmp_path / "unused.xlsx",
            EXPECTED,
            cast(VisualProfile, object()),
            journey.RoundTripResult(),
            False,
            browser.BrowserState(registry),
        )
    )
    assert result.primary and result.primary.finding.stage == "cancellation"
    assert result.cleanup == (failure,) and count == 2
    assert json.loads((inputs.config.run_directory / "roundtrip.json").read_text())["primary"]


def test_request_cancel_interrupts_watched_journey() -> None:
    async def exercise() -> None:
        registry = journey.ResourceRegistry(uuid4())
        entered = asyncio.Event()

        async def run() -> None:
            registry.watch()
            entered.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(run())
        await entered.wait()
        registry.request_cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert registry.cancel_requested

    asyncio.run(exercise())
