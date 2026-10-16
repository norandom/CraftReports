"""Adapter calibration preserves exact owner, approval and local boundaries."""

from pathlib import Path

import pytest
import test_storage_budget
from check_quality import check
from quality_policy import load_ownership, load_policy
from test_storage_budget import source

storage_repository = test_storage_budget.repository

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = ".kiro/specs/craftreport-report-model-packs/adapter-budget-calibration-amendment.md"
SCOPE = (
    '\n[scope_approval.adapter-calibration]\napproved = true\ncapability_id = "adapters"\n'
    f'budget_amendment_reference = "{APPROVAL}"\n'
)
ENTRY = (
    '\n[[capability_limits.entries]]\ncapability_id = "adapters"\n'
    'rule = "capability-lloc"\nvalue = 1800\napproved = true\nowner = "project-owner"\n'
    'rationale = "Owner approved adapter calibration"\n'
    f'approval_reference = "{APPROVAL}"\n'
)


@pytest.fixture
def repository(storage_repository: Path) -> Path:
    path = storage_repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    if "[scope_approval.adapter-calibration]" not in policy:
        policy += SCOPE
    path.write_text(policy + ENTRY, encoding="utf-8")
    target = storage_repository / APPROVAL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((ROOT / APPROVAL).read_text(encoding="utf-8"), encoding="utf-8")
    return storage_repository


def test_actual_policy_enforces_approved_adapter_limit() -> None:
    policy = load_policy(ROOT, load_ownership(ROOT))
    assert policy.capability_limit("adapters") == 1800


@pytest.mark.parametrize(
    ("prefix", "owner", "limit"),
    [
        ("src/craftreport/adapters", "adapters", 1800),
        ("src/craftreport/adapters/storage", "snapshot-storage", 2000),
        ("scripts/browser_verification", "browser-verification", 3400),
        ("src/craftreport/runtime", "runtime", 1500),
        ("scripts/gates", "development-gates", 1500),
    ],
)
def test_exact_boundaries(repository: Path, prefix: str, owner: str, limit: int) -> None:
    source(repository, prefix, limit)
    report = check(repository)
    assert report.errors + report.violations == []
    assert report.production_capabilities == {owner: limit}
    source(repository, prefix, limit + 1)
    report = check(repository)
    assert report.errors == []
    assert [(v.owner, v.rule, v.message) for v in report.violations] == [
        (owner, "capability-lloc", f"{limit + 1} > {limit}")
    ]
    assert report.waived == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("value = 1800", f"value = {value}")
        for value in ("0", "-1", "true", "1800.0", '"1800"', "1801", "1500", "2000", "3400")
    ]
    + [
        ('capability_id = "adapters"', 'capability_id = "unknown"'),
        ('capability_id = "adapters"', 'capability_id = "runtime"'),
        ('capability_id = "adapters"', 'capability_id = "*"'),
        ('rule = "capability-lloc"', 'rule = "module-lloc"'),
        ('owner = "project-owner"', 'owner = "other-owner"'),
        ('owner = "project-owner"', "owner = 1"),
        ('rationale = "Owner approved adapter calibration"', 'rationale = " "'),
        ("approved = true", "approved = false"),
        ("approved = true", "approved = 1"),
        (f'approval_reference = "{APPROVAL}"', 'approval_reference = "README.md"'),
        (f'approval_reference = "{APPROVAL}"\n', ""),
        ('owner = "project-owner"\n', ""),
        ('rule = "capability-lloc"', 'rule = "*"'),
        ("value = 1800", 'value = 1800\nunknown_field = "*"'),
    ],
)
def test_invalid_entry(repository: Path, old: str, new: str) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    assert old in ENTRY
    path.write_text(policy.removesuffix(ENTRY) + ENTRY.replace(old, new), encoding="utf-8")
    assert check(repository).errors


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('capability_id = "adapters"', 'capability_id = "runtime"'),
        ("approved = true", "approved = false"),
        ("approved = true", 'approved = "true"'),
        (f'budget_amendment_reference = "{APPROVAL}"', 'budget_amendment_reference = "README.md"'),
    ],
)
def test_invalid_scope(repository: Path, old: str, new: str) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    before, scope = policy.split("[scope_approval.adapter-calibration]", 1)
    path.write_text(
        before + "[scope_approval.adapter-calibration]" + scope.replace(old, new, 1),
        encoding="utf-8",
    )
    assert check(repository).errors


def test_duplicate_missing_reference_and_default(repository: Path) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    path.write_text(policy + ENTRY, encoding="utf-8")
    assert check(repository).errors
    path.write_text(policy, encoding="utf-8")
    (repository / APPROVAL).unlink()
    assert check(repository).errors
    path.write_text(policy.removesuffix(ENTRY), encoding="utf-8")
    source(repository, "src/craftreport/adapters", 1501)
    report = check(repository)
    assert report.errors == []
    assert [(v.owner, v.message) for v in report.violations] == [("adapters", "1501 > 1500")]


def test_unapproved_or_unknown_ownership(repository: Path) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    path.write_text(policy.replace(', "adapters",', ","), encoding="utf-8")
    assert check(repository).errors
    path.write_text(policy, encoding="utf-8")
    ledger = repository / "breadth.toml"
    ledger.write_text(
        ledger.read_text(encoding="utf-8").replace("[capability.adapters]", "[capability.other]"),
        encoding="utf-8",
    )
    assert check(repository).errors


def test_local_bounds(repository: Path) -> None:
    directory = repository / "src/craftreport/adapters"
    directory.mkdir(parents=True)
    for extra in (0, 1):
        (directory / "module.py").write_text("x = 1\n" * (300 + extra), encoding="utf-8")
        (directory / "function.py").write_text(
            "def work():\n" + "    x = 1\n" * (49 + extra), encoding="utf-8"
        )
        (directory / "branch.py").write_text(
            "def work(x):  # noqa: C901\n" + "    if x:\n        x = 1\n" * (9 + extra),
            encoding="utf-8",
        )
        report = check(repository)
        assert report.errors == []
        assert {v.rule for v in report.violations} == (
            {"module-lloc", "function-lloc", "C901"} if extra else set()
        )
