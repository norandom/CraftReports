"""Released browser session driver, workbook bootstrap, message lane and observations."""

from __future__ import annotations

import asyncio
import os
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

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
from craftreport_gridcraft.interactions import clipboard_encoding, key, read_cell, type_cell
from craftreport_gridcraft.values import (
    AppIssue,
    AppSettings,
    BrowserTarget,
    Cell,
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


def _marker_addrs(plan: MappingPlan) -> tuple[str, str]:
    return ("K1", "K2") if any(c.address == "K1" for c in plan.cells) else ("J1", "J2")


def _expected_cell_text(address: str, value: str | int | None) -> str:
    if value is None:
        return ""
    raw = f"{value}.00" if type(value) is int else str(value)
    return clipboard_encoding(raw, merged=address == "A3")


async def _verify_identity(
    page: Page,
    plan: MappingPlan,
    marker: str,
    run_id: str,
    stage: Literal["bootstrap", "observe", "mutate", "capture", "reopen"],
    effect: Literal["none", "partial", "unknown"] = "none",
) -> str | AppIssue:
    m_addr, r_addr = _marker_addrs(plan)
    try:
        _, val_m = await read_cell(page, m_addr)
        _, val_r = await read_cell(page, r_addr)
        _, val_out = await read_cell(page, "M1")
    except Exception:
        return AppIssue("unavailable", ("cells",), stage=stage, effect=effect)
    if val_m != marker:
        return AppIssue("conflict", ("document_marker",), stage=stage, effect=effect)
    if val_r != run_id:
        return AppIssue("conflict", ("run_id",), stage=stage, effect=effect)
    if val_out != "OUTSIDE-UNCHANGED":
        return AppIssue("conflict", ("outside",), stage=stage, effect=effect)
    return sha256(f"M1={val_out}".encode()).hexdigest()


async def _read_cells(
    page: Page,
    cells: tuple[Cell, ...],
    stage: Literal["observe", "mutate", "reopen"],
    effect: Literal["none", "partial", "unknown"] = "none",
) -> tuple[dict[str, str], str] | AppIssue:
    try:
        vals = {c.address: (await read_cell(page, c.address))[1] for c in cells}
    except Exception:
        return AppIssue("unavailable", (stage,), stage=stage, effect=effect)
    fp = sha256(":".join(f"{c.address}={vals[c.address]}" for c in cells).encode()).hexdigest()
    return vals, fp


def _build_observation(
    target: BrowserTarget,
    run: RunPins,
    plan: MappingPlan,
    revision: int,
    before_fp: str,
    after_fp: str,
    outside_fp: str,
    op_name: str = "gridcraft.observe",
) -> TargetObservation:
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
        operation=OperationKey(op_name, "1"),
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
        target, run, revision, before_fp, after_fp, outside_fp, findings, (ev_ref,)
    )


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
    """Driver managing isolated browser lifecycle, bootstrap, observation, mutation and save."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._lanes: dict[str, asyncio.Lock] = {}

    def _lane(self, document_id: str) -> asyncio.Lock:
        return self._lanes.setdefault(document_id, asyncio.Lock())

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

        async with self._lane(marker):
            await bootstrap_page(page, data, self._settings.origin)
            checked = await _verify_identity(
                page, plan, marker, plan.layout.run.run_id, "bootstrap"
            )
            if isinstance(checked, AppIssue):
                return checked

        return BrowserTarget(
            TargetIdentity("gridcraft", "browser", self._settings.context_id, marker),
            self._settings.deployment_id,
            self._settings.context_id,
            "page-1",
            1,
            self._settings.origin,
            self._settings.archive_digest,
            self._settings.javascript_digest,
            self._settings.wasm_digest,
            self._settings.profile_pin,
            marker,
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

        async with self._lane(target.identity.document_id):
            outside_fp = await _verify_identity(
                page, plan, target.document_marker, run.run_id, "observe"
            )
            if isinstance(outside_fp, AppIssue):
                return outside_fp
            read_res = await _read_cells(page, plan.cells, "observe")
            if isinstance(read_res, AppIssue):
                return read_res
            _, fp = read_res

        return _build_observation(target, run, plan, revision, fp, fp, outside_fp)

    async def _dispatch_and_verify(
        self, page: Page, plan: MappingPlan, current_vals: dict[str, str], marker: str, run_id: str
    ) -> tuple[str, str] | AppIssue:
        dispatched = False
        try:
            for cell in plan.cells:
                expected = _expected_cell_text(cell.address, cell.value)
                if current_vals.get(cell.address) != expected and cell.value is not None:
                    dispatched = True
                    await type_cell(page, cell.address, cell.value)
        except Exception:
            eff_err: Literal["none", "unknown"] = "unknown" if dispatched else "none"
            return AppIssue("unavailable", ("mutate",), stage="mutate", effect=eff_err)

        eff: Literal["none", "partial"] = "partial" if dispatched else "none"
        outside_fp = await _verify_identity(page, plan, marker, run_id, "mutate", eff)
        if isinstance(outside_fp, AppIssue):
            return outside_fp
        post = await _read_cells(page, plan.cells, "mutate", "unknown" if dispatched else "none")
        if isinstance(post, AppIssue):
            return post
        vals, after_fp = post
        for cell in plan.cells:
            expected = _expected_cell_text(cell.address, cell.value)
            if vals[cell.address] not in (expected, str(cell.value or "")):
                return AppIssue("conflict", ("cells", cell.address), stage="mutate", effect=eff)
        return after_fp, outside_fp

    async def apply(
        self,
        plan: MappingPlan,
        run: RunPins,
        before: TargetObservation,
        page: Page,
        before_plan: MappingPlan | None = None,
    ) -> TargetObservation | AppIssue:
        """Apply pinned content through one guarded document lane with before/after checks."""
        try:
            matched(before.target, run)
            matched(plan.layout.target, run)
        except ValueError:
            return AppIssue("conflict", ("target",), stage="mutate", effect="none")
        if plan.layout.target != before.target or plan.layout.run != run:
            return AppIssue("conflict", ("pins",), stage="mutate", effect="none")

        async with self._lane(before.target.identity.document_id):
            outside_fp = await _verify_identity(
                page, plan, before.target.document_marker, before.run.run_id, "mutate"
            )
            if isinstance(outside_fp, AppIssue):
                return outside_fp
            if outside_fp != before.outside_fingerprint:
                return AppIssue("conflict", ("outside",), stage="mutate", effect="none")

            check_cells = before_plan.cells if before_plan is not None else plan.cells
            pre = await _read_cells(page, check_cells, "mutate")
            if isinstance(pre, AppIssue):
                return pre
            current_vals, pre_fp = pre
            if pre_fp != before.after_fingerprint:
                return AppIssue("conflict", ("before_fingerprint",), stage="mutate", effect="none")

            res = await self._dispatch_and_verify(
                page, plan, current_vals, before.target.document_marker, run.run_id
            )
            if isinstance(res, AppIssue):
                return res
            after_fp, after_out = res

        return _build_observation(
            before.target,
            run,
            plan,
            before.revision + 1,
            before.after_fingerprint,
            after_fp,
            after_out,
            "gridcraft.apply",
        )

    async def _extract_candidate(self, page: Page) -> bytes | AppIssue:
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
                    if await page.evaluate("() => window.saveLane.failed"):
                        return AppIssue("conflict", ("save_lane",), stage="capture")
                    if cand is not None:
                        break
                    await asyncio.sleep(0.05)
        except TimeoutError:
            return AppIssue("unavailable", ("save_timeout",), stage="capture")
        final_lane = await page.evaluate("() => window.saveLane")
        if (
            isinstance(final_lane, dict)
            and cast(dict[str, object], final_lane).get("count", 1) != 1
        ):
            return AppIssue("conflict", ("save_lane",), stage="capture")
        raw: list[int] = cast(
            list[int], await page.evaluate("() => window.saveLane.candidate.bytes")
        )
        return bytes(raw)

    async def capture_inspection_save(
        self,
        page: Page,
        target: BrowserTarget,
        run: RunPins,
        directory: Path,
        name: str,
    ) -> tuple[SavedCandidate, bytes] | AppIssue:
        """Arm the message lane, dispatch Ctrl+s, fsync the candidate, and return SavedCandidate."""
        async with self._lane(target.identity.document_id):
            res = await self._extract_candidate(page)
            if isinstance(res, AppIssue):
                return res
            data = res
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
                ExpectedVersion(ResourceRef("app_document", target.identity.document_id), "1"),
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

    async def capture_export_save(
        self,
        page: Page,
        target: BrowserTarget,
        run: RunPins,
        plan: MappingPlan,
        name: str = "export",
    ) -> tuple[SavedCandidate, bytes] | AppIssue:
        """Hold document lane, precheck live run, capture candidate, and release lane."""
        try:
            matched(target, run)
            matched(plan.layout.target, run)
        except ValueError:
            return AppIssue("conflict", ("target",), stage="capture")

        async with self._lane(target.identity.document_id):
            checked = await _verify_identity(
                page, plan, target.document_marker, run.run_id, "capture"
            )
            if isinstance(checked, AppIssue):
                return checked
            res = await self._extract_candidate(page)
            if isinstance(res, AppIssue):
                return res
            data = res

        digest = sha256(data).hexdigest()
        ev_ref = EvidenceRef(
            identity=f"evidence-export-{name}",
            scope="app-save",
            operation_id=f"export-{name}",
            operation=OperationKey("gridcraft.save", "1"),
            resource_versions=(
                ExpectedVersion(ResourceRef("app_document", target.identity.document_id), "1"),
            ),
            content_digest=digest,
        )
        candidate = SavedCandidate(
            target=target,
            run=run,
            purpose="export",
            bytes_digest=digest,
            size=len(data),
            capture_fact=ev_ref,
        )
        return candidate, data

    async def reopen(
        self,
        page: Page,
        data: bytes,
        plan: MappingPlan,
        marker: str,
        run_id: str,
    ) -> tuple[str, str] | AppIssue:
        """Open exact bytes in verifier page and assert marker, run, cells, sentinel."""
        await bootstrap_page(page, data, self._settings.origin)
        outside_fp = await _verify_identity(page, plan, marker, run_id, "reopen")
        if isinstance(outside_fp, AppIssue):
            return outside_fp
        read_res = await _read_cells(page, plan.cells, "reopen")
        if isinstance(read_res, AppIssue):
            return read_res
        vals, after_fp = read_res
        for cell in plan.cells:
            expected = _expected_cell_text(cell.address, cell.value)
            if vals.get(cell.address) not in (expected, str(cell.value or "")):
                return AppIssue("conflict", ("cells", cell.address), stage="reopen")
        return after_fp, outside_fp
