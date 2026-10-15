"""The pipeline executes real commands and fails before later effects."""

import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from check import fast_steps, integration_steps, run_steps


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def command(self, source: str) -> list[str]:
        return [sys.executable, "-c", source]

    def test_fast_tests_use_three_file_grouped_workers(self) -> None:
        for packages in (False, True):
            with self.subTest(packages=packages):
                if packages:
                    (self.root / "packages").mkdir()
                command = fast_steps(self.root)[-1][1]
                scope = ["tests", "packages"] if packages else ["tests"]
                self.assertEqual(
                    command,
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "-n",
                        "3",
                        "--dist",
                        "loadfile",
                        "-m",
                        "not integration",
                        *scope,
                    ],
                )

    def test_integration_keeps_serial_packet_ownership(self) -> None:
        command = integration_steps(self.root, self.root / "evidence")[0][1]
        self.assertNotIn("-n", command)
        self.assertNotIn("--numprocesses", command)
        self.assertNotIn("--dist", command)
        self.assertNotIn("-m", command[3:])
        self.assertEqual(
            command[command.index("--kernel-run-dir") + 1], str(self.root / "evidence")
        )
        root = Path(__file__).resolve().parents[2]
        config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            config["tool"]["pytest"]["ini_options"]["addopts"], "--strict-config --strict-markers"
        )

    def test_success_runs_in_project_root(self) -> None:
        result = run_steps(
            self.root,
            [
                (
                    "write",
                    self.command("from pathlib import Path; Path('effect').write_text('real')"),
                )
            ],
        )
        self.assertEqual(result, 0)
        self.assertEqual((self.root / "effect").read_text(), "real")

    def test_failure_stops_later_commands(self) -> None:
        steps = [
            ("earlier", self.command("from pathlib import Path; Path('earlier').touch()")),
            ("reject", self.command("raise SystemExit(7)")),
            ("later", self.command("from pathlib import Path; Path('later').touch()")),
        ]
        self.assertEqual(run_steps(self.root, steps), 1)
        self.assertTrue((self.root / "earlier").is_file())
        self.assertFalse((self.root / "later").exists())

    def test_missing_executable_fails(self) -> None:
        self.assertEqual(run_steps(self.root, [("missing", [str(self.root / "absent")])]), 1)
