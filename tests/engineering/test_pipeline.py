"""The pipeline executes real commands and fails before later effects."""

import sys
import tempfile
import unittest
from pathlib import Path

from check import run_steps


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def command(self, source: str) -> list[str]:
        return [sys.executable, "-c", source]

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
