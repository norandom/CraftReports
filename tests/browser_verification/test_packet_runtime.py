"""Current-source headless packet, failure, and finalized recording evidence."""

import asyncio
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from scripts.browser_verification import (
    deployment,
    interactions,
    journey,
    packet,
    release,
    visual_profile,
)
from scripts.browser_verification.config import Bounds, OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import CheckSet, Succeeded
from scripts.browser_verification.evidence import decode_video
from scripts.browser_verification.fixture import FixtureExpectation

from .test_roundtrip_runtime import FIXTURE, ROOT

pytestmark = pytest.mark.integration


def prove_missing_open_reopen_files(
    inputs: packet.PacketInputs, result: journey.RoundTripResult, registry: journey.ResourceRegistry
) -> None:
    original = inputs.config.run_directory
    proof: list[dict[str, str]] = []
    for action in ("open", "reopen", "cell"):
        output = original.parent / ("missing-" + action)
        clone = output / original.name
        shutil.copytree(original, clone)
        old, new = json.dumps(str(original))[1:-1], json.dumps(str(clone))[1:-1]
        for path in clone.rglob("*.json"):
            path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        copied = journey.RoundTripResult.model_validate_json(
            result.model_dump_json().replace(old, new)
        )
        cloned_inputs = inputs.model_copy(
            update={"config": inputs.config.model_copy(update={"output_root": output})}
        )
        # A healthy clone passes before the one referenced file is removed.
        packet.verify_files(cloned_inputs, copied, registry.tokens)
        if action == "cell":
            missing = Path(
                packet.interaction_records(copied)[0].observations[0].cells[0].screenshot
            )
        else:
            receipt = next(r for r in copied.receipts if r.action == action)
            missing = Path(receipt.observation_refs[0])
        missing.unlink()
        final = packet.finalize(cloned_inputs, copied, registry.tokens)
        assert final.verdict != "VERIFIED", (action, missing)
        assert any(f.stage == "evidence" and f.status == "failed" for f in final.findings)
        proof.append(
            {"action": action, "missing_reference": str(missing), "verdict": final.verdict}
        )
    (original.parent / ("missing-receipt-files-" + original.name + ".json")).write_text(
        json.dumps(proof, indent=2), encoding="utf-8"
    )


def prove_negative_invariants(
    inputs: packet.PacketInputs, result: journey.RoundTripResult, registry: journey.ResourceRegistry
) -> None:
    cases = [
        result.model_copy(update={"videos": (result.videos[0], result.videos[0])}),
        result.model_copy(update={"videos": result.videos[:1]}),
    ]
    for changed in cases:
        with pytest.raises(ValueError):
            packet.verify_videos(changed, registry.tokens)
    changed = result.model_copy(update={"checks": (*result.checks[:2], CheckSet())})
    with pytest.raises(ValueError):
        packet.validate_associations(inputs, changed)
    changed = result.model_copy(
        update={
            "cleanup": (
                result.cleanup[0].model_copy(update={"status": "forced"}),
                *result.cleanup[1:],
            )
        }
    )
    with pytest.raises(ValueError):
        packet.reconcile_cleanup(inputs, changed, registry.tokens)
    assert isinstance(result.reopened, Succeeded)
    changed = result.model_copy(
        update={"charts": (result.charts[0], result.charts[1], result.charts[1])}
    )
    with pytest.raises(ValueError):
        packet.validate_associations(inputs, changed)


async def independently_decode_and_truncate(result: journey.RoundTripResult, root: Path) -> None:
    root.mkdir(parents=True)
    registry = journey.ResourceRegistry(result.cleanup[0].owner_run)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            for video in result.videos:
                observed = await decode_video(browser, Path(video.content.path), registry)
                assert observed.decoded_frame and observed.content == video.content
            source = Path(result.videos[0].content.path).read_bytes()
            truncated = root / "tail-truncated.webm"
            truncated.write_bytes(source[:-100])
            with pytest.raises(ValueError, match="truncated-webm"):
                await decode_video(browser, truncated, registry)
        finally:
            await browser.close()
    assert not registry.pending_cleanup


