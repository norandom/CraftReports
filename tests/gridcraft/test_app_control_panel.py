"""Tests for packaged native lifecycle controls and truthful freshness panel.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.1, 6.5.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Page, async_playwright

ROOT = Path(__file__).resolve().parents[2]
RESOURCES_DIR = ROOT / "packages/craftreport-gridcraft/resources"
HTML_PATH = RESOURCES_DIR / "report.html"
JS_PATH = RESOURCES_DIR / "report.js"


def test_control_panel_resource_files_exist_and_declared() -> None:
    """Requirement 6.1: Packaged control panel files exist at approved resource paths."""
    assert HTML_PATH.is_file(), f"Missing HTML at {HTML_PATH}"
    assert JS_PATH.is_file(), f"Missing JS at {JS_PATH}"

    # Verify resource paths are recorded in breadth.toml and quality.toml
    breadth_text = (ROOT / "breadth.toml").read_text(encoding="utf-8")
    quality_text = (ROOT / "quality.toml").read_text(encoding="utf-8")

    expected_html = "packages/craftreport-gridcraft/resources/report.html"
    expected_js = "packages/craftreport-gridcraft/resources/report.js"

    assert expected_html in breadth_text
    assert expected_js in breadth_text
    assert expected_html in quality_text
    assert expected_js in quality_text


def test_report_html_structure_and_accessibility() -> None:
    """Requirements 3.1, 3.2, 3.3: Native buttons, ARIA live region, and distinct facts."""
    html = HTML_PATH.read_text(encoding="utf-8")

    # Native labelled controls with accessible focus
    assert 'id="control-start"' in html
    assert 'id="control-pause"' in html
    assert 'id="control-resume"' in html
    assert 'id="control-stop"' in html
    assert "Start</button>" in html
    assert "Pause</button>" in html
    assert "Resume</button>" in html
    assert "Stop</button>" in html

    # Accessible status live region
    assert 'id="status-region"' in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html

    # Distinct facts displays (Req 3.2, 3.3, 3.8)
    assert 'id="refresh-interval"' in html
    assert 'id="apply-latency"' in html
    assert 'id="pending-work"' in html
    assert 'id="last-attempt-at"' in html
    assert 'id="last-completed-at"' in html
    assert 'id="latest-accepted-version"' in html
    assert 'id="latest-complete-accepted-version"' in html
    assert 'id="selected-run-id"' in html
    assert 'id="applied-version"' in html
    assert 'id="applied-at"' in html
    assert 'id="intent-state"' in html
    assert 'id="freshness-status"' in html
    assert 'id="freshness-measure"' in html
    assert 'id="outcome-status"' in html
    assert 'id="last-error"' in html

    # References report.js
    assert 'src="report.js"' in html


def test_report_js_gof_architecture_and_contract() -> None:
    """Validates GoF Command, Strategy, Observer, and Adapter design patterns in JS."""
    js = JS_PATH.read_text(encoding="utf-8")

    # Command Pattern
    assert "class LifecycleCommand" in js
    assert "class StartCommand" in js
    assert "class PauseCommand" in js
    assert "class ResumeCommand" in js
    assert "class StopCommand" in js
    assert "class CommandFactory" in js
    assert "runtime.control" in js

    # Strategy Pattern
    assert "class FreshnessStrategy" in js
    assert "evaluate(state" in js

    # Observer Pattern
    assert "class ReportStore" in js
    assert "class ReportView" in js
    assert "subscribe(" in js
    assert "notify(" in js

    # Gateway / Adapter Pattern
    assert "class RuntimeApiClient" in js
    assert "inspectBinding" in js

    # Pluggable Wiring / Test Hook
    assert "class ControlWiring" in js
    assert "setControlWiring" in js
    assert "__DISCONNECT_CONTROLS__" in js

    # No hardcoded credentials
    assert "password" not in js.lower()
    assert "secret" not in js.lower()


@pytest.fixture
async def browser_page() -> Any:
    """Headless Chromium page loaded with report.html."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        # file:// URL with forward slashes
        file_url = HTML_PATH.as_uri()
        await page.goto(file_url)
        yield page
        await browser.close()


