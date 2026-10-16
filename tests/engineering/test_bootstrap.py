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
        self.assertEqual(len(steps), 4)
        command = steps[0][1]
        self.assertEqual(command[0], sys.executable)
        self.assertIn(str(ROOT / "tests/kernel"), command)
        self.assertNotIn("integration", command)
        self.assertEqual(command[command.index("--kernel-run-dir") + 1], str(directory))
        self.assertIn("--junitxml", command)
        self.assertIn(str(directory / "junit.xml"), command)
        self.assertEqual(
            steps[1][1],
            [sys.executable, str(ROOT / "tests/kernel/catalog_proof.py"), str(directory)],
        )
        durable = steps[2][1]
        self.assertIn(str(ROOT / "tests/snapshot_runtime/test_installed.py"), durable)
        self.assertEqual(durable[durable.index("-m", 3) + 1], "integration")
        self.assertIn(str(directory / "snapshot-junit.xml"), durable)
        self.assertNotIn("-n", durable)
        app = steps[3][1]
        self.assertIn(str(ROOT / "tests/gridcraft/test_app_installed.py"), app)
        self.assertIn(str(directory / "gridcraft-junit.xml"), app)
        self.assertEqual(app[app.index("-m", 3) + 1], "integration")

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
