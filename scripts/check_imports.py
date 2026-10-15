"""Check whole-tree Python imports against the approved inward kernel layers."""

import argparse
import ast
import json
import sys
import tokenize
from pathlib import Path, PurePosixPath

from quality_policy import Ownership, load_ownership

LAYERS = {
    "contracts",
    "application",
    "adapters",
    "interfaces",
    "composition",
    "data",
    "runtime",
    "snapshot-storage",
}
ALLOWED = {
    "contracts": {"contracts"},
    "data": {"contracts", "data"},
    "runtime": {"contracts", "data", "runtime"},
    "snapshot-storage": {"contracts", "application", "data", "runtime", "snapshot-storage"},
    "application": {"contracts", "application"},
    "adapters": {"contracts", "application", "data", "runtime", "adapters"},
    "interfaces": {"contracts", "application", "interfaces"},
    "composition": LAYERS,
}
STORAGE = {"sqlite3", "dbm", "shelve"}
BROWSER_MODULES = {
    "browser_verification",
    "scripts.browser_verification",
    "examples.verify_gridcraft_browser",
    "scripts.examples.verify_gridcraft_browser",
    "playwright",
    "PIL",
}
RUNTIME_APPLICATION_MODULES = {
    "ports",
    "service_values",
    "journal_values",
    "capabilities",
    "registry",
    "outcomes",
}
SNAPSHOT_READ_RESULTS = {"Missing", "VersionConflict", "ServiceUnavailable"}


def module_name(path: Path, root: Path) -> str:
    parts = list(path.relative_to(root).with_suffix("").parts)
    if parts[0] == "packages":
        parts = parts[2:]
    if parts[0] == "src":
        parts.pop(0)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def import_targets(node: ast.Import | ast.ImportFrom, package: str) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = node.module or ""
    if node.level:
        parts = package.split(".")
        if node.level > len(parts):
            raise ValueError("relative import escapes package")
        base = ".".join(parts[: len(parts) - node.level + 1] + ([base] if base else []))
    return [base, *[f"{base}.{alias.name}" for alias in node.names if alias.name != "*"]]


def target_layer(target: str) -> str | None:
    parts = target.split(".")
    if parts[0] != "craftreport":
        return None
    if len(parts) == 1 or parts[1] in {"bootstrap", "__init__"}:
        return "composition"
    if parts[1:3] == ["adapters", "storage"]:
        return "snapshot-storage"
    return parts[1]


def forbidden(owner: str, target: str, package_modules: Ownership, module: str) -> bool:
    if owner != "browser-verification" and any(
        target == prefix or target.startswith(f"{prefix}.") for prefix in BROWSER_MODULES
    ):
        return True
    layer = target_layer(target)
    external = target.split(".")[0]
    module_path = PurePosixPath(*target.split("."))
    if any(module_path.is_relative_to(prefix) for _, prefix in package_modules.entries):
        return package_modules.resolve(module_path.as_posix()) != owner
    if (
        owner == "data"
        and module == "craftreport.data.ports"
        and target
        in {f"craftreport.application.service_values.{value}" for value in SNAPSHOT_READ_RESULTS}
    ):
        return False
    if owner in {"runtime", "snapshot-storage"} and layer == "application":
        modules = RUNTIME_APPLICATION_MODULES | (
            {"dispatch_ports"} if owner == "snapshot-storage" else set[str]()
        )
        return not any(
            target == f"craftreport.application.{name}"
            or target.startswith(f"craftreport.application.{name}.")
            for name in modules
        )
    if owner not in LAYERS:
        if layer is None:
            return False
        port = target == "craftreport.application.ports" or target.startswith(
            "craftreport.application.ports."
        )
        return layer != "contracts" and not port
    if layer is not None:
        return layer not in ALLOWED[owner]
    if owner in {"contracts", "application", "data", "runtime", "snapshot-storage"}:
        concrete = {"sqlalchemy", "sqlite3"} if owner == "snapshot-storage" else set[str]()
        return external not in (sys.stdlib_module_names - STORAGE) | concrete
    return False


def file_errors(root: Path, path: Path, owners: Ownership, package_modules: Ownership) -> list[str]:
    relative = path.relative_to(root).as_posix()
    owner = owners.resolve(relative)
    if owner not in LAYERS | {"browser-verification"} and not relative.startswith("packages/"):
        raise ValueError(f"unapproved import layer: {owner}: {relative}")
    module = module_name(path, root)
    package = module if path.stem == "__init__" else module.rpartition(".")[0]
    with tokenize.open(path) as stream:
        tree = ast.parse(stream.read(), filename=relative)
    errors: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        targets = import_targets(node, package)
        if isinstance(node, ast.ImportFrom) and len(targets) > 1:
            targets = targets[1:]
        for target in targets:
            if forbidden(owner, target, package_modules, module):
                errors.append(f"{relative}:{node.lineno}: forbidden import: {owner} -> {target}")
    return errors


def source_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in (root / "src", root / "packages"):
        for path in sorted(directory.rglob("*")):
            if path.suffix not in {".py", ".pyi"} or not path.is_file():
                continue
            parts = path.relative_to(root).parts
            if len(parts) > 3 and parts[0] == "packages" and parts[2] == "tests":
                continue
            paths.append(path)
    paths.extend(sorted((root / "scripts/browser_verification").rglob("*.py")))
    paths.extend(sorted((root / "scripts/browser_verification").rglob("*.pyi")))
    recipe = root / "scripts/examples/verify_gridcraft_browser.py"
    if recipe.is_file():
        paths.append(recipe)
    return paths


def module_ownership(root: Path, paths: list[Path], owners: Ownership) -> Ownership:
    """Preserve full Python module prefixes, including shared namespace portions."""
    entries = tuple(
        (
            owners.resolve(path.relative_to(root).as_posix()),
            PurePosixPath(*module_name(path, root).split(".")),
        )
        for path in paths
        if path.relative_to(root).parts[0] == "packages"
    )
    modules = Ownership(entries)
    for _, prefix in entries:
        try:
            modules.resolve(prefix.as_posix())
        except ValueError as error:
            module = ".".join(prefix.parts)
            raise ValueError(f"ambiguous Python module ownership: {module}: {error}") from error
    return modules


def check(root: Path) -> dict[str, object]:
    errors: list[str] = []
    checked = 0
    try:
        owners = load_ownership(root)
        paths = source_paths(root)
        package_modules = module_ownership(root, paths, owners)
        for path in paths:
            checked += 1
            try:
                if path.resolve() != path.absolute():
                    raise ValueError("source path aliases are not supported")
                errors.extend(file_errors(root, path, owners, package_modules))
            except (OSError, SyntaxError, ValueError) as error:
                errors.append(f"{path.relative_to(root).as_posix()}: {error}")
    except (KeyError, OSError, ValueError) as error:
        errors.append(str(error))
    return {"errors": errors, "checked_files": checked}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = check(Path(args.root).resolve())
    print(json.dumps(report, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
