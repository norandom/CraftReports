"""Preparation through the real kernel and file-backed production host."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from report_host_fixture import ALICE, report_host
from test_pack_reader import assets as assets
from test_prepare import definition as definition
from test_prepare import snapshot as snapshot
from test_themes import theme as theme

from craftreport.adapters.report_codecs import (
    decode_definition,
    discovery_result_codec,
    encode_definition,
    preparation_result_codec,
    validation_result_codec,
)
from craftreport.application.service_values import ResourceSnapshot
from craftreport.contracts import (
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    ReceiptState,
    Rejection,
    ResourceRef,
    StageState,
)
from craftreport.data.values import Snapshot
from craftreport.policies.values import CheckId, ReleasePolicy
from craftreport.reporting.ports import PreparationResult, ReportFailure, ValidationResult

PACK = {"namespace": "public", "name": "example", "version": "1.0.0"}


@pytest.mark.parametrize("designation", ["draft", "validated"])
@pytest.mark.parametrize("pin_count", [0, 1, 3])
def test_real_preparation_and_retained_quality(
    tmp_path: Path, assets: dict[str, bytes], snapshot: Snapshot, designation: str, pin_count: int
) -> None:
    definition_value = decode_definition(assets["definition.json"])
    encoded = encode_definition(
        replace(
            definition_value,
            release_policy=ReleasePolicy((CheckId.DEFINITION, CheckId.LAYOUT_FIT), "scope"),
        )
    )
    assets = {**assets, "definition.json": encoded, "template.json": encoded}

    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            reference = await host.publish(snapshot)
            payload: JsonObject = {
                "pack": PACK,
                "snapshot": reference,
                "requested_designation": designation,
            }
            observed = await host.resources.read(ResourceRef("snapshot", "feed:1"))
            assert isinstance(observed, ResourceSnapshot)
            all_pins = (
                *[v.version for v in host.activation.resources.observations.values()],
                observed.version,
            )
            versions = all_pins[:pin_count]
            receipt = await host.invoke("reports.prepare", payload, "prepare", versions=versions)
            assert receipt.state is (
                ReceiptState.COMPLETE if designation == "draft" else ReceiptState.FAILED
            ), receipt
            result = preparation_result_codec().decode(await host.result(receipt))
            assert isinstance(result, PreparationResult)
            assert result.prepared.tables[0].rows[0][0] == "=SUM(A1)"
            assert result.prepared.charts[0].categories == tuple(
                row[0] for row in snapshot.datasets[0].rows
            )
            assert len(receipt.evidence) == 2
            for evidence in receipt.evidence:
                assert len(evidence.resource_versions) == 3
                assert {pin.resource.kind for pin in evidence.resource_versions} == {
                    "snapshot",
                    "report_pack_source",
                    "report_pack_artifact_scope",
                }
            assert receipt.stages[0].state is StageState.PASSED
            assert (
                await host.invoke("reports.prepare", payload, "prepare", versions=versions)
                == receipt
            )
            retained = await host.result(receipt)
            persisted = receipt
        async with report_host(tmp_path, assets) as reopened:
            assert await reopened.result(persisted) == retained
            assert (
                await reopened.invoke("reports.prepare", payload, "prepare", versions=versions)
                == persisted
            )

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "scopes", [frozenset[str](), frozenset({"source"}), frozenset({"artifact"})]
)
def test_separate_pack_scopes_reject_without_receipt(
    tmp_path: Path, assets: dict[str, bytes], scopes: frozenset[str]
) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            principal = replace(ALICE, permitted_scopes=scopes)
            denied = await host.facade.invoke(
                principal,
                InvocationEnvelope(
                    OperationKey("reports.validate_definition", "1"), {"pack": PACK}, "denied"
                ),
            )
            assert isinstance(denied, Rejection)
            assert denied.diagnostic.code == "access_denied"

    asyncio.run(exercise())


def test_queries_and_typed_failures(
    tmp_path: Path, assets: dict[str, bytes], snapshot: Snapshot
) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            discovered = await host.invoke("reports.discover_packs", {})
            assert discovered.state is ReceiptState.COMPLETE
            found = discovery_result_codec().decode(await host.result(discovered))
            assert len(found.packs) == 1
            valid = await host.invoke("reports.validate_definition", {"pack": PACK})
            assert isinstance(
                validation_result_codec().decode(await host.result(valid)), ValidationResult
            )
            bad: JsonObject = {
                "pack": PACK,
                "parameters": [{"name": "unknown", "value": {"kind": "text", "value": "x"}}],
            }
            invalid = await host.invoke("reports.validate_definition", bad)
            assert invalid.state is ReceiptState.COMPLETE
            failed = validation_result_codec().decode(await host.result(invalid))
            assert isinstance(failed, ReportFailure)
            assert failed.code == "invalid_parameter"
            ref = await host.publish(snapshot)
            preparation = await host.invoke("reports.prepare", {**bad, "snapshot": ref}, "invalid")
            assert preparation.state is ReceiptState.FAILED
            assert isinstance(
                preparation_result_codec().decode(await host.result(preparation)), ReportFailure
            )
            assert preparation.evidence == ()
            assert preparation.stages[0].state is StageState.FAILED

    asyncio.run(exercise())
