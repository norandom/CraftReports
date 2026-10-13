"""Validate actual breadth, approved ownership and lifecycle evidence."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from breadth_facts import lifecycle, spec_facts
from quality_policy import Ownership, exact_path, load_ownership, read_config, strings, table

CACHE_NAMES = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv"}


def scoped_paths(root: Path, meta: dict[str, object]) -> list[Path]:
    bases = [
        str(meta["source_root"]),
        str(meta["plugin_root"]),
        "scripts",
        "tests",
        "docs",
        "deploy",
        "examples",
    ]
    paths: set[Path] = set()
    for base in bases:
        directory = root / exact_path(base)
        for path in directory.rglob("*"):
            if set(path.relative_to(directory).parts) & CACHE_NAMES:
                continue
            if path.is_symlink() or path.is_junction() or path.resolve() != path.absolute():
                raise ValueError(f"source path aliases are not supported: {path}")
            paths.add(path)
    return sorted(paths)


def ownership_errors(
    root: Path,
    paths: list[Path],
    owners: Ownership,
    capabilities: dict[str, object],
    meta: dict[str, object],
) -> list[str]:
    errors: list[str] = []
    approved = strings(meta["approved_capability_owners"])
    for name in set(approved) - set(capabilities):
        errors.append(f"unknown approved capability owner: {name}")
    for path in paths:
        relative = path.relative_to(root).as_posix()
        try:
            owner = owners.resolve(relative)
            state = str(table(capabilities[owner]).get("status"))
            if state in {"parked", "removed"}:
                errors.append(f"{state} ownership: {owner}: {relative}")
            elif owner not in approved:
                errors.append(f"unapproved ownership: {owner}: {relative}")
        except ValueError as error:
            errors.append(str(error))
    return errors


def fronts(
    root: Path,
    specs: dict[str, object],
    capabilities: dict[str, object],
    phases: dict[str, str],
    errors: list[str],
) -> list[str]:
    result: list[str] = []
    now = datetime.now(UTC)
    for kind, entries in (("spec", specs), ("capability", capabilities)):
        for name, value in entries.items():
            identity = f"{kind}.{name}"
            entry = table(value)
            closed = False
            try:
                closed = lifecycle(root, identity, entry, now)
            except (OSError, ValueError, KeyError) as error:
                errors.append(f"{identity}: {error}")
            active_spec = (
                kind == "spec"
                and name in phases
                and str(entry.get("status")) in {"active", "review"}
            )
            retiring = (
                kind == "capability"
                and str(entry.get("status")) in {"review", "retiring"}
                and entry.get("closure_required") is True
                and not closed
            )
            if active_spec or retiring:
                result.append(identity)
    return sorted(result)


def counts(
    root: Path,
    meta: dict[str, object],
    capabilities: dict[str, object],
    phases: dict[str, str],
    generated: int,
    open_fronts: list[str],
) -> dict[str, int]:
    source = root / exact_path(str(meta["source_root"]))
    plugins = root / exact_path(str(meta["plugin_root"]))
    planned_plugins = {
        str(path)
        for value in capabilities.values()
        for path in strings(table(value)["owner"])
        if PurePosixPath(path).parent == PurePosixPath(str(meta["plugin_root"]))
    }
    return {
        "spec_count": len(phases),
        "generated_task_sets": generated,
        "actual_python_modules": sum(
            path.is_file() and path.suffix in {".py", ".pyi"} for path in source.rglob("*")
        ),
        "actual_plugin_packages": sum(path.is_dir() for path in plugins.iterdir())
        if plugins.exists()
        else 0,
        "planned_plugin_packages": len(planned_plugins),
        "planned_module_capabilities": sum(
            table(value).get("kind") == "module" for value in capabilities.values()
        ),
        "open_fronts": len(open_fronts),
    }


def check(root: Path) -> dict[str, object]:
    errors: list[str] = []
    report: dict[str, object] = {"errors": errors, "counts": {}, "phases": {}}
    try:
        ledger = read_config(root / "breadth.toml")
        meta, specs, capabilities = (table(ledger[key]) for key in ("meta", "spec", "capability"))
        if meta.get("schema_version") != 1 or meta.get("retirement_limit_days") != 14:
            raise ValueError("unsupported breadth schema or retirement limit (required: 14 days)")
        reference = root / exact_path(str(meta["scope_approval_reference"]))
        if not reference.is_file() or not reference.read_text(encoding="utf-8").strip():
            raise ValueError("missing scope approval reference")
        owners = load_ownership(root)
        for _, prefix in owners.entries:
            owners.resolve(prefix.as_posix())
        phases, generated = spec_facts(root, specs, meta, errors)
        errors.extend(ownership_errors(root, scoped_paths(root, meta), owners, capabilities, meta))
        open_fronts = fronts(root, specs, capabilities, phases, errors)
        actual = counts(root, meta, capabilities, phases, generated, open_fronts)
        for key, value in actual.items():
            if type(meta.get(key)) is not int or meta[key] != value:
                errors.append(f"stale count: {key}: declared {meta.get(key)}, actual {value}")
        if sorted(strings(meta["open_front_ids"])) != open_fronts:
            errors.append(f"stale open_front_ids: actual {open_fronts}")
        report.update(counts=actual, phases=phases, open_front_ids=open_fronts)
    except (KeyError, OSError, ValueError) as error:
        errors.append(str(error))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = check(Path(args.root).resolve())
    print(json.dumps(report, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
