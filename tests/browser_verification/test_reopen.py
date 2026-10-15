"""Reopen rejects unverified bytes and old/external target associations before UI."""

import asyncio
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from scripts.browser_verification.contracts import (
    ArtifactIdentity,
    InspectedArtifact,
    Rejected,
    StageFinding,
    Succeeded,
)
from scripts.browser_verification.interactions import BrowserDriver, TargetMismatch
from scripts.browser_verification.xlsx import inspect_artifact

from .test_artifacts import EXPECTED, FIXTURE, rewritten
from .test_contracts import target


@pytest.mark.parametrize(
    "fault",
    [
        "run",
        "context",
        "page",
        "path",
        "missing",
        "semantics",
        "build",
        "origin",
        "marker",
        "source-fixture",
        "valid",
    ],
)
def test_reopen_requires_exact_inspected_artifact(tmp_path: Path, fault: str) -> None:
    path = rewritten(tmp_path, {"xl/worksheets/sheet1.xml": ("<v>20</v>", "<v>25</v>")})
    origin = target().model_copy(
        update={"fixture_marker": EXPECTED.marker.value, "artifact_sha256": EXPECTED.fixture.sha256}
    )
    artifact = ArtifactIdentity(
        artifact_id=uuid4(),
        destination=path.resolve(),
        size=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target=origin,
        route="download",
    )
    changes = {
        "build": {"build_sha256": "f" * 64},
        "origin": {"origin": "http://different.test"},
        "marker": {"fixture_marker": "different"},
        "source-fixture": {"artifact_sha256": "f" * 64},
    }
    if fault in changes:
        artifact = artifact.model_copy(update={"target": origin.model_copy(update=changes[fault])})
    inspection = inspect_artifact(artifact, EXPECTED)
    assert isinstance(inspection, Succeeded)
    state = SimpleNamespace(context_id=uuid4(), page_id=uuid4())
    config = SimpleNamespace(run_id=origin.run_id)
    if fault == "run":
        config.run_id = uuid4()
    if fault == "context":
        state.context_id = origin.context_id
    if fault == "page":
        state.page_id = origin.page_id
    if fault == "path":
        artifact = artifact.model_copy(update={"destination": tmp_path / "elsewhere.xlsx"})
    if fault == "missing":
        path.unlink()
    if fault == "semantics":
        path.write_bytes((FIXTURE / "reference.xlsx").read_bytes())
    rejected = Rejected(
        finding=StageFinding(stage="reopen", requirements=("4.6",), status="blocked")
    )
    driver = cast(
        BrowserDriver,
        SimpleNamespace(
            target=None,
            guard=MagicMock(side_effect=TargetMismatch("validated-input-boundary")),
            expected=EXPECTED,
            ready=SimpleNamespace(build_sha256=origin.build_sha256, origin=origin.origin),
            state=state,
            config=config,
            generation=1,
            rejected=AsyncMock(return_value=rejected),
        ),
    )
    result = asyncio.run(
        BrowserDriver.open(
            driver,
            path,
            InspectedArtifact(
                artifact=artifact,
                inspection=inspection.payload,
                fixture_sha256=EXPECTED.fixture.sha256,
            ),
        )
    )
    assert isinstance(result, Rejected)
    if fault == "valid":
        assert driver.target and driver.target.generation > origin.generation
        assert driver.target.artifact_sha256 == artifact.sha256
        assert driver.target.context_id != origin.context_id
        assert driver.target.page_id != origin.page_id
    else:
        assert driver.target is None


@pytest.mark.parametrize("fault", ["empty", "failed", "unexecuted", "before"])
def test_inspected_source_withholds_nonpassing_or_wrong_phase(tmp_path: Path, fault: str) -> None:
    from pydantic import ValidationError

    from scripts.browser_verification.contracts import ArtifactCheckSet

    path = rewritten(tmp_path, {"xl/worksheets/sheet1.xml": ("<v>20</v>", "<v>25</v>")})
    artifact = ArtifactIdentity(
        artifact_id=uuid4(),
        destination=path.resolve(),
        size=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target=target(),
        route="download",
    )
    findings = (
        ()
        if fault == "empty"
        else (
            StageFinding(
                stage="byte-inspection",
                requirements=("4.5",),
                status="passed"
                if fault == "before"
                else "failed"
                if fault == "failed"
                else "unexecuted",
                expected=("typed-cell-B3", "before" if fault == "before" else "after"),
            ),
        )
    )
    with pytest.raises(ValidationError):
        InspectedArtifact(
            artifact=artifact,
            inspection=ArtifactCheckSet(
                findings=findings,
                artifact_sha256=artifact.sha256,
                artifact_size=artifact.size,
                fixture_sha256=EXPECTED.fixture.sha256,
                phase="after",
            ),
            fixture_sha256=EXPECTED.fixture.sha256,
        )


@pytest.mark.parametrize("fault", ["hash", "size", "fixture", "phase"])
def test_inspection_receipt_binds_exact_bytes_and_fixture(tmp_path: Path, fault: str) -> None:
    from pydantic import ValidationError

    path = rewritten(tmp_path, {"xl/worksheets/sheet1.xml": ("<v>20</v>", "<v>25</v>")})
    artifact = ArtifactIdentity(
        artifact_id=uuid4(),
        destination=path.resolve(),
        size=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        target=target(),
        route="download",
    )
    checked = inspect_artifact(artifact, EXPECTED)
    assert isinstance(checked, Succeeded)
    updates = {
        "hash": {"artifact_sha256": "f" * 64},
        "size": {"artifact_size": artifact.size + 1},
        "fixture": {"fixture_sha256": "f" * 64},
        "phase": {"phase": "before"},
    }
    with pytest.raises(ValidationError):
        InspectedArtifact(
            artifact=artifact,
            inspection=checked.payload.model_copy(update=updates[fault]),
            fixture_sha256=EXPECTED.fixture.sha256,
        )
