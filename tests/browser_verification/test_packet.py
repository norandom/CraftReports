"""Final evidence rejects missing facts and retains primary/cleanup distinctions."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.browser_verification import journey, packet
from scripts.browser_verification.config import OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import ActionReceipt, Rejected, StageFinding
from scripts.browser_verification.deployment import DeploymentLease
from scripts.browser_verification.evidence import Diagnostic, complete_webm
from scripts.browser_verification.visual_profile import ChartObservation

from .test_artifacts import EXPECTED
from .test_contracts import target


def inputs_for(tmp_path: Path) -> packet.PacketInputs:
    config = RunConfig(
        deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path, headed=False
    )
    config.run_directory.mkdir()
    source = tmp_path / "source.py"
    source.write_text("frozen-before-run", encoding="utf-8")
    lease = DeploymentLease(
        resource_id=uuid4(),
        owner_run=config.run_id,
        mode="owned-linux",
        project="unit",
        origin="http://localhost:9000",
        bind_address="127.0.0.1",
        port=9000,
        build_sha256="a" * 64,
        assets=(),
    )
    return packet.PacketInputs(
        config=config,
        deployment=lease,
        fixture=EXPECTED,
        source_revision="unit-revision",
        source_content=(packet.hash_content(source),),
        dependencies=("unit-dependencies",),
    )


def test_missing_stages_are_unexecuted_and_packet_is_atomic(tmp_path: Path) -> None:
    inputs = inputs_for(tmp_path)
    final = packet.finalize(inputs, journey.RoundTripResult(), ())
    assert final.verdict != "VERIFIED"
    assert {f.stage for f in final.findings if f.status == "unexecuted"} == {
        "readiness",
        "visible-mutation",
        "persistence",
        "byte-inspection",
        "browser-reopen",
    }
    manifest = inputs.config.run_directory / "manifest.json"
    assert json.loads(manifest.read_text())["result"]["run_id"] == str(inputs.config.run_id)
    assert not manifest.with_name("manifest.partial").exists()
    before = manifest.read_bytes()
    retained = json.loads(manifest.read_text())
    findings = manifest.with_name("findings.json")
    assert json.loads(findings.read_text()) == [f.model_dump(mode="json") for f in final.findings]
    assert packet.hash_content(findings).model_dump(mode="json") in retained["files"]
    with pytest.raises(ValueError):
        packet.finalize(inputs, journey.RoundTripResult(), ())
    assert manifest.read_bytes() == before


@pytest.mark.parametrize("category", ["page", "console", "request"])
def test_unexpected_diagnostics_fail(tmp_path: Path, category: str) -> None:
    inputs = inputs_for(tmp_path)
    event = Diagnostic.model_validate({"stage": "edit", "category": category, "code": "safe-code"})
    result = journey.RoundTripResult(diagnostics=(event,))
    final = packet.finalize(inputs, result, ())
    assert final.verdict == "FAILED"
    assert any(f.stage == "edit" and f.status == "failed" for f in final.findings)


def test_source_change_is_retained_as_evidence_failure(tmp_path: Path) -> None:
    inputs = inputs_for(tmp_path)
    Path(inputs.source_content[0].path).write_bytes(b"changed-after-freeze")
    final = packet.finalize(inputs, journey.RoundTripResult(), ())
    assert any(f.stage == "evidence" and f.status == "failed" for f in final.findings)


def test_pending_resource_cannot_publish(tmp_path: Path) -> None:
    inputs = inputs_for(tmp_path)
    resource = journey.ResourceToken(
        token_id=uuid4(), owner_run=inputs.config.run_id, kind="context", identity="pending-context"
    )
    with pytest.raises(ValueError):
        packet.finalize(inputs, journey.RoundTripResult(), (resource,))
    assert not (inputs.config.run_directory / "manifest.json").exists()


def test_primary_failure_is_not_replaced_by_cleanup_failure(tmp_path: Path) -> None:
    inputs = inputs_for(tmp_path)
    primary = Rejected(
        finding=StageFinding(
            stage="edit", requirements=("3.3",), status="unresolved", observed=("effect-timeout",)
        )
    )
    final = packet.finalize(inputs, journey.RoundTripResult(primary=primary), ())
    assert primary.finding in final.findings
    assert any(f.stage == "cleanup" and f.status == "failed" for f in final.findings)


@pytest.mark.parametrize(
    "body", [b"", b"\x18\x53\x80\x67\x00", b"\x18\x53\x80\x67\xff", b"\x18\x53\x80\x67\x85data"]
)
def test_missing_unknown_and_truncated_segment_rejected(body: bytes) -> None:
    with pytest.raises(ValueError):
        complete_webm(body)


def test_finite_complete_segment_accepts_only_exact_size() -> None:
    body = b"\x18\x53\x80\x67\x84data"
    complete_webm(body)
    with pytest.raises(ValueError):
        complete_webm(body + b"trailing")


@pytest.mark.parametrize("fault", ["valid", "resources", "roundtrip", "truncated"])
def test_retained_typed_records_must_agree(tmp_path: Path, fault: str) -> None:
    result = journey.RoundTripResult()
    (tmp_path / "roundtrip.json").write_text(result.model_dump_json(), encoding="utf-8")
    (tmp_path / "resources.json").write_text("[]", encoding="utf-8")
    if fault == "valid":
        packet.verify_records(tmp_path, result, ())
        return
    if fault == "resources":
        (tmp_path / "resources.json").write_text('["unrelated"]', encoding="utf-8")
    elif fault == "roundtrip":
        result = result.model_copy(
            update={
                "primary": Rejected(
                    finding=StageFinding(stage="readiness", requirements=("1.5",), status="blocked")
                )
            }
        )
    else:
        (tmp_path / "roundtrip.json").write_text('{"cut":', encoding="utf-8")
    with pytest.raises(ValueError):
        packet.verify_records(tmp_path, result, ())


def test_every_retained_json_must_decode(tmp_path: Path) -> None:
    (tmp_path / "truncated.json").write_text('{"cut":', encoding="utf-8")
    with pytest.raises(ValueError):
        packet.hash_directory(tmp_path)


@pytest.mark.parametrize("action", ["open", "reopen", "edit", "save", "copy"])
def test_every_action_receipt_file_is_required(action: str, tmp_path: Path) -> None:
    path = str(tmp_path / (action + ".png"))
    receipt = ActionReceipt.model_validate(
        {
            "dispatch_id": uuid4(),
            "target": target(),
            "action": action,
            "start": 1,
            "deadline": 2,
            "status": "observed",
            "observation_refs": (path,),
        }
    )
    assert path in packet.references(journey.RoundTripResult(receipts=(receipt,)))


def test_chart_copy_receipt_files_do_not_depend_on_checkset_refs(tmp_path: Path) -> None:
    selected = target()
    path = str(tmp_path / "chart-copy.png")
    receipt = ActionReceipt(
        dispatch_id=uuid4(),
        target=selected,
        action="copy",
        start=1,
        deadline=2,
        status="observed",
        observation_refs=(path,),
    )
    chart = ChartObservation(
        target=selected,
        phase="before",
        profile_id="unit",
        category="unit",
        category_nonce="unit",
        captures=(),
        cells_before=(),
        cells=(),
        copy_receipt=receipt,
    )
    assert path in packet.references(journey.RoundTripResult(charts=(chart,)))


def test_recorded_interactions_requires_both_collections() -> None:
    with pytest.raises(ValueError):
        packet.RecordedInteractions.model_validate({"receipts": []})
    with pytest.raises(ValueError):
        packet.RecordedInteractions.model_validate({"observations": []})


@pytest.mark.parametrize("fault", ["valid", "missing", "digest", "build", "release", "member"])
def test_bundle_provenance_is_frozen_and_bound(tmp_path: Path, fault: str) -> None:
    from scripts.browser_verification import release
    from scripts.browser_verification.contracts import ContentIdentity, Succeeded

    from .test_release import selected

    inputs = inputs_for(tmp_path)
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"release-archive")
    member = tmp_path / "app.js"
    member.write_bytes(b"release-member")
    identity = selected(tmp_path, archive.read_bytes())
    bundle = release.BundleIdentity(
        release=identity,
        archive=archive,
        root=tmp_path,
        files=(ContentIdentity(path="app.js", sha256=packet.hash_content(member).sha256),),
    )
    frozen = (packet.hash_content(archive), packet.hash_content(member))
    if fault == "missing":
        frozen = frozen[:1]
    elif fault == "digest":
        frozen = (frozen[0], frozen[1].model_copy(update={"sha256": "b" * 64}))
    elif fault == "release":
        bundle = bundle.model_copy(
            update={"release": identity.model_copy(update={"version": "other"})}
        )
    elif fault == "member":
        bundle = bundle.model_copy(
            update={"files": (ContentIdentity(path="../app.js", sha256=frozen[1].sha256),)}
        )
    inputs = inputs.model_copy(
        update={
            "source_content": frozen,
            "deployment": inputs.deployment.model_copy(
                update={"build_sha256": "b" * 64 if fault == "build" else identity.sha256}
            ),
        }
    )
    (inputs.config.run_directory / "bundle.json").write_text(
        Succeeded(payload=bundle).model_dump_json(), encoding="utf-8"
    )
    (inputs.config.run_directory / "release.json").write_text(
        Succeeded(payload=identity).model_dump_json(), encoding="utf-8"
    )
    if fault == "valid":
        packet.verify_provenance(inputs)
    else:
        with pytest.raises(ValueError):
            packet.verify_provenance(inputs)


@pytest.mark.parametrize("fault", ["valid", "unfrozen", "build", "origin"])
def test_external_manifest_is_frozen_and_build_bound(tmp_path: Path, fault: str) -> None:
    from scripts.browser_verification import release
    from scripts.browser_verification.config import ExternalDeployment
    from scripts.browser_verification.contracts import ContentIdentity, Succeeded

    from .test_release import selected

    inputs = inputs_for(tmp_path)
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"archive")
    member = tmp_path / "app.js"
    member.write_bytes(b"member")
    identity = selected(tmp_path, archive.read_bytes())
    bundle = release.BundleIdentity(
        release=identity,
        archive=archive,
        root=tmp_path,
        files=(ContentIdentity(path="app.js", sha256=packet.hash_content(member).sha256),),
    )
    manifest = tmp_path / "external.json"
    external = (
        bundle
        if fault != "build"
        else bundle.model_copy(update={"release": identity.model_copy(update={"sha256": "b" * 64})})
    )
    manifest.write_text(external.model_dump_json(), encoding="utf-8")
    frozen = (packet.hash_content(archive), packet.hash_content(member))
    if fault != "unfrozen":
        frozen = (*frozen, packet.hash_content(manifest))
    inputs = inputs.model_copy(
        update={
            "source_content": frozen,
            "deployment": inputs.deployment.model_copy(update={"build_sha256": identity.sha256}),
            "config": inputs.config.model_copy(
                update={
                    "deployment": ExternalDeployment(
                        origin="http://localhost:9001"
                        if fault == "origin"
                        else inputs.deployment.origin,
                        build_manifest=manifest,
                    )
                }
            ),
        }
    )
    (inputs.config.run_directory / "bundle.json").write_text(
        Succeeded(payload=bundle).model_dump_json(), encoding="utf-8"
    )
    (inputs.config.run_directory / "release.json").write_text(
        Succeeded(payload=identity).model_dump_json(), encoding="utf-8"
    )
    if fault == "valid":
        packet.verify_provenance(inputs)
    else:
        with pytest.raises(ValueError):
            packet.verify_provenance(inputs)
