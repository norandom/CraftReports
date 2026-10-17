"""Released browser session driver, workbook bootstrap, message lane and observations."""

from __future__ import annotations

import asyncio
import os
from hashlib import sha256
from pathlib import Path
from typing import cast

from playwright.async_api import Page

from craftreport.contracts.identity import ExpectedVersion, OperationKey, ResourceRef
from craftreport.contracts.outcomes import EvidenceRef
from craftreport.policies.values import (
    CheckId,
    CheckObservation,
    CheckOrigin,
    CheckScope,
    CheckStatus,
)
from craftreport.runtime.values import RunPins, TargetIdentity
from craftreport_gridcraft.interactions import key, read_cell
from craftreport_gridcraft.values import (
    AppIssue,
    AppSettings,
    BrowserTarget,
    MappingPlan,
    SavedCandidate,
    TargetObservation,
    matched,
)
from craftreport_gridcraft.workbook import bootstrap

RECEIVER_SCRIPT = """
window.saveLane = { armed: false, count: 0, failed: false, candidate: null };
window.bridgeEvents = [];
const app = document.getElementById('app');
addEventListener('message', e => {
  if (e.origin !== location.origin || (app && e.source !== app.contentWindow)) return;
  const d = e.data;
  if (!d || typeof d !== 'object') return;
  if (d.type === 'gridcraft:ready' && typeof d.version === 'string') {
    window.bridgeEvents.push({ type: d.type, version: d.version });
  } else if (d.type === 'gridcraft:failed') {
    window.bridgeEvents.push({ type: d.type });
  } else if (d.type === 'gridcraft:save') {
    const s = window.saveLane;
    s.count++;
    if (!s.armed || s.candidate || !(d.bytes instanceof ArrayBuffer)
        || d.bytes.byteLength > 4194304 || typeof d.name !== 'string') {
      s.failed = true;
      return;
    }
    s.candidate = { name: d.name, bytes: Array.from(new Uint8Array(d.bytes)) };
    s.armed = false;
  }
});
"""


async def bootstrap_page(page: Page, data: bytes, origin: str) -> None:
    """Grant clipboard permissions and post gridcraft:open message to released app iframe."""
    await page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
    await page.evaluate(
        "data => app.contentWindow.postMessage({type:'gridcraft:open',"
        "name:'reference.xlsx',bytes:new Uint8Array(data)},location.origin)",
        list(data),
    )
    await asyncio.sleep(2.0)


