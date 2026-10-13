"""Checks for the installable engineering foundation, without product behavior."""

import importlib
import importlib.metadata
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check.py"


class BootstrapTests(unittest.TestCase):
    def test_distribution_is_importable(self) -> None:
        package = importlib.import_module("craftreport")
        self.assertIsNotNone(package.__file__)
        self.assertEqual(importlib.metadata.version("craftreport"), "0.1.0")

    def test_unimplemented_modes_report_unavailable(self) -> None:
        for mode in ("--fast", "--integration"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [sys.executable, str(CHECK), mode],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unavailable", result.stderr.lower())
                self.assertIn(mode.removeprefix("--"), result.stderr)

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
