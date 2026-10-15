"""Real gate checks over disposable violations, with CLI smoke/error coverage."""

import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import check_breadth
import check_imports

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
        module_count = sum(
            path.suffix in {".py", ".pyi"}
            for path in (self.root / "src/craftreport").rglob("*")
            if path.is_file()
        )
        self.ledger = "\n".join(
            f"actual_python_modules = {module_count}"
            if line.startswith("actual_python_modules =")
            else line
            for line in self.ledger.splitlines()
        )
        self.write("breadth.toml", self.ledger)
        meta = cast(dict[str, object], tomllib.loads(self.ledger)["meta"])
        self.baseline_front_ids = cast(list[str], meta["open_front_ids"])
        self.baseline_front_count = cast(int, meta["open_fronts"])

    def write(self, path: str, content: str) -> None:
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def run_gate(self, gate: str, expected: int = 0, *, cli: bool = False) -> dict[str, object]:
        if not cli:
            report = self.direct_gate(gate)
            self.assertEqual(int(bool(report["errors"])), expected, report)
            return report
        result = subprocess.run(
            [sys.executable, str(ROOT / f"scripts/check_{gate}.py"), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return cast(dict[str, object], json.loads(result.stdout))

    def direct_gate(self, gate: str) -> dict[str, object]:
        return {"breadth": check_breadth.check, "imports": check_imports.check}[gate](self.root)

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
        phases = {
            path.parent.name: cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))[
                "phase"
            ]
            for path in (self.root / ".kiro/specs").glob("*/spec.json")
        }
        report = self.run_gate("breadth", cli=True)
        self.assertEqual(report["phases"], phases)
        self.assertIn("actual_python_modules", str(report["counts"]))
        self.run_gate("imports", cli=True)

    def test_stale_counts(self) -> None:
        for key in (
            "spec_count",
            "generated_task_sets",
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

    def test_unregistered_spec_and_unapproved_implementation(self) -> None:
        original = self.root / ".kiro/specs/craftreport-operation-kernel/spec.json"
        spec = cast(dict[str, object], json.loads(original.read_text(encoding="utf-8")))
        spec["feature_name"] = "surprise"
        self.write(".kiro/specs/surprise/spec.json", json.dumps(spec))
        self.assertIn("unregistered spec: surprise", str(self.run_gate("breadth", 1)))
        self.write(
            "breadth.toml",
            self.scope_ledger(self.ledger, remove=("craftreport-operation-kernel",)),
        )
        self.assertIn(
            "unapproved implementation scope: craftreport-operation-kernel",
            str(self.run_gate("breadth", 1)),
        )

    def scope_ledger(
        self, ledger: str, *, remove: tuple[str, ...] = (), add: tuple[str, ...] = ()
    ) -> str:
        meta = cast(dict[str, object], tomllib.loads(ledger)["meta"])
        scopes = cast(list[str], meta["approved_spec_scopes"])
        scopes = sorted({scope for scope in scopes if scope not in remove} | set(add))
        return "\n".join(
            f"approved_spec_scopes = {json.dumps(scopes)}"
            if line.startswith("approved_spec_scopes =")
            else line
            for line in ledger.splitlines()
        )

    def pending_task_spec(self, phase: str = "tasks-generated") -> dict[str, object]:
        path = ".kiro/specs/craftreport-browser-verification/spec.json"
        data = cast(dict[str, object], json.loads((self.root / path).read_text(encoding="utf-8")))
        data.update(phase=phase, ready_for_implementation=False)
        data["approvals"] = {
            "requirements": {"generated": True, "approved": True},
            "design": {"generated": True, "approved": True},
            "tasks": {"generated": True, "approved": False},
        }
        self.write(path, json.dumps(data))
        generated = sum(
            json.loads(item.read_text(encoding="utf-8"))["approvals"]["tasks"]["generated"]
            for item in (self.root / ".kiro/specs").glob("*/spec.json")
        )
        self.write(
            "breadth.toml",
            "\n".join(
                f"generated_task_sets = {generated}"
                if line.startswith("generated_task_sets =")
                else line
                for line in self.scope_ledger(
                    self.ledger, remove=("craftreport-browser-verification",)
                ).splitlines()
            ),
        )
        return data

    def test_registered_generated_tasks_can_await_human_review(self) -> None:
        baseline = cast(dict[str, int], self.direct_gate("breadth")["counts"])
        self.pending_task_spec()
        report = self.run_gate("breadth")
        self.assertEqual(
            cast(dict[str, int], report["counts"])["generated_task_sets"],
            baseline["generated_task_sets"],
        )
        self.assertEqual(
            cast(dict[str, str], report["phases"])["craftreport-browser-verification"],
            "tasks-generated",
        )

    def test_pending_tasks_cannot_claim_implementation_approval(self) -> None:
        self.pending_task_spec()
        path = self.root / "breadth.toml"
        ledger = path.read_text(encoding="utf-8")
        self.write(
            "breadth.toml",
            self.scope_ledger(ledger, add=("craftreport-browser-verification",)),
        )
        self.assertIn("not implementation-approved", str(self.run_gate("breadth", 1)))

    def test_implementation_phases_require_scope_and_all_approvals(self) -> None:
        path = ".kiro/specs/craftreport-browser-verification/spec.json"
        for phase in ("implementation-in-progress", "implementation-complete"):
            for missing in ("ready_for_implementation", "requirements", "design", "tasks", None):
                with self.subTest(phase=phase, missing=missing):
                    data = self.pending_task_spec(phase)
                    data["ready_for_implementation"] = missing != "ready_for_implementation"
                    approvals = cast(dict[str, dict[str, bool]], data["approvals"])
                    for stage, values in approvals.items():
                        values["approved"] = stage != missing
                    self.write(path, json.dumps(data))
                    errors = str(self.run_gate("breadth", 1)["errors"])
                    self.assertIn("unapproved implementation scope", errors)
                    if missing is not None:
                        self.assertIn("not implementation-approved", errors)
                    else:
                        self.assertNotIn("not implementation-approved", errors)

    def test_pending_task_registration_and_generated_flag_remain_required(self) -> None:
        data = self.pending_task_spec()
        path = ".kiro/specs/craftreport-browser-verification/spec.json"
        approvals = cast(dict[str, dict[str, bool]], data["approvals"])
        approvals["tasks"]["generated"] = False
        self.write(path, json.dumps(data))
        self.assertIn("inconsistent generated tasks", str(self.run_gate("breadth", 1)))
        self.pending_task_spec()
        path_ledger = self.root / "breadth.toml"
        ledger = path_ledger.read_text(encoding="utf-8")
        self.write(
            "breadth.toml",
            ledger.replace(
                "[spec.craftreport-browser-verification]",
                "[spec.unregistered-browser-verification]",
            ),
        )
        self.assertIn("unregistered spec", str(self.run_gate("breadth", 1)))

    def test_approval_and_metadata_fail_closed(self) -> None:
        path = ".kiro/specs/craftreport-operation-kernel/spec.json"
        data = cast(dict[str, object], json.loads((self.root / path).read_text(encoding="utf-8")))
        data["ready_for_implementation"] = False
        self.write(path, json.dumps(data))
        self.assertIn("not implementation-approved", str(self.run_gate("breadth", 1)))
        self.write(path, "{broken")
        self.assertIn("spec.json", str(self.run_gate("breadth", 1, cli=True)))

    def test_unknown_unapproved_and_most_specific_parked_owners(self) -> None:
        for path, diagnostic in (
            ("src/craftreport/mystery/code.py", "unknown ownership"),
            ("src/craftreport/reporting/code.py", "unapproved ownership: reporting"),
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

    def declare_fronts(self, ledger: str, identities: list[str], count: int) -> str:
        return "\n".join(
            f"open_fronts = {count}"
            if line.startswith("open_fronts =")
            else f"open_front_ids = {json.dumps(identities)}"
            if line.startswith("open_front_ids =")
            else line
            for line in ledger.splitlines()
        )

    def retirement(self, since: str, extra: str = "") -> None:
        entry = (
            '\n[capability.old]\nkind = "tooling"\nstatus = "retiring"\n'
            'line = "quality-verification"\nowner = ["old"]\n'
            'closure_required = true\nclose_targets = ["old/code.py"]\n'
            f'status_since = "{since}"\naccountable_owner = "maintainer"\n' + extra
        )
        ledger = self.declare_fronts(
            self.ledger,
            [*self.baseline_front_ids, "capability.old"],
            self.baseline_front_count + 1,
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
            self.declare_fronts(ledger, self.baseline_front_ids, self.baseline_front_count),
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

    def test_snapshot_allowed_dependencies(self) -> None:
        cases = {
            "data/values.py": "from decimal import Decimal\nfrom ..contracts import values\n",
            "data/ports.py": (
                "from craftreport.application.service_values import Missing as M, "
                "VersionConflict, ServiceUnavailable\nfrom .values import Snapshot\n"
            ),
            "runtime/publication.py": (
                "from ..data import ports\nfrom ..application import ports as kernel_ports\n"
                "from craftreport.application.registry import OperationBinding\n"
                "from craftreport.application.capabilities import CapabilityInstance\n"
                "from craftreport.application.outcomes import outcome_update, OutcomeFacts\n"
                "from craftreport.application.journal_values import ReceiptUpdate\n"
            ),
            "adapters/storage/schema.py": (
                "import sqlite3\nfrom sqlalchemy import Table\nfrom ...runtime import values\n"
                "from craftreport.application.dispatch_ports import RetainedResult\n"
                "from .database import Database\n"
            ),
            "adapters/snapshot_wire.py": "from ..data import values\nfrom ..runtime import ports\n",
            "composition/snapshot_host.py": "from ..adapters.storage import providers\n",
        }
        for path, source in cases.items():
            self.write(f"src/craftreport/{path}", source)
        self.run_gate("imports", cli=True)

    def test_snapshot_forbidden_dependencies(self) -> None:
        cases = (
            ("data/values.py", "from ..application.service_values import Missing"),
            ("data/ports.py", "from ..application.service_values import ResourceSnapshot"),
            ("data/ports.py", "from ..application.service_values import *"),
            ("data/ports.py", "import craftreport.application.service_values as services"),
            ("data/ports/helpers.py", "from ...application.service_values import Missing"),
            ("data/values.py", "from ..runtime import values"),
            ("data/values.py", "import sqlite3"),
            ("data/values.py", "import pydantic"),
            ("data/values.py", "import polars"),
            ("data/values.py", "from ..adapters.storage import database"),
            ("runtime/publication.py", "from ..reporting import compiler"),
            ("runtime/publication.py", "from ..themes import values"),
            ("runtime/publication.py", "from ..policies import checks"),
            ("runtime/publication.py", "from ..application import dispatch"),
            ("runtime/publication.py", "from ..adapters.storage import snapshots"),
            ("runtime/publication.py", "import sqlalchemy"),
            ("runtime/publication.py", "import sqlite3"),
            ("runtime/publication.py", "import fastapi"),
            ("adapters/storage/schema.py", "from ...reporting import compiler"),
            ("adapters/storage/schema.py", "from ...application import dispatch"),
            ("adapters/storage/schema.py", "from .. import snapshot_wire"),
            ("adapters/storage/schema.py", "import fastapi"),
            ("adapters/storage/schema.py", "import duckdb"),
        )
        for path, source in cases:
            with self.subTest(path=path, source=source):
                fixture = f"src/craftreport/{path}"
                self.write(fixture, source + "\n")
                report = str(self.run_gate("imports", 1))
                self.assertIn(f"{fixture}:1: forbidden import:", report)
                if path.startswith("adapters/storage/"):
                    self.assertIn("snapshot-storage ->", report)
                (self.root / fixture).unlink()

    def test_invalid_syntax_and_unresolved_relative_imports(self) -> None:
        for source in ("from ....adapters import bad\n", "def broken(:\n"):
            self.write("src/craftreport/contracts/value.py", source)
            self.assertIn(
                "src/craftreport/contracts/value.py", str(self.run_gate("imports", 1, cli=True))
            )

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
