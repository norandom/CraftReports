"""Installed-wheel integration fixtures; fast tests never boot this runtime."""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fixture_packaging import ROOT, InstalledFixture, build_fixture
from installed_evidence import Evidence

EVIDENCE = pytest.StashKey[Evidence]()
INSTALLED = pytest.StashKey[InstalledFixture]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--kernel-run-dir", type=Path, default=None)


def evidence(config: pytest.Config) -> Evidence:
    if EVIDENCE not in config.stash:
        configured: Path | None = config.getoption("--kernel-run-dir")
        name = datetime.now(UTC).strftime("kernel-%Y%m%dT%H%M%S-") + uuid4().hex[:8]
        directory = (configured or ROOT / "artifacts" / name).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        config.stash[EVIDENCE] = Evidence(directory)
    return config.stash[EVIDENCE]


@pytest.fixture(scope="session")
def installed_runtime(pytestconfig: pytest.Config) -> InstalledFixture:
    if INSTALLED not in pytestconfig.stash:
        pytestconfig.stash[INSTALLED] = build_fixture(evidence(pytestconfig).directory)
    return pytestconfig.stash[INSTALLED]


def pytest_sessionstart(session: pytest.Session) -> None:
    if session.config.getoption("--kernel-run-dir") is not None:
        from test_activation import ACTIVATION_VARIANTS

        session.config.stash[INSTALLED] = build_fixture(
            evidence(session.config).directory, ACTIVATION_VARIANTS
        )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if EVIDENCE in item.config.stash:
        fixtures = item.funcargs.values() if isinstance(item, pytest.Function) else ()
        item.config.stash[EVIDENCE].cases.append(
            {
                "case": report.nodeid,
                "phase": report.when,
                "outcome": report.outcome,
                "duration_seconds": report.duration,
                "run_id": item.config.stash[EVIDENCE].directory.name,
                "build_digest": item.config.stash[EVIDENCE].build_digest,
                "installed_builds": sorted(
                    {
                        item.config.stash[EVIDENCE].capture_build(value)
                        for value in fixtures
                        if isinstance(value, InstalledFixture)
                    }
                ),
            }
        )
    return report


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if EVIDENCE in session.config.stash:
        passed = session.config.stash[EVIDENCE].finish(exitstatus)
        if session.config.getoption("--kernel-run-dir") is not None and not passed:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
