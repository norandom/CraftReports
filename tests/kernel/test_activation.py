"""Activation is exercised from installed wheels in an isolated interpreter."""

import pytest
from fixture_packaging import ROOT, InstalledFixture, build_fixture


@pytest.fixture(scope="module")
def installed(tmp_path_factory: pytest.TempPathFactory) -> InstalledFixture:
    return build_fixture(
        tmp_path_factory.mktemp("activation-wheels"),
        (
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
        ),
    )


def test_installed_activation(installed: InstalledFixture) -> None:
    probe = ROOT / "tests/kernel/activation_probe.py"
    output = installed.probe(
        f"import sys, runpy; sys.path.insert(0, {str(probe.parent)!r}); "
        f"runpy.run_path({str(probe)!r}, run_name='__main__')"
    )
    assert "installed activation verified" in output