@pytest.mark.anyio
async def test_control_panel_initial_state(browser_page: Page) -> None:
    """Requirements 3.2, 3.3, 3.8: Distinct facts and unknown for absent timestamps."""
    # 10s refresh interval exposed as configured cadence, distinct from apply latency
    interval = await browser_page.text_content("#refresh-interval")
    assert interval is not None and "10s" in interval and "cadence" in interval

    # Apply latency is unknown initially, not 0
    latency = await browser_page.text_content("#apply-latency")
    assert latency == "unknown"

    # Absent timestamps display "unknown", NEVER "0" or "1970-01-01"
    for sel in ("#last-attempt-at", "#last-completed-at", "#applied-at"):
        val = await browser_page.text_content(sel)
        assert val == "unknown", f"Expected unknown for {sel}, got {val}"

    # Absent versions display unknown
    for sel in (
        "#latest-accepted-version",
        "#latest-complete-accepted-version",
        "#applied-version",
    ):
        val = await browser_page.text_content(sel)
        assert val == "unknown", f"Expected unknown for {sel}, got {val}"

    # Initial intent is stopped
    intent = await browser_page.text_content("#intent-state")
    assert intent == "stopped"

    # Freshness is unknown with no timestamp recorded
    freshness = await browser_page.text_content("#freshness-status")
    assert freshness is not None and "unknown" in freshness
    measure = await browser_page.text_content("#freshness-measure")
    assert measure == "no_timestamp_recorded"

    # Button initial states: Start enabled, Pause/Resume/Stop disabled
    assert not await browser_page.is_disabled("#control-start")
    assert await browser_page.is_disabled("#control-pause")
    assert await browser_page.is_disabled("#control-resume")
    assert await browser_page.is_disabled("#control-stop")


@pytest.mark.anyio
async def test_control_panel_lifecycle_state_transitions(browser_page: Page) -> None:
    """Requirements 3.1, 3.4, 3.5, 3.6, 3.7: Start, pause-pending, pause, resume, stop."""
    # 1. Simulate transition to running (Start)
    running_state = {
        "generation": "1",
        "revision": "1",
        "intent": "running",
        "pause_pending": False,
        "selected_run_id": "run-101",
        "applied_snapshot": {"version": 1, "created_at": "2026-10-18T10:00:00Z"},
        "latest_complete_snapshot": {"version": 1},
        "last_attempt_at": "2026-10-18T10:00:00Z",
        "last_completed_at": "2026-10-18T10:00:01Z",
    }
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(running_state)})"
    )

    assert await browser_page.text_content("#intent-state") == "running"
    assert await browser_page.text_content("#selected-run-id") == "run-101"
    assert await browser_page.text_content("#applied-version") == "1"
    assert await browser_page.text_content("#apply-latency") == "1000ms"
    # Buttons when running
    assert await browser_page.is_disabled("#control-start")
    assert not await browser_page.is_disabled("#control-pause")
    assert await browser_page.is_disabled("#control-resume")
    assert not await browser_page.is_disabled("#control-stop")

    # 2. Simulate Pause requested while in-flight mutation is active (Req 3.4)
    # Immediately prevents new mutation starts and displays "pause pending"
    await browser_page.evaluate("window.reportApp.store.setPausePending(true)")
    assert await browser_page.text_content("#intent-state") == "pause pending"
    assert await browser_page.text_content("#pending-work") == "pause pending"
    status_text = await browser_page.text_content("#status-region")
    assert status_text is not None and "pause" in status_text.lower()
    # In pause pending, pause and start buttons are disabled
    assert await browser_page.is_disabled("#control-start")
    assert await browser_page.is_disabled("#control-pause")

    # 3. In-flight mutation finishes; publications continue during pause (Req 3.5)
    # Visible document content retained; latest complete accepted version exposed separately
    paused_state = {
        "generation": "1",
        "revision": "2",
        "intent": "paused",
        "pause_pending": False,
        "applied_snapshot": {"version": 1, "created_at": "2026-10-18T10:00:00Z"},
        "latest_complete_snapshot": {"version": 3},
        "latest_accepted_snapshot": {"version": 4},
        "last_completed_at": "2026-10-18T10:00:01Z",
    }
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(paused_state)})"
    )

    assert await browser_page.text_content("#intent-state") == "paused"
    assert await browser_page.text_content("#applied-version") == "1"
    assert await browser_page.text_content("#latest-complete-accepted-version") == "3"
    assert await browser_page.text_content("#latest-accepted-version") == "4"
    # Buttons when paused
    assert not await browser_page.is_disabled("#control-resume")
    assert await browser_page.is_disabled("#control-pause")

    # 4. Resume applies highest complete producer version (Req 3.6)
    resumed_state = {
        "generation": "1",
        "revision": "3",
        "intent": "running",
        "applied_snapshot": {"version": 3, "created_at": "2026-10-18T10:05:00Z"},
        "latest_complete_snapshot": {"version": 3},
        "last_completed_at": "2026-10-18T10:05:01Z",
    }
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(resumed_state)})"
    )
    assert await browser_page.text_content("#intent-state") == "running"
    assert await browser_page.text_content("#applied-version") == "3"

    # 5. Stop completes (Req 3.7)
    stopped_state = {
        "generation": "2",
        "revision": "4",
        "intent": "stopped",
        "last_effect": "partial",
        "applied_snapshot": {"version": 3, "created_at": "2026-10-18T10:05:00Z"},
        "last_completed_at": "2026-10-18T10:05:01Z",
    }
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(stopped_state)})"
    )
    assert await browser_page.text_content("#intent-state") == "stopped"
    assert await browser_page.text_content("#outcome-status") == "partial"
    assert not await browser_page.is_disabled("#control-start")
    assert await browser_page.is_disabled("#control-stop")


