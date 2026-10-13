"""Whole-scope approved engineering budgets."""

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from quality_measurement import (
    FunctionSize,
    ModuleSize,
    Violation,
    branching,
    measure_file,
    source_files,
    verify_versions,
)
from quality_policy import Policy, load_ownership, load_policy


@dataclass
class Report:
    versions: dict[str, str] = field(default_factory=dict[str, str])
    excluded_paths: list[str] = field(default_factory=list[str])
    modules: list[ModuleSize] = field(default_factory=list[ModuleSize])
    functions: list[FunctionSize] = field(default_factory=list[FunctionSize])
    production_capabilities: dict[str, int] = field(default_factory=dict[str, int])
    test_capabilities: dict[str, int] = field(default_factory=dict[str, int])
    violations: list[Violation] = field(default_factory=list[Violation])
    waived: list[dict[str, object]] = field(default_factory=list[dict[str, object]])
    errors: list[str] = field(default_factory=list[str])


def size_violations(report: Report, policy: Policy) -> list[Violation]:
    result: list[Violation] = []
    owners = {module.path: module.owner for module in report.modules}
    for function in report.functions:
        if not function.test and function.lloc > policy.limits["function-lloc"]:
            result.append(
                Violation(
                    "function-lloc",
                    owners[function.path],
                    function.path,
                    f"{function.name}:{function.line}: {function.lloc} > "
                    f"{policy.limits['function-lloc']}",
                )
            )
    for module in report.modules:
        totals = report.test_capabilities if module.test else report.production_capabilities
        totals[module.owner] = totals.get(module.owner, 0) + module.lloc
        if not module.test and module.lloc > policy.limits["module-lloc"]:
            result.append(
                Violation(
                    "module-lloc",
                    module.owner,
                    module.path,
                    f"{module.lloc} > {policy.limits['module-lloc']}",
                )
            )
    for owner, total in report.production_capabilities.items():
        if total > policy.limits["capability-lloc"]:
            result.append(
                Violation(
                    "capability-lloc", owner, "", f"{total} > {policy.limits['capability-lloc']}"
                )
            )
    return result


def apply_waivers(report: Report, violations: list[Violation], policy: Policy) -> None:
    for violation in violations:
        matching = [
            waiver
            for waiver in policy.waivers
            if waiver.capability_id == violation.owner
            and waiver.exact_path_or_rule in {violation.path, violation.rule}
        ]
        if matching:
            report.waived.append(
                {"violation": asdict(violation), "waiver_ids": [waiver.id for waiver in matching]}
            )
        else:
            report.violations.append(violation)


def check(root: Path) -> Report:
    report = Report()
    try:
        ownership = load_ownership(root)
        policy = load_policy(root, ownership)
        report.versions = verify_versions(policy)
        report.excluded_paths = [path.as_posix() for path in policy.excluded]
        files = source_files(root, ownership, policy)
        for path in files:
            try:
                module, functions = measure_file(root, path, ownership, policy)
                report.modules.append(module)
                report.functions.extend(functions)
            except (ValueError, OSError) as error:
                report.errors.append(str(error))
        violations = size_violations(report, policy)
        if not report.errors:
            violations.extend(branching(root, files, ownership, policy))
        apply_waivers(report, violations, policy)
    except (ValueError, OSError, KeyError) as error:
        report.errors.append(str(error))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    report = check(Path(args.root).resolve())
    print(json.dumps(asdict(report), indent=2))
    return int(bool(report.errors or report.violations))


if __name__ == "__main__":
    raise SystemExit(main())
