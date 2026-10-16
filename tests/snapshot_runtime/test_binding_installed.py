"""Ordinary installed binding clients preserve exact values across real restart."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from craftreport.adapters.binding_codecs import (
    BindingResultCodec,
    bind_codec,
    parameter_digest,
    requirements_digest,
)
from craftreport.adapters.canonical import canonical_bytes
from craftreport.adapters.report_codecs import (
    preparation_result_codec,
    validation_result_codec,
    validation_scope_identifier,
)
from craftreport.application.service_values import Missing
from craftreport.reporting.ports import PreparationResult, ValidationResult
from craftreport.runtime.values import BindingSpec, BindingState, BindRequest, RunPins
from scripts.examples.prepare_reusable_report import PACK, snapshot
from tests.kernel.fixture_packaging import ROOT, build_fixture
from tests.reporting.report_demo import ASSETS
from tests.snapshot_runtime.installed_client import SnapshotProcess
from tests.snapshot_runtime.test_binding_values import binding_spec
from tests.snapshot_runtime.test_installed import command, published

pytest_plugins = ["tests.snapshot_runtime.test_wire"]


def evidence_directory() -> Path:
    directory = ROOT / "artifacts/snapshot-runtime/task-5.1/installed" / uuid4().hex
    directory.mkdir(parents=True)
    sources = (
        "test_binding_installed.py",
        "installed_host.py",
        "installed_client.py",
        "binding_host.py",
    )
    hashes = {
        name: sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in sources
    }
    (directory / "test-source-hashes.json").write_text(
        json.dumps(hashes, indent=2), encoding="utf-8"
    )
    return directory


def installed_spec(feed: str) -> BindingSpec:
    spec = binding_spec()
    parameters = (
        *spec.resolved_parameters,
        ("day", date(2026, 10, 16)),
        ("instant", datetime(2026, 10, 16, 1, 2, 3, 123456, UTC)),
        ("flag", True),
        ("empty", None),
    )
    return replace(
        spec,
        feed_id=feed,
        resolved_parameters=parameters,
        parameter_digest=parameter_digest(parameters),
    )


def bind_request(spec: BindingSpec, generation: int, revision: str, key: str) -> dict[str, Any]:
    return {
        "operation": "runtime.bind",
        "contract_version": "1",
        "payload": json.loads(canonical_bytes(bind_codec().encode(BindRequest(spec, generation)))),
        "correlation_id": key,
        "retry_key": key,
        "expected_versions": [
            {"resource": {"kind": "binding", "identity": spec.binding_id}, "version": revision},
            {"resource": {"kind": "feed", "identity": spec.feed_id}, "version": "1"},
        ],
    }


def inspect_request(identity: str, kind: str = "binding") -> dict[str, Any]:
    return {
        "operation": "runtime.inspect",
        "contract_version": "1",
        "payload": {"kind": kind, "identity": identity},
        "correlation_id": "inspect-binding",
    }


def result(host: SnapshotProcess, receipt: dict[str, Any]) -> dict[str, Any]:
    assert receipt["state"] == "complete", receipt
    read = host.rest("GET", f"/v1/operations/{receipt['operation_id']}/result")
    assert read["receipt"] == receipt
    return read["value"]


async def mcp_result(host: SnapshotProcess, request: dict[str, Any]) -> dict[str, Any]:
    receipt = await host.mcp(request["operation"] + ".v1", request)
    assert receipt["state"] == "complete", receipt
    read = await host.mcp("craftreport.result.v1", {"operation_id": receipt["operation_id"]})
    return read["value"]


@pytest.mark.integration
def test_installed_binding_clients_and_restart(payload: dict[str, Any]) -> None:
    directory = evidence_directory()
    installed = build_fixture(directory)
    database = directory / "retained.sqlite3"
    host = SnapshotProcess(installed, database, directory / "first")
    spec = installed_spec(payload["feed_id"])
    try:
        catalog = json.dumps(host.catalog)
        assert '"runtime.bind"' in catalog and '"runtime.inspect"' in catalog
        mcp_catalog = asyncio.run(host.mcp("craftreport.catalog.v1", {}))
        assert mcp_catalog == {k: v for k, v in host.catalog.items() if k != "transport_limits"}
        published(host, command(payload, "publish", "absent"), "accepted")
        created_receipt = host.rest("POST", "/v1/invoke", bind_request(spec, 0, "absent", "create"))
        created = result(host, created_receipt)
        assert BindingResultCodec().decode(created) == BindingState(spec, 1, 1, "stopped", None)
        inspected = asyncio.run(mcp_result(host, inspect_request(spec.binding_id)))
        assert inspected == created
        for kind in ("binding", "run"):
            missing = result(
                host, host.rest("POST", "/v1/invoke", inspect_request("not-retained", kind))
            )
            assert BindingResultCodec().decode(missing) == Missing()
        identical = asyncio.run(mcp_result(host, bind_request(spec, 1, "1", "identical")))
        assert identical == created
        changed_spec = replace(spec, theme=replace(spec.theme, version="house-green"))
        changed = result(
            host, host.rest("POST", "/v1/invoke", bind_request(changed_spec, 1, "1", "change"))
        )
        assert BindingResultCodec().decode(changed) == BindingState(
            changed_spec, 2, 2, "stopped", None
        )
        denied = host.rest("POST", "/v1/invoke", inspect_request(spec.binding_id), subject="bob")
        assert denied["diagnostic"]["code"] == "access_denied"
        denied_bind = host.rest(
            "POST", "/v1/invoke", bind_request(spec, 2, "2", "bob-bind"), subject="bob"
        )
        assert denied_bind["diagnostic"]["code"] == "access_denied"
        target = replace(
            spec, binding_id="forbidden", target=replace(spec.target, document_id="other")
        )
        rejected = host.rest("POST", "/v1/invoke", bind_request(target, 0, "absent", "target"))
        assert rejected.get("state") != "complete", rejected
        denied_result = host.rest("GET", f"/v1/operations/{rejected['operation_id']}/result")
        assert denied_result["value"] == {"kind": "unavailable", "service": "binding_access"}
        stale = host.rest("POST", "/v1/invoke", bind_request(spec, 1, "1", "stale"))
        assert stale["diagnostic"]["code"] == "version_conflict"
        stale_generation = host.rest(
            "POST", "/v1/invoke", bind_request(spec, 1, "2", "stale-generation")
        )
        assert stale_generation.get("state") != "complete", stale_generation
        conflict_result = host.rest(
            "GET", f"/v1/operations/{stale_generation['operation_id']}/result"
        )
        assert conflict_result["value"]["kind"] == "version_conflict"
        assert (
            result(host, host.rest("POST", "/v1/invoke", inspect_request(spec.binding_id)))
            == changed
        )
        epoch = host.catalog["deployment_epoch"]
    finally:
        host.close()
    with sqlite3.connect(database) as connection:
        before = connection.execute("SELECT * FROM bindings").fetchall()
        assert len(before) == 1
    reopened = SnapshotProcess(installed, database, directory / "reopened")
    try:
        assert reopened.catalog["deployment_epoch"] == epoch
        assert reopened.catalog["capabilities"] == host.catalog["capabilities"]
        assert asyncio.run(mcp_result(reopened, inspect_request(spec.binding_id))) == changed
        assert result(reopened, created_receipt) == created
        original_state = BindingResultCodec().decode(created)
        assert isinstance(original_state, BindingState) and original_state.spec == spec
    finally:
        reopened.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM bindings").fetchall() == before


def report_request(operation: str, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation": operation,
        "contract_version": "1",
        "payload": content,
        "correlation_id": operation,
        "retry_key": operation,
    }


def prepare_binding(
    host: SnapshotProcess,
) -> tuple[BindingSpec, PreparationResult, dict[str, Any], dict[str, Any]]:
    validation = result(
        host,
        host.rest(
            "POST", "/v1/invoke", report_request("reports.validate_definition", {"pack": PACK})
        ),
    )
    valid = validation_result_codec().decode(validation)
    assert isinstance(valid, ValidationResult)
    supplied = snapshot("binding-run", 1)
    publication = published(host, command(supplied, "publish-report", "absent"), "accepted")
    preparation_receipt = host.rest(
        "POST",
        "/v1/invoke",
        report_request(
            "reports.prepare", {"pack": PACK, "snapshot": publication["value"]["requested"]}
        ),
    )
    preparation = preparation_result_codec().decode(result(host, preparation_receipt))
    assert isinstance(preparation, PreparationResult)
    prepared = preparation.prepared
    spec = BindingSpec(
        "prepared-binding",
        prepared.snapshot.feed_id,
        valid.requirements,
        requirements_digest(valid.requirements),
        prepared.definition,
        prepared.template,
        prepared.theme,
        prepared.pack.version_pin,
        prepared.resolved_parameters,
        parameter_digest(prepared.resolved_parameters),
        validation_scope_identifier(prepared.release_policy),
        binding_spec().target,
    )
    binding_receipt = host.rest(
        "POST", "/v1/invoke", bind_request(spec, 0, "absent", "bind-prepared")
    )
    bound = result(host, binding_receipt)
    assert BindingResultCodec().decode(bound) == BindingState(spec, 1, 1, "stopped", None)
    return spec, preparation, preparation_receipt, binding_receipt


@pytest.mark.integration
def test_installed_historical_run_exact_pins_after_restart() -> None:
    directory = evidence_directory()
    installed = build_fixture(directory)
    database = directory / "retained.sqlite3"
    pack = directory / "public-pack"
    pack.mkdir()
    for name, source in ASSETS.items():
        (pack / name).write_bytes((ROOT / source).read_bytes())
    first = SnapshotProcess(installed, database, directory / "prepare", pack_root=pack)
    try:
        spec, prepared, receipt, binding_receipt = prepare_binding(first)
    finally:
        first.close()
    seeded = SnapshotProcess(
        installed, database, directory / "select", pack_root=pack, seed_binding=True
    )
    try:
        state = BindingResultCodec().decode(
            result(seeded, seeded.rest("POST", "/v1/invoke", inspect_request(spec.binding_id)))
        )
        assert isinstance(state, BindingState) and state.selected_run_id is not None
        assert (state.generation, state.revision, state.intent) == (1, 2, "stopped")
        identical = asyncio.run(mcp_result(seeded, bind_request(spec, 1, "2", "selected-noop")))
        assert BindingResultCodec().decode(identical) == state
        assert (
            seeded.rest("GET", f"/v1/operations/{binding_receipt['operation_id']}")
            == binding_receipt
        )
        run_request = inspect_request(state.selected_run_id, "run")
        original = asyncio.run(mcp_result(seeded, run_request))
        expected = RunPins(
            state.selected_run_id,
            spec.binding_id,
            1,
            prepared.prepared.snapshot,
            spec.definition,
            spec.template,
            spec.theme,
            spec.pack,
            spec.resolved_parameters,
            spec.parameter_digest,
            spec.validation_scope,
            receipt["operation_id"],
            receipt["result_ref"],
            prepared.prepared.content_digest,
            spec.target,
        )
        assert BindingResultCodec().decode(original) == expected
        changed = replace(spec, theme=replace(spec.theme, version="changed-after-selection"))
        replacement = result(
            seeded,
            seeded.rest("POST", "/v1/invoke", bind_request(changed, 1, "2", "replace-selected")),
        )
        assert BindingResultCodec().decode(replacement) == BindingState(
            changed, 2, 3, "stopped", None
        )
        denied = seeded.rest("POST", "/v1/invoke", run_request, subject="bob")
        assert denied["diagnostic"]["code"] == "access_denied"
    finally:
        seeded.close()
    with sqlite3.connect(database) as connection:
        before = connection.execute("SELECT * FROM runs").fetchall()
        assert len(before) == 1
        stored, digest = connection.execute("SELECT run_bytes, run_digest FROM runs").fetchone()
        assert sha256(stored).hexdigest() == digest and json.loads(stored) == original
    reopened = SnapshotProcess(installed, database, directory / "historical", pack_root=pack)
    try:
        assert asyncio.run(mcp_result(reopened, run_request)) == original
        assert result(reopened, reopened.rest("POST", "/v1/invoke", run_request)) == original
        assert preparation_result_codec().decode(result(reopened, receipt)) == prepared
    finally:
        reopened.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM runs").fetchall() == before
        connection.execute(
            "UPDATE results SET result_bytes = ? WHERE identity = ?", (b"{}", receipt["result_ref"])
        )
    damaged = SnapshotProcess(
        installed, database, directory / "damaged-preparation", pack_root=pack
    )
    try:
        unavailable = result(damaged, damaged.rest("POST", "/v1/invoke", run_request))
        assert unavailable["kind"] == "unavailable"
    finally:
        damaged.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT * FROM runs").fetchall() == before
