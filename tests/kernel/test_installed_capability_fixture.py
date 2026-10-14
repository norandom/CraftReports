"""Selected target-mode requirements must reach the installed operation binding."""

import pytest
from fixture_packaging import InstalledFixture, build_fixture


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> InstalledFixture:
    return build_fixture(tmp_path_factory.mktemp("capability-fixture"))


def test_installed_target_requirement(installed: InstalledFixture) -> None:
    assert "verified" in installed.probe("""
from craftreport_kernel_fixture import factory
from craftreport_kernel_fixture.operations import Operations
from craftreport.contracts import CapabilityRequirement
expected = (CapabilityRequirement("synthetic-target", ">=1.0,<2.0", "native"),)
assert factory().describe().operations[0].required_capabilities == ()
manifest = factory(capability_probe=True).describe()
assert manifest.operations[0].required_capabilities == expected
bound = Operations("synthetic", "synthetic").bindings(capability_probe=True)[0]
assert bound.descriptor == manifest.operations[0]
print("selected target requirement verified")
""")
