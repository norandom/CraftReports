"""The optional installed fixture exposes usable exact boundary contracts."""

import pytest
from fixture_packaging import InstalledFixture, build_fixture


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> InstalledFixture:
    return build_fixture(tmp_path_factory.mktemp("limit-fixture"))


def test_installed_probe_contract(installed: InstalledFixture) -> None:
    output = installed.probe("""
from craftreport_kernel_fixture import factory
assert len(factory().describe().operations) == 2
manifest = factory(boundary_probe=True).describe()
assert [op.key.name for op in manifest.operations] == [
    "synthetic.write", "synthetic.read", "synthetic.probe"]
from craftreport_kernel_fixture.models import PROBE, ProbeRequest
from craftreport_kernel_fixture.operations import Operations, sized_result
from craftreport.adapters.canonical import canonical_bytes, WireFailure
from craftreport_kernel_fixture.models import RESULT
assert len(Operations("synthetic", "synthetic").bindings(True)) == 3
request = PROBE.decode({"resource":"target-1", "value":"boundary"})
assert isinstance(request, ProbeRequest)
assert request.output_size == 0 and request.nesting is None
for size in (4096, 4097):
    result = sized_result(size, "actual-version")
    assert len(canonical_bytes({"value":result.value,"version":result.version})) == size
    try:
        encoded = RESULT.encode(result)
        assert size == 4096 and len(canonical_bytes(encoded)) == size
    except WireFailure as error:
        assert size == 4097 and error.limit == "max_output_bytes"
node = None
for _ in range(6):
    node = {"child": node}
value = {"resource":"target-1", "value":"boundary", "nesting":node}
assert PROBE.encode(PROBE.decode(value))["nesting"] == node
print("optional installed boundary contract verified")
""")
    assert "verified" in output
