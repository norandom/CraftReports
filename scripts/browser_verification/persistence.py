"""BrowserDriver-owned exclusive download persistence."""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from playwright.async_api import Error

from .contracts import ArtifactIdentity, Outcome, Rejected, Succeeded, TargetIdentity
from .interactions import BrowserDriver, TargetMismatch, key, title


def persist(source: Path, destination: Path) -> tuple[int, str]:
    with source.open("rb") as stream:
        data = stream.read(4_000_001)
    if not 0 < len(data) <= 4_000_000:
        raise ValueError("download-size-invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    retained = destination.read_bytes()
    if retained != data:
        raise ValueError("persisted-bytes-mismatch")
    return len(retained), hashlib.sha256(retained).hexdigest()


async def save(driver: BrowserDriver, target: TargetIdentity) -> Outcome[ArtifactIdentity]:
    """Arm the download event before one genuine released Save shortcut."""
    try:
        driver.guard(target)
        if driver.save_attempted:
            raise TargetMismatch("save-already-attempted")
        if driver.config.destination.exists():
            raise TargetMismatch("destination-conflict")
        if not driver.ready.picker.absent:
            raise TargetMismatch("download-route-unavailable")
        assert driver.state.diagnostics
        driver.state.diagnostics.stage = "persistence"
        async with asyncio.timeout(driver.config.bounds.action):
            await driver.observe(driver.checks(target, "after"))
            if driver.document_title != await title(driver.page):
                raise TargetMismatch("document-title-mismatch")
            driver.guard(target)
            driver.receipt(target, "save", uuid4())
            driver.save_attempted = True
            async with driver.page.expect_download() as pending:
                await key(driver.page, "Control+s")
            download = await pending.value
            path = await download.path()
            if await download.failure():
                raise ValueError("download-file-unavailable")
            driver.guard(target)
            size, digest = persist(path, driver.config.destination)
            artifact = ArtifactIdentity(
                artifact_id=uuid4(),
                destination=driver.config.destination,
                size=size,
                sha256=digest,
                target=target,
                route="download",
            )
            checkpoint = driver.config.run_directory / "persisted.png"
            await driver.page.screenshot(path=str(checkpoint))
            driver.guard(target)
            driver.receipts[-1] = driver.receipts[-1].model_copy(
                update={
                    "status": "observed",
                    "observation_refs": (str(artifact.destination), str(checkpoint)),
                }
            )
            return Succeeded[ArtifactIdentity](payload=artifact)
    except (Error, OSError, ValueError, TimeoutError) as error:
        if isinstance(error, FileExistsError):
            error = TargetMismatch("destination-conflict")
        rejected = await driver.rejected("persistence", error)
        return Rejected(
            finding=rejected.finding.model_copy(
                update={"requirements": ("4.1", "4.2", "4.3", "4.4")}
            )
        )
