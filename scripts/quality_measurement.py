"""Exact source extraction and pinned external tool measurement boundaries."""

import ast
import importlib
import importlib.metadata
import io
import json
import subprocess
import sys
import textwrap
import tokenize
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from quality_policy import Ownership, Policy, table


class RawMetrics(Protocol):
    @property
    def lloc(self) -> int: ...


def logical_lines(source: str) -> int:
    # Radon has no type metadata; isolate its public raw API behind this narrow contract.
    analyze = cast(Callable[[str], RawMetrics], importlib.import_module("radon.raw").analyze)
    value = analyze(source).lloc
    if type(value) is not int or value < 0:
        raise ValueError("Radon returned invalid LLOC")
    return value


@dataclass(frozen=True)
class FunctionSize:
    path: str
    name: str
    line: int
    lloc: int
    test: bool


@dataclass(frozen=True)
class ModuleSize:
    path: str
    owner: str
    lloc: int
    test: bool


@dataclass(frozen=True)
class Violation:
    rule: str
    owner: str
    path: str
    message: str


def decorator_start(
    node: ast.FunctionDef | ast.AsyncFunctionDef, tokens: list[tokenize.TokenInfo]
) -> int:
    if not node.decorator_list:
        return node.lineno
    first_expression = node.decorator_list[0].lineno
    starts = [
        token.start[0]
        for token in tokens
        if token.type == tokenize.OP
        and token.string == "@"
        and token.start[1] == node.col_offset
        and token.start[0] <= first_expression
    ]
    if not starts:
        raise ValueError(f"cannot extract first decorator at line {first_expression}")
    return max(starts)


def function_sizes(source: str, path: str, test: bool) -> list[FunctionSize]:
    tree = ast.parse(source, filename=path)
    lines = source.splitlines(keepends=True)
    tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    result: list[FunctionSize] = []

    def visit(node: ast.AST, parents: tuple[str, ...]) -> None:
        scope = parents
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = decorator_start(node, tokens)
            end = node.end_lineno
            if end is None or not 1 <= start <= end <= len(lines):
                raise ValueError(f"invalid extraction bounds: {path}:{node.lineno}")
            segment = textwrap.dedent("".join(lines[start - 1 : end]))
            parsed = ast.parse(segment, filename=path)
            if len(parsed.body) != 1 or not isinstance(parsed.body[0], type(node)):
                raise ValueError(f"invalid function extraction: {path}:{start}")
            scope = (*parents, node.name)
            result.append(FunctionSize(path, ".".join(scope), start, logical_lines(segment), test))
        elif isinstance(node, ast.ClassDef):
            scope = (*parents, node.name)
        for child in ast.iter_child_nodes(node):
            visit(child, scope)

    visit(tree, ())
    return result


def source_files(root: Path, ownership: Ownership, policy: Policy) -> list[Path]:
    roots = {PurePosixPath(name) for name in ("src", "scripts", "tests", "packages")}
    roots.update(path for _, path in ownership.entries)
    files: set[Path] = set()
    for relative in sorted(roots):
        base = root / relative
        candidates = base.rglob("*") if base.is_dir() else [base]
        for path in candidates:
            local = PurePosixPath(path.relative_to(root).as_posix())
            if any(local.is_relative_to(excluded) for excluded in policy.excluded):
                continue
            if path.is_symlink() or path.is_junction():
                raise ValueError(f"source path aliases are not supported: {local}")
            if path.suffix not in {".py", ".pyi"} or not path.is_file():
                continue
            if path.resolve() != path.absolute():
                raise ValueError(f"source path aliases are not supported: {local}")
            files.add(path)
    return sorted(files)


def is_test_file(relative: str, owner: str, ownership: Ownership) -> bool:
    parts = PurePosixPath(relative).parts
    if parts[0] == "tests":
        return True
    if len(parts) >= 4 and parts[0] == "packages" and parts[2] == "tests":
        return (owner, PurePosixPath(*parts[:2])) in ownership.entries
    return False


def measure_file(
    root: Path, path: Path, ownership: Ownership, policy: Policy
) -> tuple[ModuleSize, list[FunctionSize]]:
    relative = path.relative_to(root).as_posix()
    owner = ownership.resolve(relative)
    if owner not in policy.approved:
        raise ValueError(f"unapproved budget: {owner}: {relative}")
    test = is_test_file(relative, owner, ownership)
    try:
        with tokenize.open(path) as stream:
            source = stream.read()
        functions = function_sizes(source, relative, test)
        size = logical_lines(source)
    except (SyntaxError, ValueError, UnicodeError, tokenize.TokenError) as error:
        raise ValueError(f"extraction failed: {relative}: {error}") from error
    return ModuleSize(relative, owner, size, test), functions


def verify_versions(policy: Policy) -> dict[str, str]:
    versions = {tool: importlib.metadata.version(tool) for tool in policy.versions}
    if versions != policy.versions:
        raise ValueError(f"tool version mismatch: expected {policy.versions}, installed {versions}")
    return versions


def branching(
    root: Path, files: list[Path], ownership: Ownership, policy: Policy
) -> list[Violation]:
    violations: list[Violation] = []
    # Bound command length on Windows; every enumerated file is still checked exactly once.
    for start in range(0, len(files), 40):
        command = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--select",
            "C901",
            "--ignore-noqa",
            "--no-respect-gitignore",
            "--output-format",
            "json",
            "--config",
            f"lint.mccabe.max-complexity={policy.limits['C901']}",
            *[str(path) for path in files[start : start + 40]],
        ]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            raise ValueError(f"Ruff check unavailable: {result.stderr}")
        rows: object = json.loads(result.stdout)
        if not isinstance(rows, list):
            raise ValueError("invalid Ruff result")
        for row in cast(list[object], rows):
            item = table(row)
            filename, message = item.get("filename"), item.get("message")
            if item.get("code") != "C901" or not isinstance(filename, str):
                raise ValueError(f"invalid Ruff diagnostic: {item}")
            relative = Path(filename).relative_to(root).as_posix()
            violations.append(
                Violation("C901", ownership.resolve(relative), relative, str(message))
            )
        if result.returncode == 1 and not rows:
            raise ValueError("Ruff failed without diagnostics")
    return violations
