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
    "reporting",
    "themes",
    "policies",
}
ALLOWED = {
    "contracts": {"contracts"},
    "data": {"contracts", "data"},
    "reporting": {"contracts", "data", "themes", "policies", "reporting"},
    "themes": {"contracts", "themes"},
    "policies": {"contracts", "policies"},
    "runtime": {"contracts", "data", "runtime"},
    "snapshot-storage": {"contracts", "application", "data", "runtime", "snapshot-storage"},
    "application": {"contracts", "application"},
    "adapters": {
        "contracts",
        "application",
        "data",
        "runtime",
        "adapters",
        "reporting",
        "themes",
        "policies",
    },
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
EXACT_CONTRACT_IMPORTS = {
    ("data", "craftreport.data.ports"): {
        f"craftreport.application.service_values.{value}" for value in SNAPSHOT_READ_RESULTS
    },
    ("snapshot-storage", "craftreport.adapters.storage.serialization"): {
        "pydantic.TypeAdapter",
        "pydantic.ValidationError",
        "craftreport.adapters.canonical.canonical_bytes",
    },
}
REPORTING_INTEGRATION = {"craftreport.reporting.operations", "craftreport.reporting.ports"}
REPORTING_KERNEL_VALUES = {
    "registry": {"OperationBinding", "CommandBehavior", "QueryBehavior"},
    "ports": {"CommandContext", "ReadContext"},
    "service_values": SNAPSHOT_READ_RESULTS,
}
GRIDCRAFT_RECIPES = {
    "scripts/examples/run_live_gridcraft_report.py",
    "scripts/examples/gridcraft_report_host.py",
}
GRIDCRAFT_VALUES = {
    "craftreport.contracts",
    "craftreport.data.values",
    "craftreport.reporting.prepared",
    "craftreport.themes.values",
    "craftreport.policies.values",
    "craftreport.runtime.values",
}
GRIDCRAFT_MODULES = {
    "values": {"values"},
    "codecs": {"values", "codecs"},
    "workbook": {"values", "workbook"},
    "interactions": {"values", "interactions"},
    "browser": {"values", "workbook", "interactions", "browser"},
    "artifacts": {"values", "browser", "artifacts"},
    "facts": {"values", "codecs", "facts"},
    "providers": {"values", "facts", "providers"},
    "operations": {
        "values",
        "codecs",
        "workbook",
        "browser",
        "artifacts",
        "facts",
        "providers",
        "operations",
    },
    "capability": {"values", "codecs", "operations", "providers", "capability"},
    "craftreport_gridcraft": {"values", "capability"},
}
GRIDCRAFT_ORCHESTRATION = {"facts", "providers", "operations", "capability", "integration"}
GRIDCRAFT_KERNEL = {
    "registry": {"Codec", "OperationBinding", "CommandBehavior", "QueryBehavior", "BoundOperation"},
    "ports": {
        "Facade",
        "CommandContext",
        "ReadContext",
        "GuardLease",
        "ExecutionGuard",
        "GuardAcquisitionError",
        "EvidenceReader",
        "ResourceReader",
        "ResourceEffects",
        "CapabilityResolver",
        "AccessPolicy",
    },
    "service_values": SNAPSHOT_READ_RESULTS
    | {"ResourceSnapshot", "ResourceEffect", "GuardCurrent", "GuardLost"},
    "capabilities": {"CapabilityInstance", "CapabilityFactory"},
}
GRIDCRAFT_CODECS = {
    "craftreport.adapters.validation.PydanticCodec",
    "craftreport.adapters.validation.StrictWireModel",
    *(
        f"craftreport.adapters.snapshot_wire.{name}"
        for name in ("encode_scalar", "decode_scalar", "encode_parameter", "decode_parameter")
    ),
}
GRIDCRAFT_COMPOSITION = {
    "craftreport.composition.settings",
    "craftreport.composition.app.open_application",
    "craftreport.composition.snapshot_host",
    "craftreport.composition.reporting",
    "craftreport.adapters.storage.providers",
}


def beneath(target: str, prefixes: set[str]) -> bool:
    return any(target == prefix or target.startswith(f"{prefix}.") for prefix in prefixes)


def gridcraft_forbidden(target: str, module: str) -> bool:
    role = module.removeprefix("craftreport_gridcraft.")
    if role not in GRIDCRAFT_MODULES and role != "integration":
        return True
    if target.split(".")[0] == "craftreport_gridcraft":
        peers = set(GRIDCRAFT_MODULES) if role == "integration" else GRIDCRAFT_MODULES[role]
        return not beneath(target, {f"craftreport_gridcraft.{name}" for name in peers})
    if beneath(target, GRIDCRAFT_VALUES):
        return False
    if role in GRIDCRAFT_ORCHESTRATION and target in {
        f"craftreport.application.{name}.{value}"
        for name, values in GRIDCRAFT_KERNEL.items()
        for value in values
    }:
        return False
    if role in GRIDCRAFT_ORCHESTRATION and beneath(
        target,
        {
            "craftreport.runtime.ports",
            "craftreport.reporting.operations",
            "craftreport.policies.evaluate",
        },
    ):
        return False
    if role == "integration" and beneath(target, GRIDCRAFT_COMPOSITION):
        return False
    if role == "codecs" and (target in GRIDCRAFT_CODECS or beneath(target, {"pydantic"})):
        return False
    sdk = {
        "workbook": "xlsxwriter",
        "browser": "playwright",
        "interactions": "playwright",
        "artifacts": "openpyxl",
    }.get(role)
    return target.split(".")[0] not in (sys.stdlib_module_names - STORAGE) | (
        {sdk} if sdk else set[str]()
    )


def reporting_forbidden(target: str, module: str) -> bool | None:
    integration = module in REPORTING_INTEGRATION
    layer = target_layer(target)
    if layer == "application":
        return not integration or target not in {
            f"craftreport.application.{name}.{value}"
            for name, values in REPORTING_KERNEL_VALUES.items()
            for value in values
        }
    if layer == "data":
        allowed = {"values", "requirements"} | ({"ports"} if integration else set[str]())
        return not any(
            target == f"craftreport.data.{name}" or target.startswith(f"craftreport.data.{name}.")
            for name in allowed
        )
    if not integration and any(
        target == name or target.startswith(f"{name}.") for name in REPORTING_INTEGRATION
    ):
        return True
    return None


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
    if module.replace(".", "/") + ".py" in GRIDCRAFT_RECIPES:
        return False
    module_path = PurePosixPath(*target.split("."))
    if any(module_path.is_relative_to(prefix) for _, prefix in package_modules.entries):
        if package_modules.resolve(module_path.as_posix()) != owner:
            return True
    if owner == "gridcraft":
        return gridcraft_forbidden(target, module)
    if owner in LAYERS - {"composition"} and beneath(target, {"craftreport_gridcraft"}):
        return True
    return kernel_forbidden(owner, target, package_modules, module)


def kernel_forbidden(owner: str, target: str, package_modules: Ownership, module: str) -> bool:
    if owner != "browser-verification" and any(
        target == prefix or target.startswith(f"{prefix}.") for prefix in BROWSER_MODULES
    ):
        return True
    layer = target_layer(target)
    external = target.split(".")[0]
    if owner == "reporting" and (decision := reporting_forbidden(target, module)) is not None:
        return decision
    if target in EXACT_CONTRACT_IMPORTS.get((owner, module), set[str]()):
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
    if owner in {
        "contracts",
        "application",
        "data",
        "runtime",
        "snapshot-storage",
        "reporting",
        "themes",
        "policies",
    }:
        concrete = {"sqlalchemy", "sqlite3"} if owner == "snapshot-storage" else set[str]()
        return external not in (sys.stdlib_module_names - STORAGE) | concrete
    return False


def file_errors(root: Path, path: Path, owners: Ownership, package_modules: Ownership) -> list[str]:
    relative = path.relative_to(root).as_posix()
    owner = owners.resolve(relative)
    if (
        owner not in LAYERS | {"browser-verification"}
        and relative not in GRIDCRAFT_RECIPES
        and not relative.startswith("packages/")
    ):
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
    for suffix in ("*.py", "*.pyi"):
        paths.extend(sorted((root / "examples").rglob(suffix)))
    recipe = root / "scripts/examples/verify_gridcraft_browser.py"
    if recipe.is_file():
        paths.append(recipe)
    paths.extend(root / name for name in sorted(GRIDCRAFT_RECIPES) if (root / name).is_file())
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
