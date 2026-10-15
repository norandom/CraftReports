"""Real source fixtures exercise the approved browser-only aggregate budget."""

import tempfile
import unittest
from pathlib import Path

from check_quality import check

ROOT = Path(__file__).resolve().parents[2]
APPROVAL = ".kiro/specs/craftreport-browser-verification/lifecycle-evidence-budget-amendment.md"
PREVIOUS_APPROVAL = ".kiro/specs/craftreport-browser-verification/budget-amendment.md"
ENTRY = (
    '\n[[capability_limits.entries]]\ncapability_id = "browser-verification"\n'
    'rule = "capability-lloc"\nvalue = 3400\napproved = true\nowner = "project-owner"\n'
    'rationale = "Reviewed browser calibration"\n'
    f'approval_reference = "{APPROVAL}"\n'
)


class BrowserBudgetTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.policy = (ROOT / "quality.toml").read_text(encoding="utf-8")
        self.policy = self.policy.split("\n[capability_limits]")[0] + ENTRY
        self.write("quality.toml", self.policy)
        self.write(APPROVAL, (ROOT / APPROVAL).read_text(encoding="utf-8"))
        self.write(
            "breadth.toml",
            '[capability.application]\nowner = ["src"]\n'
            '[capability.development-gates]\nowner = ["scripts", "tests"]\n'
            "[capability.browser-verification]\n"
            'owner = ["scripts/browser_verification", '
            '"scripts/examples/verify_gridcraft_browser.py", "tests/browser_verification"]\n',
        )

    def write(self, name: str, content: str) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def source(self, prefix: str, total: int) -> None:
        for index, start in enumerate(range(0, total, 300)):
            self.write(f"{prefix}/part{index}.py", "x = 1\n" * min(300, total - start))

    def test_browser_boundary_helpers_recipe_and_move_count_once(self) -> None:
        self.source("scripts/browser_verification/helpers", 3399)
        report = check(self.root)
        self.assertEqual(report.errors + report.violations, [])
        self.assertEqual(report.production_capabilities, {"browser-verification": 3399})
        self.write("scripts/examples/verify_gridcraft_browser.py", "x = 1\n")
        self.write("tests/browser_verification/test_large.py", "x = 1\n" * 3000)
        report = check(self.root)
        self.assertEqual(report.errors + report.violations, [])
        self.assertEqual(report.production_capabilities, {"browser-verification": 3400})
        self.assertEqual(report.test_capabilities, {"browser-verification": 3000})
        extra = self.write("scripts/browser_verification/extra.py", "x = 1\n")
        moved = self.root / "scripts/browser_verification/nested/tests/extra.py"
        moved.parent.mkdir(parents=True)
        extra.rename(moved)
        report = check(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.production_capabilities, {"browser-verification": 3401})
        self.assertEqual(
            [(v.rule, v.message) for v in report.violations], [("capability-lloc", "3401 > 3400")]
        )
        self.assertEqual(report.waived, [])

    def test_other_capability_keeps_default(self) -> None:
        self.source("src", 1500)
        report = check(self.root)
        self.assertEqual(report.errors + report.violations, [])
        self.assertEqual(report.production_capabilities, {"application": 1500})
        self.source("src", 1501)
        report = check(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(
            [(v.owner, v.message) for v in report.violations], [("application", "1501 > 1500")]
        )

    def test_development_gates_keeps_default(self) -> None:
        self.source("scripts/gates", 1500)
        report = check(self.root)
        self.assertEqual(report.errors + report.violations, [])
        self.assertEqual(report.production_capabilities, {"development-gates": 1500})
        self.source("scripts/gates", 1501)
        report = check(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(
            [(v.owner, v.message) for v in report.violations],
            [("development-gates", "1501 > 1500")],
        )

    def test_omitted_override_retains_default(self) -> None:
        self.write("quality.toml", self.policy.split("\n[[capability_limits.entries]]")[0])
        self.source("scripts/browser_verification", 1501)
        report = check(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual([v.message for v in report.violations], ["1501 > 1500"])

    def test_browser_local_limits_remain(self) -> None:
        self.write("scripts/browser_verification/module.py", "x = 1\n" * 300)
        self.write("scripts/browser_verification/function.py", "def work():\n" + "    x = 1\n" * 49)
        self.write(
            "scripts/browser_verification/branch.py",
            "def work(x):\n" + "    if x:\n        x = 1\n" * 9,
        )
        report = check(self.root)
        self.assertEqual(report.errors + report.violations, [])
        self.write("scripts/browser_verification/module.py", "x = 1\n" * 301)
        self.write("scripts/browser_verification/function.py", "def work():\n" + "    x = 1\n" * 50)
        self.write(
            "scripts/browser_verification/branch.py",
            "def work(x):  # noqa: C901\n" + "    if x:\n        x = 1\n" * 10,
        )
        report = check(self.root)
        self.assertEqual(report.errors, [])
        self.assertEqual(
            {v.rule for v in report.violations}, {"module-lloc", "function-lloc", "C901"}
        )

    def test_invalid_entries_fail_without_source(self) -> None:
        replacements = (
            ('capability_id = "browser-verification"', 'capability_id = "unknown"'),
            ('capability_id = "browser-verification"', 'capability_id = "application"'),
            ('capability_id = "browser-verification"', 'capability_id = "*"'),
            ('rule = "capability-lloc"', 'rule = "module-lloc"'),
            ('rule = "capability-lloc"', 'rule = "*"'),
            ("value = 3400", "value = 0"),
            ("value = 3400", "value = -1"),
            ("value = 3400", "value = true"),
            ("value = 3400", "value = 3400.0"),
            ("value = 3400", 'value = "3400"'),
            ("value = 3400", "value = 3401"),
            ("value = 3400", "value = 2800"),
            ('owner = "project-owner"', 'owner = " "'),
            ('rationale = "Reviewed browser calibration"', 'rationale = ""'),
            (f'approval_reference = "{APPROVAL}"', 'approval_reference = ""'),
            (f'approval_reference = "{APPROVAL}"', 'approval_reference = "README.md"'),
            (f'approval_reference = "{APPROVAL}"', f'approval_reference = "{PREVIOUS_APPROVAL}"'),
        )
        for old, new in replacements:
            with self.subTest(new=new):
                self.write("quality.toml", self.policy.replace(old, new))
                self.assertTrue(check(self.root).errors)

    def test_duplicate_missing_unapproved_and_wrong_scope(self) -> None:
        policies = (
            self.policy + ENTRY,
            self.policy.replace(f'approval_reference = "{APPROVAL}"\n', ""),
            self.policy.replace(', "browser-verification"', ""),
            self.policy.replace("approved = true", "approved = false"),
            self.policy.replace(
                'capability_id = "browser-verification"', 'capability_id = "application"', 1
            ),
            self.policy.replace("[[capability_limits.entries]]", "[capability_limits.entries]"),
            self.policy + 'exact_path_or_rule = "*"\n',
            self.policy.replace("approved = true\nowner", "approved = false\nowner"),
            self.policy.replace(
                f'budget_amendment_reference = "{APPROVAL}"',
                f'budget_amendment_reference = "{PREVIOUS_APPROVAL}"',
            ),
            self.policy.replace('owner = "project-owner"\n', ""),
            self.policy.replace('rationale = "Reviewed browser calibration"\n', ""),
        )
        for policy in policies:
            with self.subTest(policy=policy):
                self.write("quality.toml", policy)
                self.assertTrue(check(self.root).errors)
        self.write("quality.toml", self.policy)
        (self.root / APPROVAL).unlink()
        self.assertTrue(check(self.root).errors)
