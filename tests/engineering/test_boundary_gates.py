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
            else "actual_plugin_packages = 0"
            if line.startswith("actual_plugin_packages =")
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
        self.write(
            "breadth.toml",
            self.ledger + '\n[capability.unapproved]\nkind = "configuration"\n'
            'status = "active"\nline = "craft-app-integration"\nowner = ["deploy/unapproved"]\n'
            "closure_required = false\nclose_targets = []\n",
        )
        for path, diagnostic in (
            ("src/craftreport/mystery/code.py", "unknown ownership"),
            ("deploy/unapproved/service.yaml", "unapproved ownership: unapproved"),
            ("deploy/service.yaml", "unknown ownership"),
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

    def test_gridcraft_exact_ownership_is_active_without_scaffolding(self) -> None:
        self.write(
            "breadth.toml",
            self.ledger.replace("actual_plugin_packages = 0", "actual_plugin_packages = 1"),
        )
        self.write("tests/gridcraft/test_future.py", "# test fixture\n")
        self.write("deploy/gridcraft-report/compose.yaml", "# deployment fixture\n")
        self.write("packages/craftreport-gridcraft/resources/report.html", "<!-- fixture -->\n")
        self.run_gate("breadth")

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
            "adapters/storage/serialization.py": (
                "from pydantic import TypeAdapter as Adapter, ValidationError\n"
                "from ..canonical import canonical_bytes\n"
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
            ("adapters/storage/serialization.py", "import pydantic"),
            ("adapters/storage/serialization.py", "from pydantic import BaseModel"),
            ("adapters/storage/serialization.py", "from pydantic import *"),
            ("adapters/storage/serialization.py", "from .. import canonical"),
            ("adapters/storage/serialization.py", "from ..canonical import fingerprint"),
            ("adapters/storage/serialization.py", "from ..canonical import *"),
            ("adapters/storage/serialization.py", "from ..transport_wire import receipt_to_wire"),
            ("adapters/storage/journal.py", "from pydantic import TypeAdapter"),
            ("adapters/storage/schema.py", "from pydantic import ValidationError"),
            ("adapters/storage/journal.py", "from ..canonical import canonical_bytes"),
            ("runtime/publication.py", "from pydantic import TypeAdapter"),
            ("data/values.py", "from pydantic import ValidationError"),
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

    def test_report_model_allowed_dependencies(self) -> None:
        cases = {
            "themes/values.py": "from ..contracts.pins import VersionPin\n",
            "themes/resolve.py": "from .values import SemanticRole\nimport dataclasses\n",
            "policies/values.py": "from ..contracts import ExpectedVersion\n",
            "policies/evaluate.py": "from .values import CheckScope\n",
            "reporting/definitions.py": (
                "from ..data.requirements import InputRequirements\n"
                "from ..themes.values import SemanticRole\n"
                "from ..policies.values import ReleasePolicy\n"
            ),
            "reporting/prepared.py": "from ..data.validation import validate_scalar\n",
            "reporting/prepare.py": (
                "from ..data.values import Snapshot\nfrom .prepared import PreparedReport\n"
                "from ..themes.resolve import resolve\nfrom ..policies.evaluate import evaluate\n"
            ),
            "reporting/ports.py": (
                "from ..application.service_values import ServiceUnavailable\n"
                "from ..contracts import EvidenceRef\nfrom .prepared import PreparedReport\n"
            ),
            "reporting/operations.py": (
                "from ..application.registry import OperationBinding, CommandBehavior\n"
                "from ..application.registry import QueryBehavior\n"
                "from ..application.ports import CommandContext, ReadContext\n"
                "from ..application.service_values import Missing, VersionConflict, "
                "ResourceSnapshot, GuardCurrent\n"
                "from ..application.service_values import ServiceUnavailable\n"
                "from ..contracts.outcomes import OutcomeProposal\n"
                "from ..data.ports import SnapshotReader\nfrom .ports import PackReader\n"
            ),
            "reporting/registration.py": (
                "from ..application.registry import Codec, BoundOperation, OperationBinding\n"
                "from ..application.service_values import DiagnosticPolicy\n"
            ),
            "adapters/report_models.py": "from ..reporting import definitions\nimport pydantic\n",
            "adapters/pack_reader.py": "from ..themes import values\nimport packaging\n",
            "adapters/report_resources.py": "from ..policies import values\n",
            "composition/reporting.py": "from ..reporting import operations\n",
        }
        for path, source in cases.items():
            self.write(f"src/craftreport/{path}", source)
        self.run_gate("imports", cli=True)

    def test_report_model_forbidden_dependencies(self) -> None:
        cases = (
            ("themes/values.py", "from ..reporting import definitions"),
            ("themes/resolve.py", "from ..data.values import Snapshot"),
            ("themes/values.py", "from ..policies import values"),
            ("policies/values.py", "from ..reporting.prepared import PreparedReport"),
            ("policies/evaluate.py", "from ..themes import values"),
            ("policies/values.py", "from ..data.values import Snapshot"),
            ("reporting/prepared.py", "from ..data.validation import *"),
            ("reporting/prepared.py", "from ..data import validation"),
            ("reporting/prepared.py", "import craftreport.data.validation as validation"),
            ("reporting/prepared.py", "from ..data.validation import validate_dataset"),
            ("reporting/prepare.py", "from ..data.validation import validate_scalar"),
            ("reporting/prepare.py", "from ..runtime import publication"),
            ("reporting/definitions.py", "from ..application.ports import CommandContext"),
            ("reporting/prepare.py", "from .operations import prepare"),
            ("reporting/prepare.py", "from . import ports"),
            ("reporting/prepared.py", "import craftreport.reporting.operations as ops"),
            ("reporting/prepare.py", "from ..data.ports import SnapshotReader"),
            ("reporting/operations.py", "from ..application import dispatch"),
            (
                "reporting/operations.py",
                "from ..application.registry import ImmutableOperationRegistry",
            ),
            ("reporting/operations.py", "from ..application.ports import ResourceReader"),
            ("reporting/ports.py", "from ..application.service_values import ResourceSnapshot"),
            ("reporting/ports.py", "from ..application.service_values import *"),
            ("reporting/operations.py", "import craftreport.application.registry as registry"),
            ("reporting/operations/helpers.py", "from ...application.ports import CommandContext"),
            ("reporting/operations.py", "from ..adapters.pack_reader import ConfiguredPackReader"),
            ("reporting/operations.py", "from ..runtime import values"),
            ("application/run.py", "from ..reporting import operations"),
            ("interfaces/http.py", "from ..reporting import operations"),
        )
        external = (
            "pydantic",
            "packaging",
            "sqlalchemy",
            "sqlite3",
            "fastapi",
            "mcp",
            "playwright",
        )
        for path, source in (
            *cases,
            *(
                (f"{owner}/values.py", f"import {name}")
                for owner in ("themes", "policies", "reporting")
                for name in external
            ),
        ):
            with self.subTest(path=path, source=source):
                fixture = f"src/craftreport/{path}"
                self.write(fixture, source + "\n")
                report = str(self.run_gate("imports", 1))
                self.assertIn(f"{fixture}:1: forbidden import:", report)
                (self.root / fixture).unlink()

    def test_public_pack_content_cannot_hide_python(self) -> None:
        for suffix in ("py", "pyi"):
            with self.subTest(suffix=suffix):
                path = f"examples/templates/public_report/execute.{suffix}"
                self.write(path, "import os\n")
                report = str(self.run_gate("imports", 1))
                self.assertIn(f"unapproved import layer: public-packs: {path}", report)
                (self.root / path).unlink()

    def test_report_resource_adapter_exact_storage_ports(self) -> None:
        self.write(
            "src/craftreport/adapters/report_resources.py",
            "from craftreport.adapters.storage.providers import DurableResources\n"
            "from .storage.results import DurableResults as Results\n",
        )
        self.run_gate("imports", cli=True)

    def test_report_resource_storage_allowance_stays_narrow(self) -> None:
        cases = (
            ("report_resources", "from .storage.providers import DurableHandoffs"),
            ("report_resources", "from .storage.results import other"),
            ("report_resources", "from .storage.providers import *"),
            ("report_resources", "import craftreport.adapters.storage.providers as storage"),
            ("report_resources", "from .storage import results"),
            ("report_resources", "from .storage.schema import commands"),
            ("report_resources", "from .storage.journal import DurableJournal"),
            ("other_adapter", "from .storage.providers import DurableResources"),
            ("other_adapter", "from .storage.results import DurableResults"),
        )
        for module, source in cases:
            with self.subTest(module=module, source=source):
                path = f"src/craftreport/adapters/{module}.py"
                self.write(path, source + "\n")
                report = str(self.run_gate("imports", 1))
                self.assertIn(f"{path}:1: forbidden import: adapters ->", report)
                (self.root / path).unlink()

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

    def test_gridcraft_allowed_dependencies(self) -> None:
        cases = {
            "app_values": "from craftreport.runtime.values import RunPins, TargetIdentity\n",
            "values": "from .app_values import BrowserTarget\n"
            "from craftreport.reporting.prepared import PreparedReport\n"
            "from craftreport.runtime.values import RunPins\n",
            "codecs": "from .values import Target\nfrom pydantic import Field\n"
            "from craftreport.adapters.validation import PydanticCodec, StrictWireModel\n"
            "from craftreport.adapters.validation import model_shape, construct\n"
            "from craftreport.adapters.snapshot_wire import encode_scalar, decode_scalar\n"
            "from craftreport.adapters.binding_codecs import parameter_digest, RunWire\n"
            "from craftreport.adapters.binding_codecs import BindingResultCodec\n"
            "from craftreport.adapters.report_codecs import prepared_identifier\n"
            "from craftreport.adapters.report_codecs import validation_scope_identifier\n"
            "from .app_values import BrowserTarget\n",
            "workbook": "from .values import MappingPlan\nimport xlsxwriter\n"
            "from .codecs import mapping_pins_match\n",
            "browser": "from .interactions import edit\nfrom playwright.async_api import Page\n",
            "interactions": "from .values import Target\nfrom playwright.async_api import Page\n",
            "artifacts": "from .browser import reopen\nfrom openpyxl import load_workbook\n",
            "providers": "from .facts import FactStore\n"
            "from craftreport.application.ports import GuardLease, ResourceReader\n"
            "from craftreport.application.service_values import ResourceSnapshot\n",
            "operations": "from .browser import apply\nfrom .codecs import request_codec\n"
            "from craftreport.application.registry import OperationBinding\n"
            "from craftreport.runtime.ports import AppOperationCaller\n"
            "from craftreport.policies.evaluate import evaluate\n",
            "capability": "from .operations import bindings\n"
            "from craftreport.application.capabilities import CapabilityInstance\n",
            "integration": "from craftreport.composition.app import open_application\n"
            "from craftreport.composition.settings import GuaranteeProviders\n"
            "from craftreport.adapters.storage.providers import providers\n",
        }
        for module, source in cases.items():
            self.write(
                f"packages/craftreport-gridcraft/src/craftreport_gridcraft/{module}.py", source
            )
        self.run_gate("imports", cli=True)

    def test_gridcraft_forbidden_dependencies(self) -> None:
        cases = (
            ("app_values", "from .codecs import decode"),
            ("app_values", "from .browser import Driver"),
            ("app_values", "from craftreport.adapters.binding_codecs import RunWire"),
            ("codecs", "from craftreport.adapters.binding_codecs import *"),
            ("codecs", "from craftreport.adapters.binding_codecs import BindingRequestCodec"),
            ("workbook", "from craftreport.adapters.report_codecs import prepared_identifier"),
            ("values", "from .browser import Driver"),
            ("values", "from craftreport_gridcraft import browser"),
            ("values", "from . import capability"),
            ("values", "from .codecs import decode"),
            ("values", "from craftreport.runtime.ports import RuntimeStore"),
            ("values", "from craftreport.reporting.operations import prepare"),
            ("values", "from craftreport.application.ports import CommandContext"),
            ("codecs", "from .browser import Driver"),
            ("codecs", "from craftreport.adapters import validation"),
            ("codecs", "from craftreport.adapters.validation import decode_envelope"),
            ("codecs", "from craftreport.adapters.snapshot_wire import finalize_snapshot"),
            (
                "operations",
                "from craftreport.application.registry import ImmutableOperationRegistry",
            ),
            ("operations", "import craftreport.application.registry as registry"),
            ("providers", "from craftreport.adapters.storage.journal import DurableJournal"),
            ("integration", "from craftreport.adapters.storage.schema import commands"),
            ("integration", "from craftreport.application.dispatch import Inspection"),
            ("helpers", "from playwright.async_api import Page"),
            ("values", "from craftreport.data.validation import validate"),
            ("workbook", "from .operations import apply"),
        )
        for module, source in (
            *cases,
            *(
                (name, f"import {sdk}")
                for name in ("values", "operations", "integration")
                for sdk in ("playwright", "xlsxwriter", "openpyxl", "pydantic", "PIL", "sqlite3")
            ),
            *(
                (name, "from scripts.browser_verification import browser")
                for name in ("browser", "interactions", "integration")
            ),
            ("browser", "import xlsxwriter"),
            ("workbook", "import openpyxl"),
            ("artifacts", "import playwright"),
        ):
            with self.subTest(module=module, source=source):
                fixture = f"packages/craftreport-gridcraft/src/craftreport_gridcraft/{module}.py"
                self.write(fixture, source + "\n")
                self.assertIn(
                    f"{fixture}:1: forbidden import: gridcraft ->", str(self.run_gate("imports", 1))
                )
                (self.root / fixture).unlink()

    def test_gridcraft_package_role_does_not_bypass_other_package_ownership(self) -> None:
        self.write(
            "breadth.toml",
            self.ledger + '\n[capability.plugin_a]\nowner = ["packages/plugin-a"]\n',
        )
        self.write("packages/plugin-a/src/craftreport_gridcraft/values.py", "x = 1\n")
        fixture = "packages/craftreport-gridcraft/src/craftreport_gridcraft/workbook.py"
        self.write(fixture, "from .values import x\n")
        self.assertIn("gridcraft -> craftreport_gridcraft.values", str(self.run_gate("imports", 1)))

    def test_core_cannot_import_gridcraft_before_package_exists(self) -> None:
        for owner in ("contracts", "data", "reporting", "themes", "policies", "application"):
            fixture = f"src/craftreport/{owner}/values.py"
            self.write(fixture, "from craftreport_gridcraft.values import Target\n")
            self.assertIn(f"{fixture}:1: forbidden import:", str(self.run_gate("imports", 1)))
            (self.root / fixture).unlink()

    def test_only_exact_gridcraft_recipes_are_scanned_and_admitted(self) -> None:
        self.write("packages/craftreport-gridcraft/src/craftreport_gridcraft/integration.py", "")
        for name in ("run_live_gridcraft_report", "gridcraft_report_host"):
            fixture = f"scripts/examples/{name}.py"
            self.write(fixture, "from craftreport_gridcraft.integration import host\n")
            self.run_gate("imports")
            self.write(fixture, "def invalid(:\n")
            self.assertIn(fixture, str(self.run_gate("imports", 1)))
            (self.root / fixture).unlink()
        self.write("scripts/examples/unrelated.py", "def invalid(:\n")
        self.run_gate("imports")
