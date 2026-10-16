"""Real source boundaries for the approved storage-only calibration."""

from pathlib import Path

import pytest
from check_quality import check

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = ".kiro/specs/craftreport-snapshot-runtime/storage-budget-calibration-amendment.md"
STORAGE = "src/craftreport/adapters/storage"
ENTRY = (
    '\n[[capability_limits.entries]]\ncapability_id = "snapshot-storage"\n'
    'rule = "capability-lloc"\nvalue = 2000\napproved = true\nowner = "project-owner"\n'
    'rationale = "Owner approved storage calibration"\n'
    f'approval_reference = "{APPROVAL}"\n'
)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    policy = (ROOT / "quality.toml").read_text(encoding="utf-8")
    policy = policy.split('\n[[capability_limits.entries]]\ncapability_id = "snapshot-storage"')[0]
    (tmp_path / "quality.toml").write_text(policy + ENTRY, encoding="utf-8")
    (tmp_path / "breadth.toml").write_text(
        (ROOT / "breadth.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for reference in (
        APPROVAL,
        ".kiro/specs/craftreport-browser-verification/lifecycle-evidence-budget-amendment.md",
    ):
        target = tmp_path / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / reference).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def source(root: Path, prefix: str, total: int) -> None:
    directory = root / prefix
    directory.mkdir(parents=True, exist_ok=True)
    for index, start in enumerate(range(0, total, 300)):
        (directory / f"part{index}.py").write_text(
            "x = 1\n" * min(300, total - start), encoding="utf-8"
        )


@pytest.mark.parametrize(
    ("prefix", "owner", "limit"),
    [
        (STORAGE, "snapshot-storage", 2000),
        ("src/craftreport/runtime", "runtime", 1500),
        ("src/craftreport/adapters", "adapters", 1500),
        ("scripts/browser_verification", "browser-verification", 3400),
    ],
)
def test_exact_source_boundaries(repository: Path, prefix: str, owner: str, limit: int) -> None:
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


def test_storage_local_bounds(repository: Path) -> None:
    directory = repository / STORAGE
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


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('capability_id = "snapshot-storage"', f'capability_id = "{owner}"')
        for owner in ("unknown", "runtime", "*")
    ]
    + [
        ("value = 2000", f"value = {value}")
        for value in ("0", "-1", "true", "2000.0", '"2000"', "2001", "1500", "3400")
    ]
    + [
        ('rule = "capability-lloc"', 'rule = "module-lloc"'),
        ('owner = "project-owner"', 'owner = " "'),
        ('owner = "project-owner"', 'owner = "unapproved-owner"'),
        ("value = 2000\napproved = true", "value = 2000\napproved = false"),
        (
            "[scope_approval.snapshot-runtime]\napproved = true",
            "[scope_approval.snapshot-runtime]\napproved = false",
        ),
        ('rationale = "Owner approved storage calibration"', 'rationale = ""'),
        (f'approval_reference = "{APPROVAL}"', 'approval_reference = "README.md"'),
        (f'approval_reference = "{APPROVAL}"\n', ""),
        (f'budget_amendment_reference = "{APPROVAL}"', 'budget_amendment_reference = "README.md"'),
        (
            'capability_ids = ["data", "runtime", "snapshot-storage"]',
            'capability_ids = ["snapshot-storage"]',
        ),
        ('"runtime", "snapshot-storage", "reporting"', '"runtime", "reporting"'),
        ("approved = true", "approved = false"),
        ("approved = true", "approved = 1"),
    ],
)
def test_invalid_metadata(repository: Path, old: str, new: str) -> None:
    path = repository / "quality.toml"
    policy = path.read_text(encoding="utf-8")
    assert old in policy
    changed = (
        policy.removesuffix(ENTRY) + ENTRY.replace(old, new)
        if old in ENTRY
        else policy.replace(old, new)
    )
    path.write_text(changed, encoding="utf-8")
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
    source(repository, STORAGE, 1501)
    report = check(repository)
    assert report.errors == []
    assert [v.message for v in report.violations] == ["1501 > 1500"]
