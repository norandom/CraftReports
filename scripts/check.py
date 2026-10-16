"""Whole-scope engineering checks and the separate conformance entry point."""

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


def fast_steps(root: Path) -> list[tuple[str, list[str]]]:
    scope = ["src", "scripts", "tests"]
    if (root / "packages").is_dir():
        scope.append("packages")
    python = sys.executable
    test_scope = ["tests", "packages"] if "packages" in scope else ["tests"]
    return [
        ("Ruff lint", [python, "-m", "ruff", "check", "--no-respect-gitignore", *scope]),
        (
            "Ruff format",
            [python, "-m", "ruff", "format", "--check", "--no-respect-gitignore", *scope],
        ),
        ("Pyright strict", [python, "-m", "pyright", "--project", "pyproject.toml", *scope]),
        ("Size and branching budgets", [python, "scripts/check_quality.py"]),
        ("Breadth and retirement aging", [python, "scripts/check_breadth.py"]),
        ("Import boundaries", [python, "scripts/check_imports.py"]),
        (
            "Focused tests",
            [
                python,
                "-m",
                "pytest",
                "-q",
                "-n",
                "3",
                "--dist",
                "loadfile",
                "-m",
                "not integration",
                *test_scope,
            ],
        ),
    ]


def run_steps(root: Path, steps: list[tuple[str, list[str]]]) -> int:
    for name, command in steps:
        print(f"== {name} ==", flush=True)
        try:
            result = subprocess.run(command, cwd=root, check=False)
        except OSError as error:
            print(f"{name} unavailable: {error}", file=sys.stderr)
            return 1
        if result.returncode:
            print(f"{name} failed (exit {result.returncode}).", file=sys.stderr)
            return 1
    return 0


def integration_steps(root: Path, directory: Path) -> list[tuple[str, list[str]]]:
    return [
        (
            "Kernel contracts, installed activation and synthetic client journeys",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(root / "tests/kernel"),
                "--kernel-run-dir",
                str(directory),
                "--junitxml",
                str(directory / "junit.xml"),
            ],
        ),
        (
            "Fresh installed catalog verification of the completed packet",
            [sys.executable, str(root / "tests/kernel/catalog_proof.py"), str(directory)],
        ),
        (
            "Installed durable snapshot publication and restart",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-m",
                "integration",
                str(root / "tests/snapshot_runtime/test_installed.py"),
                "--junitxml",
                str(directory / "snapshot-junit.xml"),
            ],
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run CraftReport verification.")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--fast", action="store_true", help="Run engineering and focused tests")
    modes.add_argument("--integration", action="store_true", help="Run installed-wheel conformance")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.fast:
        return run_steps(root, fast_steps(root))
    run_id = datetime.now(UTC).strftime("kernel-%Y%m%dT%H%M%S-") + uuid4().hex[:8]
    directory = root / "artifacts" / run_id
    directory.mkdir(parents=True)
    print(f"Evidence: {directory}", flush=True)
    return run_steps(root, integration_steps(root, directory))


if __name__ == "__main__":
    raise SystemExit(main())
