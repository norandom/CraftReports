"""Real subprocess checks over disposable boundary violations."""

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]


class BoundaryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ("breadth.toml",):
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / ".kiro/specs", self.root / ".kiro/specs")
        self.write("src/craftreport/__init__.py", '"""Bootstrap."""\n')
        self.ledger = (self.root / "breadth.toml").read_text(encoding="utf-8")
        self.ledger = self.ledger.replace("actual_python_modules = 0", "actual_python_modules = 1")
        self.write("breadth.toml", self.ledger)

    def write(self, path: str, content: str) -> None:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def run_gate(self, gate: str, expected: int = 0) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(ROOT / f"scripts/check_{gate}.py"), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return cast(dict[str, object], json.loads(result.stdout))

    def direct_gate(self, gate: str) -> dict[str, object]:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            module = importlib.import_module(f"check_{gate}")
        finally:
            sys.path.pop(0)
        check = cast(Callable[[Path], dict[str, object]], module.check)
        return check(self.root)

    def test_generated_phase_requires_its_generated_artifact(self) -> None:
        path = ".kiro/specs/craftreport-reporting-facade/spec.json"
        original = (self.root / path).read_text(encoding="utf-8")
        for stage in ("requirements", "design"):
            with self.subTest(stage=stage):
                spec = cast(dict[str, object], json.loads(original))
                spec["phase"] = f"{stage}-generated"
                approvals = cast(dict[str, object], spec["approvals"])
                approvals[stage] = {"generated": False, "approved": False}
                self.write(path, json.dumps(spec))
                errors = str(self.direct_gate("breadth")["errors"])
                self.assertIn(f"inconsistent generated {stage}", errors)
                approvals[stage] = {"generated": True, "approved": False}
                self.write(path, json.dumps(spec))
                self.assertEqual(self.direct_gate("breadth")["errors"], [])

    def namespace_plugins(self) -> None:
        self.write(
            "breadth.toml",
            self.ledger + "\n[capability.plugin_a]\n"
            'owner = ["packages/plugin-a"]\n[capability.plugin_b]\n'
            'owner = ["packages/plugin-b"]\n',
        )
        self.write("packages/plugin-a/src/shared_plugins/a/__init__.py", "x = 1\n")
        self.write("packages/plugin-b/src/shared_plugins/b/__init__.py", "x = 1\n")

    def test_shared_namespace_keeps_most_specific_package_ownership(self) -> None:
        self.namespace_plugins()
        path = "packages/plugin-b/src/shared_plugins/b/wire.py"
        for source in (
            "from shared_plugins.a import x\n",
            "from ..a import x\n",
            "from shared_plugins import a\n",
        ):
            with self.subTest(source=source):
                self.write(path, source)
                errors = str(self.direct_gate("imports")["errors"])
                self.assertIn(f"{path}:1", errors)
                self.assertIn("plugin_b -> shared_plugins.a", errors)
        for source in ("from shared_plugins.b import x\n", "from . import x\n"):
            with self.subTest(source=source):
                self.write(path, source)
                self.assertEqual(self.direct_gate("imports")["errors"], [])
        self.write(
            "packages/plugin-a/src/shared_plugins/a/wire.py", "from shared_plugins.a import x\n"
        )
        self.assertEqual(self.direct_gate("imports")["errors"], [])

    def test_duplicate_python_module_ownership_fails(self) -> None:
        self.namespace_plugins()
        self.write("packages/plugin-b/src/shared_plugins/a/__init__.py", "x = 2\n")
        errors = str(self.direct_gate("imports")["errors"])
        self.assertIn("ambiguous Python module ownership: shared_plugins.a", errors)

    def test_current_bootstrap_and_actual_phases(self) -> None:
        report = self.run_gate("breadth")
        self.assertIn("tasks-generated", str(report["phases"]))
        self.assertIn("actual_python_modules", str(report["counts"]))
        self.run_gate("imports")

    def test_stale_counts(self) -> None:
        for key in (
            "spec_count",
            "actual_python_modules",
            "planned_plugin_packages",
            "open_fronts",
        ):
            with self.subTest(key=key):
                lines = self.ledger.splitlines()
                self.write(
                    "breadth.toml",
                    "\n".join(
                        f"{key} = 999" if line.startswith(f"{key} =") else line for line in lines
                    ),
                )
                self.assertIn(f"stale count: {key}", str(self.run_gate("breadth", 1)))

    def test_unregistered_spec_and_unapproved_tasks(self) -> None:
        original = self.root / ".kiro/specs/craftreport-operation-kernel/spec.json"
        spec = cast(dict[str, object], json.loads(original.read_text(encoding="utf-8")))
        spec["feature_name"] = "surprise"
        self.write(".kiro/specs/surprise/spec.json", json.dumps(spec))
        self.assertIn("unregistered spec: surprise", str(self.run_gate("breadth", 1)))
        self.write(
            "breadth.toml",
            self.ledger.replace(
                'approved_spec_scopes = ["craftreport-operation-kernel"]',
                "approved_spec_scopes = []",
            ),
        )
        self.assertIn(
            "unapproved task scope: craftreport-operation-kernel", str(self.run_gate("breadth", 1))
        )

    def test_approval_and_metadata_fail_closed(self) -> None:
        path = ".kiro/specs/craftreport-operation-kernel/spec.json"
        data = cast(dict[str, object], json.loads((self.root / path).read_text(encoding="utf-8")))
        data["ready_for_implementation"] = False
        self.write(path, json.dumps(data))
        self.assertIn("not implementation-approved", str(self.run_gate("breadth", 1)))
        self.write(path, "{broken")
        self.assertIn("spec.json", str(self.run_gate("breadth", 1)))

    def test_unknown_unapproved_and_most_specific_parked_owners(self) -> None:
        for path, diagnostic in (
            ("src/craftreport/mystery/code.py", "unknown ownership"),
            ("src/craftreport/data/code.py", "unapproved ownership: data"),
            ("packages/craftreport-wordcraft/README.md", "parked ownership: wordcraft"),
        ):
            with self.subTest(path=path):
                self.write(path, "# fixture\n")
                self.assertIn(diagnostic, str(self.run_gate("breadth", 1)))
                (self.root / path).unlink()
        self.write(
            "breadth.toml",
            self.ledger + '\n[capability.hidden]\nkind = "module"\n'
            'status = "parked"\nline = "shared-reporting"\n'
            'owner = ["src/craftreport/application/hidden"]\nclosure_required = false\n'
            "close_targets = []\n",
        )
        self.write("src/craftreport/application/hidden/feature.py", "x = 1\n")
        self.assertIn("parked ownership: hidden", str(self.run_gate("breadth", 1)))

    def test_unknown_states_lines_and_ambiguous_ownership(self) -> None:
        for old, new, diagnostic in (
            ('status = "active"', 'status = "magic"', "unknown state"),
            ('line = "shared-reporting"', 'line = "other"', "unknown line"),
            (
                'owner = ["src/craftreport/contracts"]',
                'owner = ["src/craftreport/__init__.py"]',
                "ambiguous ownership",
            ),
        ):
            with self.subTest(diagnostic=diagnostic):
                self.write("breadth.toml", self.ledger.replace(old, new, 1))
                self.assertIn(diagnostic, str(self.run_gate("breadth", 1)))

    def retirement(self, since: str, extra: str = "") -> None:
        entry = (
            '\n[capability.old]\nkind = "tooling"\nstatus = "retiring"\n'
            'line = "quality-verification"\nowner = ["old"]\n'
            'closure_required = true\nclose_targets = ["old/code.py"]\n'
            f'status_since = "{since}"\naccountable_owner = "maintainer"\n' + extra
        )
        ledger = self.ledger.replace("open_fronts = 2", "open_fronts = 3").replace(
            '"spec.craftreport-operation-kernel"]',
            '"spec.craftreport-operation-kernel", "capability.old"]',
        )
        self.write("breadth.toml", ledger + entry)

    def test_retirement_utc_age(self) -> None:
        now = datetime.now(UTC)
        self.retirement((now - timedelta(days=13, hours=23)).isoformat())
        self.run_gate("breadth")
        self.retirement((now - timedelta(days=14, seconds=1)).isoformat())
        self.assertIn("overdue retirement: capability.old", str(self.run_gate("breadth", 1)))
        self.retirement("yesterday")
        self.assertIn("invalid status_since", str(self.run_gate("breadth", 1)))

    def test_closure_requires_matching_evidence(self) -> None:
        self.retirement(
            datetime.now(UTC).isoformat(),
            'closure_executed = true\nclosure_evidence = "evidence/old.json"\n',
        )
        self.assertIn("closure evidence", str(self.run_gate("breadth", 1)))
        self.write(
            "evidence/old.json",
            json.dumps(
                {"entry_id": "capability.other", "close_targets": ["old/code.py"], "executed": True}
            ),
        )
        self.assertIn("closure evidence", str(self.run_gate("breadth", 1)))
        self.write(
            "evidence/old.json",
            json.dumps(
                {"entry_id": "capability.old", "close_targets": ["old/code.py"], "executed": True}
            ),
        )
        ledger = (self.root / "breadth.toml").read_text(encoding="utf-8")
        self.write(
            "breadth.toml",
            ledger.replace("open_fronts = 3", "open_fronts = 2").replace(
                ', "capability.old"]', "]"
            ),
        )
        self.run_gate("breadth")
        self.write("old/code.py", "x = 1\n")
        self.assertIn("closure target still exists", str(self.run_gate("breadth", 1)))

    def test_forbidden_absolute_relative_and_aliased_imports(self) -> None:
        cases = (
            ("application/run.py", "from .. import adapters as a", "craftreport.adapters"),
            ("contracts/model.py", "import pydantic as p", "pydantic"),
            (
                "contracts/model.py",
                "from ..application import ports as p",
                "craftreport.application",
            ),
            (
                "application/run.py",
                "from ..adapters import validation as v",
                "craftreport.adapters",
            ),
            ("application/run.py", "import sqlite3", "sqlite3"),
            ("application/run.py", "from fastapi import Depends", "fastapi"),
            (
                "adapters/wire.py",
                "from craftreport import interfaces as i",
                "craftreport.interfaces",
            ),
            (
                "interfaces/http.py",
                "import craftreport.adapters.validation as v",
                "craftreport.adapters",
            ),
            ("interfaces/http.py", "from ..composition.app import app", "craftreport.composition"),
        )
        for path, source, target in cases:
            with self.subTest(path=path, source=source):
                self.write(f"src/craftreport/{path}", source + "\n")
                report = str(self.run_gate("imports", 1))
                self.assertIn(f"src/craftreport/{path}:1", report)
                self.assertIn(target, report)
                (self.root / "src/craftreport" / path).unlink()

    def test_allowed_layer_imports(self) -> None:
        self.write("src/craftreport/contracts/values.py", "from dataclasses import dataclass\n")
        self.write(
            "src/craftreport/application/run.py",
            "from ..contracts import values\nfrom .ports import Port\nimport asyncio\n",
        )
        self.write(
            "src/craftreport/adapters/wire.py",
            "from pydantic import BaseModel\nfrom craftreport.application import ports\n",
        )
        self.write(
            "src/craftreport/interfaces/http.py",
            "from fastapi import FastAPI\nfrom ..application import run\n",
        )
        self.write("src/craftreport/__init__.py", "from .composition.app import app\n")
        self.run_gate("imports")

    def test_invalid_syntax_and_unresolved_relative_imports(self) -> None:
        for source in ("from ....adapters import bad\n", "def broken(:\n"):
            self.write("src/craftreport/contracts/value.py", source)
            self.assertIn("src/craftreport/contracts/value.py", str(self.run_gate("imports", 1)))

    def test_capability_packages_cannot_import_each_others_implementation(self) -> None:
        self.write(
            "breadth.toml",
            self.ledger + "\n[capability.plugin_a]\n"
            'owner = ["packages/plugin-a"]\n[capability.plugin_b]\n'
            'owner = ["packages/plugin-b"]\n',
        )
        self.write(
            "packages/plugin-a/src/plugin_a/__init__.py",
            "from craftreport.contracts import values\n"
            "from craftreport.application.ports import Port\n",
        )
        self.write("packages/plugin-b/src/plugin_b/__init__.py", "x = 1\n")
        self.run_gate("imports")
        self.write("packages/plugin-a/src/plugin_a/wire.py", "import plugin_b as b\n")
        report = str(self.run_gate("imports", 1))
        self.assertIn("packages/plugin-a/src/plugin_a/wire.py:1", report)
        self.assertIn("plugin_a -> plugin_b", report)