@pytest.mark.parametrize("disconnected", [True, False], ids=["challenge", "recovery"])
def test_current_headless_final_packet(disconnected: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    if disconnected:

        async def suppress(driver: interactions.BrowserDriver, edit: interactions.CellEdit) -> None:
            pass

        monkeypatch.setattr(interactions.BrowserDriver, "dispatch_edit", suppress)
    root = Path(
        os.environ.get(
            "CRAFTREPORT_BROWSER_EVIDENCE",
            str(ROOT / "artifacts/browser-verification/task-4.1/acceptance"),
        )
    ).resolve()
    config = RunConfig(
        deployment=OwnedDeployment(
            mode="owned-wsl" if platform.system() == "Windows" else "owned-linux"
        ),
        output_root=root,
        headed=False,
        bounds=Bounds(action=60, cleanup=60),
    )
    config.run_directory.mkdir(parents=True)
    paths = sorted(
        [
            *(ROOT / "scripts/browser_verification").glob("*.py"),
            *(ROOT / "tests/browser_verification").glob("*.py"),
            *(ROOT / "tests/fixtures/browser_verification").rglob("*.json"),
            *(ROOT / "tests/fixtures/browser_verification").rglob("*.png"),
            FIXTURE / "reference.xlsx",
            ROOT / "uv.lock",
            ROOT / ".kiro/specs/craftreport-browser-verification/requirements.md",
            ROOT / ".kiro/specs/craftreport-browser-verification/design.md",
        ]
    )
    frozen = tuple(packet.hash_content(path) for path in paths)
    selected = release.resolve_release(config)
    assert isinstance(selected, Succeeded), selected
    (config.run_directory / "release.json").write_text(
        selected.model_dump_json(indent=2), encoding="utf-8"
    )
    bundle = release.acquire(selected.payload, ROOT / "artifacts/browser-verification/cache")
    assert isinstance(bundle, Succeeded), bundle
    (config.run_directory / "bundle.json").write_text(
        bundle.model_dump_json(indent=2), encoding="utf-8"
    )
    frozen = (
        *frozen,
        packet.hash_content(bundle.payload.archive),
        *(packet.hash_content(bundle.payload.root / f.path) for f in bundle.payload.files),
    )
    (config.run_directory / "source-freeze.json").write_text(
        json.dumps([f.model_dump(mode="json") for f in frozen], indent=2), encoding="utf-8"
    )
    registry = journey.ResourceRegistry(config.run_id)
    state = deployment.DeploymentState(registry)
    result = journey.RoundTripResult()
    prepared = None
    try:
        prepared = deployment.prepare(config, bundle.payload, state)
        assert isinstance(prepared, Succeeded), prepared
        result = asyncio.run(
            journey.roundtrip(
                config,
                prepared.payload,
                registry,
                FIXTURE / "reference.xlsx",
                FixtureExpectation.read(FIXTURE / "expected.json"),
                visual_profile.VisualProfile.read(FIXTURE / "visual/manifest.json"),
            )
        )
    finally:
        if state.lease:
            cleanup = deployment.close(state, config.bounds.cleanup)
            result = result.model_copy(update={"cleanup": (*result.cleanup, cleanup)})
        (config.run_directory / "resources.json").write_text(
            json.dumps([r.model_dump(mode="json") for r in registry.tokens], indent=2),
            encoding="utf-8",
        )
    assert isinstance(prepared, Succeeded)
    inputs = packet.PacketInputs(
        config=config,
        deployment=prepared.payload,
        fixture=FixtureExpectation.read(FIXTURE / "expected.json"),
        source_revision=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        source_content=frozen,
        dependencies=(
            "playwright==1.64.0",
            "chromium==156.0.8078.4/revision1248",
            "pillow==12.3.0",
        ),
    )
    if not disconnected:
        prove_missing_open_reopen_files(inputs, result, registry)
    final = packet.finalize(inputs, result, registry.tokens)
    assert final.verdict == ("FAILED" if disconnected else "VERIFIED"), final
    if not disconnected:
        prove_negative_invariants(inputs, result, registry)
    asyncio.run(
        independently_decode_and_truncate(
            result, config.run_directory.parent / (str(config.run_id) + "-decode")
        )
    )
