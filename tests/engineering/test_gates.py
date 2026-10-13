"""Disposable repositories prove the quality gate's externally observable results."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/check_quality.py"


class QualityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.policy = (ROOT / "quality.toml").read_text(encoding="utf-8")
        self.write("quality.toml", self.policy)
        self.write(
            "breadth.toml",
            '[capability.application]\nowner = ["src", "packages/demo"]\n'
            '[capability.development-gates]\nowner = ["scripts", "tests"]\n',
        )

    def write(self, path: str, content: str) -> Path:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination

    def run_gate(self, expected: int = 0) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(GATE), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return cast(dict[str, object], json.loads(result.stdout))

    def test_function_boundary(self) -> None:
        for size in (50, 51):
            with self.subTest(size=size):
                self.write("src/work.py", "def work():\n" + "    x = 1\n" * (size - 1))
                report = self.run_gate(int(size > 50))
                self.assertIn(f'"lloc": {size}', json.dumps(report))
                if size > 50:
                    self.assertIn("function-lloc", str(report["violations"]))

    def test_module_boundary(self) -> None:
        for size in (300, 301):
            with self.subTest(size=size):
                self.write("src/work.py", "x = 1\n" * size)
                report = self.run_gate(int(size > 300))
                if size > 300:
                    self.assertIn("module-lloc", str(report["violations"]))

    def test_capability_boundary_and_move(self) -> None:
        for index in range(5):
            self.write(f"src/part{index}.py", "x = 1\n" * 300)
        report = self.run_gate()
        self.assertEqual(report["production_capabilities"], {"application": 1500})
        self.write("src/extra.py", "x = 1\n")
        self.assertIn("capability-lloc", str(self.run_gate(1)["violations"]))
        hidden = self.root / "src/tests/extra.py"
        hidden.parent.mkdir()
        (self.root / "src/extra.py").rename(hidden)
        self.assertEqual(self.run_gate(1)["production_capabilities"], {"application": 1501})
        destination = self.root / "packages/demo/moved.py"
        destination.parent.mkdir(parents=True)
        hidden.rename(destination)
        self.assertEqual(self.run_gate(1)["production_capabilities"], {"application": 1501})

    def test_branching_boundary_ignores_noqa(self) -> None:
        for complexity in (10, 11):
            with self.subTest(complexity=complexity):
                source = "def branch(x):  # noqa: C901\n"
                source += "    if x:\n        x = 1\n" * (complexity - 1)
                self.write("src/branch.py", source)
                report = self.run_gate(int(complexity > 10))
                if complexity > 10:
                    self.assertIn("C901", str(report["violations"]))

    def test_decorated_async_nested_multiline_extraction(self) -> None:
        self.write(
            "src/functions.py",
            "@decorate(\n    1,\n)\nasync def outer():\n"
            "    # ignored comment\n\n"
            "    @decorate(2)\n    def inner():\n"
            "        value = (\n            1 + 2\n        )\n"
            "        return value\n    return inner()\n",
        )
        report = self.run_gate()
        self.assertEqual(report["production_capabilities"], {"application": 7})
        functions = cast(list[dict[str, object]], report["functions"])
        self.assertEqual(
            [(row["name"], row["lloc"]) for row in functions], [("outer", 7), ("outer.inner", 4)]
        )

    def test_tests_measured_separately(self) -> None:
        self.write("src/real.py", "x = 1\n")
        self.write("tests/test_large.py", "x = 1\n" * 1501)
        self.write("packages/demo/tests/test_nested.py", "x = 1\n" * 301)
        report = self.run_gate()
        self.assertEqual(report["production_capabilities"], {"application": 1})
        self.assertEqual(
            report["test_capabilities"], {"application": 301, "development-gates": 1501}
        )

    def test_parenthesized_decorator_includes_at_sign(self) -> None:
        self.write("src/decorated.py", "@(\n    decorate\n)\ndef work():\n    return 1\n")
        report = self.run_gate()
        functions = cast(list[dict[str, object]], report["functions"])
        self.assertEqual(functions[0]["line"], 1)
        self.assertEqual(functions[0]["lloc"], 3)

    def test_missing_waiver_approval_and_duplicate_ids_fail(self) -> None:
        self.waiver("module-lloc", "2099-01-01")
        valid = (self.root / "quality.toml").read_text(encoding="utf-8")
        self.write(
            "quality.toml",
            valid.replace('approval_reference = "review/1"', 'approval_reference = ""'),
        )
        self.assertIn("approval_reference", str(self.run_gate(1)["errors"]))
        self.write(
            "quality.toml",
            valid + "\n[[waivers.entries]]\n" + valid.split("[[waivers.entries]]\n")[1],
        )
        self.assertIn("duplicate waiver", str(self.run_gate(1)["errors"]))

    def test_declared_generated_vendor_exclusions_are_visible_in_policy(self) -> None:
        policy = self.policy.replace(
            "[measurement.lloc]", '[measurement.lloc]\nexcluded_paths = ["src/vendor"]'
        )
        self.write("quality.toml", policy)
        self.write("src/vendor/thirdparty.py", "x = 1\n" * 301)
        self.write("src/owned.py", "x = 1\n")
        report = self.run_gate()
        self.assertEqual(report["production_capabilities"], {"application": 1})
        self.assertEqual(report["excluded_paths"], ["src/vendor"])

    def test_most_specific_owner_and_unique_files(self) -> None:
        self.write(
            "breadth.toml",
            '[capability.application]\nowner = ["src", "src/base"]\n'
            '[capability.contracts]\nowner = ["src/base/special"]\n',
        )
        self.write("src/base/a.py", "x = 1\n")
        self.write("src/base/special/b.pyi", "def b() -> int: ...\n")
        report = self.run_gate()
        self.assertEqual(report["production_capabilities"], {"application": 1, "contracts": 2})

    def test_unknown_owner_fails(self) -> None:
        self.write("packages/unowned/code.py", "x = 1\n")
        self.assertIn("unknown ownership", str(self.run_gate(1)["errors"]))

    def test_ambiguous_owner_fails(self) -> None:
        self.write(
            "breadth.toml",
            '[capability.application]\nowner = ["src"]\n[capability.contracts]\nowner = ["src"]\n',
        )
        self.write("src/code.py", "x = 1\n")
        self.assertIn("ambiguous ownership", str(self.run_gate(1)["errors"]))

    def test_unapproved_capability_has_no_silent_unlimited_budget(self) -> None:
        self.write("breadth.toml", '[capability.future]\nowner = ["src"]\n')
        self.write("src/code.py", "x = 1\n")
        self.assertIn("unapproved budget", str(self.run_gate(1)["errors"]))

    def test_invalid_syntax_fails(self) -> None:
        self.write("src/broken.py", "def broken(:\n")
        self.assertIn("extraction", str(self.run_gate(1)["errors"]))

    def waiver(self, scope: str, expires: str) -> None:
        entry = (
            '[[waivers.entries]]\nid = "review-1"\ncapability_id = "application"\n'
            f'exact_path_or_rule = "{scope}"\nowner = "maintainer"\n'
            'reason = "Reviewed temporary fixture"\napproval_reference = "review/1"\n'
            f'expires_at = "{expires}"\n'
        )
        self.write("quality.toml", self.policy.replace("entries = []\n", "") + "\n" + entry)

    def test_exact_approved_waiver_is_visible(self) -> None:
        self.write("src/large.py", "x = 1\n" * 301)
        self.waiver("src/large.py", "2099-01-01")
        report = self.run_gate()
        self.assertIn("review-1", str(report["waived"]))
        self.assertEqual(report["production_capabilities"], {"application": 301})

    def test_rule_waiver_remains_capability_scoped(self) -> None:
        self.waiver("module-lloc", "2099-01-01")
        self.write("scripts/large.py", "x = 1\n" * 301)
        self.assertIn("module-lloc", str(self.run_gate(1)["violations"]))

    def test_invalid_waivers_fail_even_without_violation(self) -> None:
        expired = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        for scope, expiry in (
            ("*", "2099-01-01"),
            ("src", "2099-01-01"),
            ("src/missing.py", "2099-01-01"),
            ("module-lloc", expired),
            ("module-lloc", "never"),
        ):
            with self.subTest(scope=scope, expiry=expiry):
                self.waiver(scope, expiry)
                self.assertIn("waiver", str(self.run_gate(1)["errors"]))

    def test_scripts_included_without_git_or_ruff_config(self) -> None:
        self.write("scripts/untracked.py", "x = 1\n" * 301)
        self.write(".gitignore", "scripts/\n")
        self.write("ruff.toml", 'exclude = ["scripts"]\n')
        self.assertIn("module-lloc", str(self.run_gate(1)["violations"]))
