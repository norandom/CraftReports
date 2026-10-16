"""Real configured report capability and durable host behavior."""

import asyncio
from pathlib import Path

from report_host_fixture import ALICE, report_host
from test_pack_reader import assets as assets
from test_prepare import definition as definition
from test_themes import theme as theme

from craftreport.composition.reporting import is_compatible, reporting_factory
from craftreport.contracts import CapabilityRequirement, CapabilityVersion


def test_manifest_and_actual_compatibility() -> None:
    manifest = reporting_factory().describe()
    assert manifest.identity == "reporting"
    assert {op.key.name for op in manifest.operations} == {
        "reports.validate_definition",
        "reports.discover_packs",
        "reports.prepare",
    }
    assert is_compatible(CapabilityVersion("test", "1.0"), CapabilityRequirement("test", ">=1"))
    assert not is_compatible(CapabilityVersion("test", "bad"), CapabilityRequirement("test", ">=1"))
    assert not is_compatible(CapabilityVersion("other", "1"), CapabilityRequirement("test", ">=1"))


def test_real_host_catalog(tmp_path: Path, assets: dict[str, bytes]) -> None:
    async def exercise() -> None:
        async with report_host(tmp_path, assets) as host:
            assert len(host.app.settings.selections) == 2
            catalog = await host.facade.catalog(ALICE)
            assert {operation.key.name for operation in catalog.operations} == {
                "reports.discover_packs",
                "reports.validate_definition",
                "reports.prepare",
                "snapshot.publish",
                "snapshot.read",
                "snapshot.latest",
                "runtime.bind",
                "runtime.inspect",
            }

    asyncio.run(exercise())
