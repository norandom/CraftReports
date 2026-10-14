"""Checks for the installable engineering foundation, without product behavior."""

import importlib
import importlib.metadata
import subprocess
import sys
import unittest
from pathlib import Path

from check import integration_steps

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check.py"


class BootstrapTests(unittest.TestCase):
    def test_distribution_is_importable(self) -> None:
        package = importlib.import_module("craftreport")
        self.assertIsNotNone(package.__file__)
        self.assertEqual(importlib.metadata.version("craftreport"), "0.1.0")

    def test_integration_routes_to_separate_installed_client_suite(self) -> None:
        directory = ROOT / "artifacts" / "routing-only"
        steps = integration_steps(ROOT, directory)
        self.assertEqual(len(steps), 1)
        command = steps[0][1]
        self.assertEqual(command[0], sys.executable)
        self.assertIn(str(ROOT / "tests/kernel"), command)
        self.assertEqual(command[command.index("-m", 3) + 1], "integration")
        self.assertEqual(command[command.index("--kernel-run-dir") + 1], str(directory))
        self.assertIn("--junitxml", command)
        self.assertIn(str(directory / "junit.xml"), command)

    def test_command_requires_exactly_one_mode(self) -> None:
        for modes in ([], ["--fast", "--integration"]):
            with self.subTest(modes=modes):
                result = subprocess.run(
                    [sys.executable, str(CHECK), *modes],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)
