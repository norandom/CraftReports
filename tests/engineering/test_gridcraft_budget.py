"""GridCraft first-release calibration preserves exact owner, approval and local boundaries."""

from pathlib import Path

import pytest
import test_adapter_budget
import test_storage_budget
from check_quality import check
from quality_policy import load_ownership, load_policy
from test_storage_budget import source

storage_repository = test_storage_budget.repository
adapter_repository = test_adapter_budget.repository

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = ".kiro/specs/craftreport-gridcraft-web-reports/first-release-budget-proposal.md"
GRIDCRAFT = "packages/craftreport-gridcraft/src/craftreport_gridcraft"
SCOPE = (
    '\n[scope_approval.gridcraft-web-reports]\napproved = true\ncapability_id = "gridcraft"\n'
    f'budget_amendment_reference = "{APPROVAL}"\n'
)
ENTRY = (
    '\n[[capability_limits.entries]]\ncapability_id = "gridcraft"\n'
    'rule = "capability-lloc"\nvalue = 2600\napproved = true\nowner = "project-owner"\n'
    'rationale = "Owner approved first-release gridcraft calibration"\n'
    f'approval_reference = "{APPROVAL}"\n'
)


@pytest.fixture
def repository(adapter_repository: Path) -> Path:
    path = adapter_repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    if "[scope_approval.gridcraft-web-reports]" in policy:
        before, rest = policy.split("[scope_approval.gridcraft-web-reports]", 1)
        _, after = rest.split("\n[future_gate_families]", 1)
        policy = f"{before}{SCOPE.lstrip()}\n[future_gate_families]{after}"
    else:
        policy += SCOPE
    path.write_text(policy + ENTRY, encoding="utf-8")
    target = adapter_repository / APPROVAL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((ROOT / APPROVAL).read_text(encoding="utf-8"), encoding="utf-8")
    return adapter_repository


def test_actual_policy_enforces_approved_gridcraft_limit() -> None:
    policy = load_policy(ROOT, load_ownership(ROOT))
    assert policy.capability_limit("gridcraft") == 2600


@pytest.mark.parametrize(
    ("prefix", "owner", "limit"),
    [
        (GRIDCRAFT, "gridcraft", 2600),
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
        ("value = 2600", f"value = {value}")
        for value in ("0", "-1", "true", "2600.0", '"2600"', "2601", "1500", "2000", "3400")
    ]
    + [
        ('capability_id = "gridcraft"', 'capability_id = "unknown"'),
        ('capability_id = "gridcraft"', 'capability_id = "runtime"'),
        ('capability_id = "gridcraft"', 'capability_id = "*"'),
        ('rule = "capability-lloc"', 'rule = "module-lloc"'),
        ('owner = "project-owner"', 'owner = "other-owner"'),
        ('owner = "project-owner"', "owner = 1"),
        (
            'rationale = "Owner approved first-release gridcraft calibration"',
            'rationale = " "',
        ),
        ("approved = true", "approved = false"),
        ("approved = true", "approved = 1"),
        (f'approval_reference = "{APPROVAL}"', 'approval_reference = "README.md"'),
        (f'approval_reference = "{APPROVAL}"\n', ""),
        ('owner = "project-owner"\n', ""),
        ('rule = "capability-lloc"', 'rule = "*"'),
        ("value = 2600", 'value = 2600\nunknown_field = "*"'),
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
        ('capability_id = "gridcraft"', 'capability_id = "runtime"'),
        ("approved = true", "approved = false"),
        ("approved = true", 'approved = "true"'),
        (f'budget_amendment_reference = "{APPROVAL}"', 'budget_amendment_reference = "README.md"'),
    ],
)
def test_invalid_scope(repository: Path, old: str, new: str) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    before, scope = policy.split("[scope_approval.gridcraft-web-reports]", 1)
    path.write_text(
        before + "[scope_approval.gridcraft-web-reports]" + scope.replace(old, new, 1),
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
    source(repository, GRIDCRAFT, 1501)
    report = check(repository)
    assert report.errors == []
    assert [(v.owner, v.message) for v in report.violations] == [("gridcraft", "1501 > 1500")]


def test_local_bounds(repository: Path) -> None:
    directory = repository / GRIDCRAFT
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