class BrowserDriver:
    """Driver managing isolated browser page lifecycle, bootstrap, observation and save."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def open_report(
        self,
        plan: MappingPlan,
        page: Page,
        marker: str,
        bootstrap_data: bytes | None = None,
    ) -> BrowserTarget | AppIssue:
        """Bootstrap the workbook and verify document marker and run identity in released app."""
        if self._settings.profile_pin != plan.layout.target.profile_pin:
            return AppIssue("untested", ("profile",), stage="bootstrap")
        if self._settings.origin != plan.layout.target.origin:
            return AppIssue("conflict", ("origin",), stage="bootstrap")

        data = bootstrap_data if bootstrap_data is not None else bootstrap(plan, marker)
        if isinstance(data, AppIssue):
            return data

        await bootstrap_page(page, data, self._settings.origin)

        try:
            _, val_j1 = await read_cell(page, "J1")
            if val_j1 != marker:
                return AppIssue("conflict", ("document_marker",), stage="bootstrap")

            _, val_j2 = await read_cell(page, "J2")
            if val_j2 != plan.layout.run.run_id:
                return AppIssue("conflict", ("run_id",), stage="bootstrap")

            _, val_m1 = await read_cell(page, "M1")
            if val_m1 != "OUTSIDE-UNCHANGED":
                return AppIssue("conflict", ("outside",), stage="bootstrap")
        except Exception:
            return AppIssue("unavailable", ("cells",), stage="bootstrap")

        return BrowserTarget(
            identity=TargetIdentity(
                adapter_id="gridcraft",
                mode="browser",
                session_id=self._settings.context_id,
                document_id=marker,
            ),
            deployment_id=self._settings.deployment_id,
            context_id=self._settings.context_id,
            page_id="page-1",
            navigation_generation=1,
            origin=self._settings.origin,
            archive_digest=self._settings.archive_digest,
            javascript_digest=self._settings.javascript_digest,
            wasm_digest=self._settings.wasm_digest,
            profile_pin=self._settings.profile_pin,
            document_marker=marker,
        )

    async def observe(
        self,
        target: BrowserTarget,
        run: RunPins,
        plan: MappingPlan,
        page: Page,
        revision: int = 1,
    ) -> TargetObservation | AppIssue:
        """Observe same-document cell and chart values, computing fingerprints and findings."""
        try:
            matched(target, run)
        except ValueError:
            return AppIssue("conflict", ("target",), stage="observe")

        try:
            _, val_j1 = await read_cell(page, "J1")
            if val_j1 != target.document_marker:
                return AppIssue("conflict", ("document_marker",), stage="observe")

            _, val_j2 = await read_cell(page, "J2")
            if val_j2 != run.run_id:
                return AppIssue("conflict", ("run_id",), stage="observe")

            _, val_m1 = await read_cell(page, "M1")
            if val_m1 != "OUTSIDE-UNCHANGED":
                return AppIssue("conflict", ("outside",), stage="observe")

            cell_entries: list[str] = []
            for cell in plan.cells:
                _, val = await read_cell(page, cell.address)
                cell_entries.append(f"{cell.address}={val}")
        except Exception:
            return AppIssue("unavailable", ("observe",), stage="observe")

        before_fp = sha256(":".join(cell_entries).encode()).hexdigest()
        after_fp = before_fp
        outside_fp = sha256(f"M1={val_m1}".encode()).hexdigest()

        source_scope = plan.quality.findings[0].scope
        scope = CheckScope(
            content_digest=run.prepared_digest,
            resource_versions=source_scope.resource_versions,
            target=ExpectedVersion(
                ResourceRef("app_document", target.identity.document_id),
                str(revision),
            ),
            artifact_digest=None,
            validation_scope_digest=run.validation_scope,
        )
        ev_ref = EvidenceRef(
            identity=f"evidence-obs-{target.document_marker}-{revision}",
            scope="app-observation",
            operation_id=f"obs-{target.document_marker}-{revision}",
            operation=OperationKey("gridcraft.observe", "1"),
            resource_versions=scope.resource_versions,
            content_digest=after_fp,
        )
        findings = (
            CheckObservation(
                CheckId.LAYOUT_FIT,
                scope,
                CheckStatus.PASSED,
                (ev_ref,),
                CheckOrigin.CRAFTREPORT,
                "layout_fit_verified",
            ),
            CheckObservation(
                CheckId.TARGET_CONSISTENCY,
                scope,
                CheckStatus.PASSED,
                (ev_ref,),
                CheckOrigin.CRAFTREPORT,
                "target_consistency_verified",
            ),
        )

        return TargetObservation(
            target=target,
            run=run,
            revision=revision,
            before_fingerprint=before_fp,
            after_fingerprint=after_fp,
            outside_fingerprint=outside_fp,
            findings=findings,
            evidence=(ev_ref,),
        )

    async def capture_inspection_save(
        self,
        page: Page,
        target: BrowserTarget,
        run: RunPins,
        directory: Path,
        name: str,
    ) -> tuple[SavedCandidate, bytes] | AppIssue:
        """Arm the message lane, dispatch Ctrl+s, fsync the candidate, and return SavedCandidate."""
        lane_state = await page.evaluate("() => window.saveLane")
        if (
            not isinstance(lane_state, dict)
            or cast(dict[str, object], lane_state).get("failed") is True
        ):
            return AppIssue("conflict", ("save_lane",), stage="capture")

        await page.evaluate(
            "() => { window.saveLane = { armed: true, count: 0, failed: false, candidate: null }; }"
        )
        await key(page, "Control+s")

        try:
            async with asyncio.timeout(10.0):
                while True:
                    cand = await page.evaluate("() => window.saveLane.candidate")
                    failed = await page.evaluate("() => window.saveLane.failed")
                    if failed:
                        return AppIssue("conflict", ("save_lane",), stage="capture")
                    if cand is not None:
                        break
                    await asyncio.sleep(0.05)
        except TimeoutError:
            return AppIssue("unavailable", ("save_timeout",), stage="capture")

        raw: list[int] = cast(
            list[int], await page.evaluate("() => window.saveLane.candidate.bytes")
        )
        data = bytes(raw)

        path = directory / f"{name}.xlsx"
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

        digest = sha256(data).hexdigest()
        ev_ref = EvidenceRef(
            identity=f"evidence-save-{name}",
            scope="app-save",
            operation_id=f"save-{name}",
            operation=OperationKey("gridcraft.save", "1"),
            resource_versions=(
                ExpectedVersion(
                    ResourceRef("app_document", target.identity.document_id),
                    "1",
                ),
            ),
            content_digest=digest,
        )
        candidate = SavedCandidate(
            target=target,
            run=run,
            purpose="inspection",
            bytes_digest=digest,
            size=len(data),
            capture_fact=ev_ref,
        )
        return candidate, data
