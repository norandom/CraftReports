"""Actual installed distributions, not mocked entry points or source imports."""

import pytest
from fixture_packaging import ROOT, InstalledFixture, build_fixture


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> InstalledFixture:
    return build_fixture(tmp_path_factory.mktemp("kernel-wheels"))


def test_installed_entry_point_and_origin(installed: InstalledFixture) -> None:
    output = installed.probe("""
import sys
from pathlib import Path
from importlib.metadata import distribution
import craftreport
dist = distribution("craftreport-kernel-fixture")
points = [p for p in dist.entry_points if p.group == "craftreport.capabilities"]
assert len(points) == 1
assert points[0].name == "synthetic"
factory = points[0].load()()
assert factory.describe().package == dist.metadata["Name"]
assert Path(craftreport.__file__).is_relative_to(Path(sys.prefix))
import craftreport_kernel_fixture
assert Path(craftreport_kernel_fixture.__file__).is_relative_to(Path(sys.prefix))
assert not any(n.startswith("pytest") for n in sys.modules)
print("installed metadata, factory and wheel origins verified")
""")
    assert "verified" in output


def test_fixture_wheel_excludes_providers(installed: InstalledFixture) -> None:
    from zipfile import ZipFile

    wheel = next(p for p in installed.wheels if p.name.startswith("craftreport_kernel_fixture-"))
    with ZipFile(wheel) as archive:
        names = archive.namelist()
    assert all("fixture_services" not in name and "pytest" not in name for name in names)
    assert any(name.endswith("entry_points.txt") for name in names)


def test_installed_author_contract(installed: InstalledFixture) -> None:
    probe = ROOT / "tests/kernel/fixture_package_probe.py"
    output = installed.probe(
        f"import sys, runpy; sys.path.insert(0, {str(probe.parent)!r}); "
        f"runpy.run_path({str(probe)!r}, run_name='__main__')"
    )
    assert "synthetic readback verified" in output


def test_documented_author_example(installed: InstalledFixture) -> None:
    documentation = (ROOT / "docs/capability-authoring.md").read_text(encoding="utf-8")
    example = documentation.split("```python\n", 1)[1].split("```", 1)[0]
    installed.probe(example)


def test_installed_versions_match_frozen_lock(installed: InstalledFixture) -> None:
    import json
    import tomllib

    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    expected = {item["name"]: item["version"] for item in lock["package"]}
    inventory = json.loads((installed.directory / "inventory.json").read_text())
    packages = inventory["environment"]["packages"]
    for name, version in packages.items():
        if not name.startswith("craftreport-kernel-fixture"):
            assert expected[name.lower().replace("_", "-")] == version
    assert len(inventory["wheels"]) == 5


def test_isolated_variants_have_real_discovery_metadata(installed: InstalledFixture) -> None:
    output = installed.probe("""
import sys
from importlib.metadata import entry_points
from packaging.specifiers import SpecifierSet
from packaging.version import Version
points = {p.name: p for p in entry_points(group="craftreport.capabilities")}
assert set(points) == {"snapshot", "synthetic", "unselected", "incompatible", "collision"}
assert points["snapshot"].value == "craftreport.composition.snapshot_host:snapshot_factory"
assert "craftreport.composition.snapshot_host" not in sys.modules
assert not any(n.startswith("craftreport_kernel_fixture") for n in sys.modules)
base = points["synthetic"].load()().describe()
assert "craftreport_kernel_fixture_unselected" not in sys.modules
bad = points["incompatible"].load()().describe()
collision = points["collision"].load()().describe()
assert Version("1.0.0") not in SpecifierSet(bad.core_contract_range)
assert collision.identity == base.identity
assert collision.operations == base.operations
assert len({base.implementation_digest, bad.implementation_digest,
            collision.implementation_digest}) == 3
assert "craftreport_kernel_fixture_unselected" not in sys.modules
assert "craftreport.composition.snapshot_host" not in sys.modules
print("isolated variants verified")
""")
    assert "verified" in output
