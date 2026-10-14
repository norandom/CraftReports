"""Activation is exercised from installed wheels in an isolated interpreter."""

import pytest
from fixture_packaging import ROOT, InstalledFixture, build_fixture

ACTIVATION_VARIANTS = (
    "dependent",
    "wrongrange",
    "cyclea",
    "cycleb",
    "provideddup",
    "tooldup",
    "reserved",
    "badversion",
    "badpackage",
    "mismatch",
    "tool128",
    "tool129",
)


@pytest.fixture(scope="module")
def installed(
    tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest
) -> InstalledFixture:
    if request.config.getoption("--kernel-run-dir") is not None:
        return request.getfixturevalue("installed_runtime")
    return build_fixture(
        tmp_path_factory.mktemp("activation-wheels"),
        ACTIVATION_VARIANTS,
    )


def test_installed_activation(installed: InstalledFixture) -> None:
    probe = ROOT / "tests/kernel/activation_probe.py"
    output = installed.probe(
        f"import sys, runpy; sys.path.insert(0, {str(probe.parent)!r}); "
        f"runpy.run_path({str(probe)!r}, run_name='__main__')"
    )
    assert "installed activation verified" in output
    (installed.directory / "activation-probe.log").write_text(output, encoding="utf-8")
