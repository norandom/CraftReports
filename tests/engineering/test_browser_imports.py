"""Browser tooling isolation checks against disposable actual source trees."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import check_imports

ROOT = Path(__file__).resolve().parents[2]


class BrowserImportTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.write(
            "breadth.toml",
            '[capability.composition]\nowner = ["src/craftreport"]\n'
            "[capability.browser-verification]\n"
            'owner = ["scripts/browser_verification", '
            '"scripts/examples/verify_gridcraft_browser.py"]\n',
        )

    def write(self, path: str, source: str) -> None:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")

    def test_production_cannot_import_harness_or_browser_dependencies(self) -> None:
        for source in (
            "import browser_verification.browser\n",
            "from browser_verification import journey\n",
            "from scripts import browser_verification\n",
            "from scripts.examples import verify_gridcraft_browser\n",
            "import examples.verify_gridcraft_browser\n",
            "from playwright.sync_api import sync_playwright\n",
            "from PIL import Image\n",
        ):
            with self.subTest(source=source):
                self.write("src/craftreport/bootstrap.py", source)
                errors = str(check_imports.check(self.root)["errors"])
                self.assertIn("forbidden import: composition ->", errors)
                self.assertIn("src/craftreport/bootstrap.py:1", errors)

    def test_tooling_cannot_import_production_implementation(self) -> None:
        for path in (
            "scripts/browser_verification/browser.py",
            "scripts/examples/verify_gridcraft_browser.py",
        ):
            for source in (
                "import craftreport.adapters\n",
                "from craftreport import interfaces\n",
                "from craftreport.composition.app import app\n",
                "from craftreport import bootstrap\n",
            ):
                with self.subTest(path=path, source=source):
                    self.write(path, source)
                    errors = str(check_imports.check(self.root)["errors"])
                    self.assertIn("forbidden import: browser-verification ->", errors)
                    self.assertIn(f"{path}:1", errors)

    def test_allowed_tooling_and_production_imports(self) -> None:
        self.write("src/craftreport/bootstrap.py", "from craftreport.contracts import values\n")
        self.write(
            "scripts/browser_verification/browser.py",
            "from playwright.sync_api import sync_playwright\nfrom PIL import Image\n"
            "from craftreport.contracts import values\n"
            "from craftreport.application.ports import Port\nfrom . import config\n",
        )
        self.write(
            "scripts/examples/verify_gridcraft_browser.py",
            "from browser_verification import journey\n",
        )
        report = check_imports.check(self.root)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["checked_files"], 3)

    def test_cli_rejects_tooling_violation(self) -> None:
        self.write("scripts/browser_verification/browser.py", "import craftreport.adapters\n")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_imports.py"), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("forbidden import", str(json.loads(result.stdout)))