@pytest.mark.anyio
async def test_control_panel_truthful_freshness(browser_page: Page) -> None:
    """Requirement 3.8: Truthful freshness calculation and triggering measures."""
    # 1. Fresh state: age within configured 30s threshold
    fresh_state = {
        "intent": "running",
        "applied_snapshot": {"version": 1, "created_at": "2026-10-18T12:00:00Z"},
        "last_completed_at": "2026-10-18T12:00:00Z",
    }
    # Provide nowMs as 12:00:10Z (10 seconds later, <= 30s)
    now_ms = 1792324810000  # 2026-10-18T12:00:10.000Z
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(fresh_state)}, {now_ms})"
    )
    freshness = await browser_page.text_content("#freshness-status")
    assert freshness is not None and "fresh" in freshness
    measure = await browser_page.text_content("#freshness-measure")
    assert measure is not None and "age: 10s <= 30s" in measure

    # 2. Stale state: age exceeds 30s threshold
    now_stale_ms = 1792324845000  # 45 seconds later (> 30s)
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(fresh_state)}, {now_stale_ms})"
    )
    freshness = await browser_page.text_content("#freshness-status")
    assert freshness is not None and "stale" in freshness
    measure = await browser_page.text_content("#freshness-measure")
    assert measure is not None and "last_applied_age: 45s exceeds threshold 30s" in measure

    # 3. Error / failed effect state: stale regardless of age
    failed_state = {
        "intent": "running",
        "last_effect": "failed",
        "last_error": "target_timeout",
        "applied_snapshot": {"version": 1, "created_at": "2026-10-18T12:00:00Z"},
        "last_completed_at": "2026-10-18T12:00:00Z",
    }
    await browser_page.evaluate(
        f"window.reportApp.store.updateFromBindingState({json.dumps(failed_state)}, {now_ms})"
    )
    freshness = await browser_page.text_content("#freshness-status")
    assert freshness is not None and "stale" in freshness
    measure = await browser_page.text_content("#freshness-measure")
    assert measure is not None and "target_timeout" in measure


@pytest.mark.anyio
async def test_deliberately_disconnected_control_fails_and_restores(browser_page: Page) -> None:
    """Requirement 6.5: A deliberately disconnected control must fail its critical test

    before restoring and proving the correct wiring.
    """
    # 1. Deliberately disconnect control wiring
    await browser_page.evaluate("window.reportApp.setControlWiring(false)")
    assert await browser_page.evaluate("window.reportApp.wiring.isWired()") is False

    # Intercept custom disconnected event
    await browser_page.evaluate(
        """
        window.__DISCONNECTED_EVENT_FIRED = false;
        document.addEventListener('control:disconnected', (e) => {
            window.__DISCONNECTED_EVENT_FIRED = true;
            window.__DISCONNECTED_ACTION = e.detail.action;
        });
        """
    )

    # 2. Click the Start button while disconnected
    await browser_page.click("#control-start")

    # Assert that the disconnected control FAILS to advance intent and records error
    event_fired = await browser_page.evaluate("window.__DISCONNECTED_EVENT_FIRED")
    action = await browser_page.evaluate("window.__DISCONNECTED_ACTION")
    assert event_fired is True
    assert action == "start"

    # Intent remains stopped (it failed to dispatch command)
    intent = await browser_page.text_content("#intent-state")
    assert intent == "stopped"

    # Last error and freshness show the disconnected failure
    last_error = await browser_page.text_content("#last-error")
    assert last_error is not None and "disconnected" in last_error.lower()

    # 3. Now RESTORE the correct wiring
    await browser_page.evaluate("window.reportApp.setControlWiring(true)")
    assert await browser_page.evaluate("window.reportApp.wiring.isWired()") is True

    # Mock the API client's invoke method to simulate successful server response
    await browser_page.evaluate(
        """
        window.reportApp.apiClient.invoke = async (envelope) => {
            window.__LAST_INVOKED_ENVELOPE = envelope;
            return {
                proposal: {
                    value: {
                        generation: "1",
                        revision: "1",
                        intent: "running",
                        pause_pending: false
                    }
                }
            };
        };
        """
    )

    # 4. Click Start again with restored wiring
    await browser_page.click("#control-start")

    # Assert that command was properly dispatched
    last_envelope = await browser_page.evaluate("window.__LAST_INVOKED_ENVELOPE")
    assert last_envelope is not None
    assert last_envelope["operation"]["name"] == "runtime.control"
    assert last_envelope["payload"]["action"] == "start"
    assert last_envelope["payload"]["binding_id"] == "binding-1"

    # State has successfully transitioned to running
    assert await browser_page.text_content("#intent-state") == "running"
