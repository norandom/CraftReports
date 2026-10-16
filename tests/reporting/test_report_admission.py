"""Real facade rejects unsupported mapping before durable command admission."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from report_host_fixture import ALICE, ReportHost, report_host
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from test_pack_reader import assets as assets
from test_prepare import definition as definition
from test_prepare import snapshot as snapshot
from test_themes import support as support
from test_themes import theme as theme

from craftreport.adapters.report_codecs import (
    decode_theme,
    encode_theme,
    preparation_request_codec,
    preparation_result_codec,
    theme_identifier,
)
from craftreport.adapters.storage.schema import commands, evidence, results
from craftreport.contracts import (
    InvocationEnvelope,
    JsonObject,
    OperationKey,
    ReceiptState,
    Rejection,
)
from craftreport.data.values import Snapshot
from craftreport.policies.values import CheckId, CheckStatus
from craftreport.reporting.ports import PreparationResult
from craftreport.themes.resolve import CapabilityStatus

PACK = {"namespace": "public", "name": "example", "version": "1.0.0"}


async def counts(host: ReportHost) -> tuple[int, ...]:
    def read(connection: Connection) -> tuple[int, ...]:
        return tuple(
            connection.execute(select(func.count()).select_from(table)).scalar_one()
            for table in (commands, evidence, results)
        )

    return await host.resources.database.transaction(read)


def unsupported(
    support: tuple[CapabilityStatus, ...], problem: str
) -> tuple[CapabilityStatus, ...]:
    if problem.startswith("property_") or problem == "unused_optional":
        property_name = (
            "format.date_pattern" if problem == "unused_optional" else "text.font_family"
        )
        return tuple(
            replace(
                item,
                properties=tuple(
                    (
                        name,
                        ("untested" if problem == "property_untested" else "unsupported")
                        if name == property_name
                        else status,
                    )
                    for name, status in item.properties
                ),
            )
            for item in support
        )
    selected = support[0]
    if problem in ("incompatible", "malformed"):
        selected = replace(
            selected,
            capability=replace(
                selected.capability,
                version="2.0.0" if problem == "incompatible" else "not-a-version!",
            ),
        )
    else:
        selected = replace(selected, status="untested" if problem == "untested" else "unsupported")
    return (selected, *support[1:])


@pytest.mark.parametrize(
    "problem",
    [
        "incompatible",
        "malformed",
        "untested",
        "unsupported",
        "property_untested",
        "property_unsupported",
    ],
)
def test_real_admission_theme_failure_creates_no_receipt_or_facts(
    tmp_path: Path,
    assets: dict[str, bytes],
    snapshot: Snapshot,
    support: tuple[CapabilityStatus, ...],
    problem: str,
) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            reference = await host.publish(snapshot)
            codec = preparation_request_codec()
            request = codec.decode({"pack": PACK, "snapshot": reference})
            payload = codec.encode(replace(request, target_support=unsupported(support, problem)))
            before = await counts(host)
            rejected = await host.facade.invoke(
                ALICE,
                InvocationEnvelope(
                    OperationKey("reports.prepare", "1"), payload, "mapping", "unsupported"
                ),
            )
            assert isinstance(rejected, Rejection)
            assert rejected.diagnostic.code == (
                "incompatible_version"
                if problem in ("incompatible", "malformed")
                else f"{problem.removeprefix('property_')}_mapping"
            )
            assert rejected.diagnostic.location == ("target_support",)
            assert await counts(host) == before
        async with report_host(tmp_path, assets) as reopened:
            assert await counts(reopened) == before

    asyncio.run(exercise())


def test_unused_optional_unsupported_property_is_admissible(
    tmp_path: Path,
    assets: dict[str, bytes],
    snapshot: Snapshot,
    support: tuple[CapabilityStatus, ...],
) -> None:
    selected_theme = decode_theme(assets["theme.json"])
    selected_theme = replace(
        selected_theme,
        formats=tuple(replace(value, date_pattern=None) for value in selected_theme.formats),
    )
    selected_theme = replace(
        selected_theme,
        version_pin=replace(
            selected_theme.version_pin, content_digest=theme_identifier(selected_theme)
        ),
    )
    assets = {**assets, "theme.json": encode_theme(selected_theme)}

    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            reference = await host.publish(snapshot)
            codec = preparation_request_codec()
            request = codec.decode({"pack": PACK, "snapshot": reference})
            payload = codec.encode(
                replace(request, target_support=unsupported(support, "unused_optional"))
            )
            before = await counts(host)
            receipt = await host.invoke("reports.prepare", payload, "optional-unused")
            assert receipt.state is ReceiptState.COMPLETE
            assert await counts(host) == tuple(
                value + increment for value, increment in zip(before, (1, 2, 1), strict=True)
            )
            result = preparation_result_codec().decode(await host.result(receipt))
            assert isinstance(result, PreparationResult)
            assert result.quality.draft_eligible
            assert (
                next(f for f in result.quality.findings if f.check_id is CheckId.LAYOUT_FIT).status
                is CheckStatus.UNEVALUATED
            )

    asyncio.run(exercise())


def test_changed_retry_content_conflicts_before_theme_eligibility(
    tmp_path: Path,
    assets: dict[str, bytes],
    snapshot: Snapshot,
    support: tuple[CapabilityStatus, ...],
) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            reference = await host.publish(snapshot)
            payload: JsonObject = {"pack": PACK, "snapshot": reference}
            receipt = await host.invoke("reports.prepare", payload, "same-key")
            assert receipt.state is ReceiptState.COMPLETE
            before = await counts(host)
            codec = preparation_request_codec()
            changed = codec.encode(
                replace(codec.decode(payload), target_support=unsupported(support, "malformed"))
            )
            rejected = await host.facade.invoke(
                ALICE,
                InvocationEnvelope(
                    OperationKey("reports.prepare", "1"), changed, "changed", "same-key"
                ),
            )
            assert isinstance(rejected, Rejection)
            assert rejected.diagnostic.code == "retry_conflict"
            assert await counts(host) == before
            assert await host.invoke("reports.prepare", payload, "same-key") == receipt
        async with report_host(tmp_path, assets) as reopened:
            assert await counts(reopened) == before
            assert await reopened.invoke("reports.prepare", payload, "same-key") == receipt

    asyncio.run(exercise())
