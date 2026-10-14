"""Read actual specification phases and verify lifecycle closure evidence."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quality_policy import exact_path, strings, table

STATES = {"active", "done", "parked", "retiring", "review", "removed"}
LINES = {"shared-reporting", "craft-app-integration", "quality-verification", "template-packs"}
PHASES = {
    "initialized",
    "requirements-generated",
    "design-generated",
    "tasks-generated",
    "implementation-in-progress",
    "implementation-complete",
}
GENERATED_STAGES = {
    "initialized": (),
    "requirements-generated": ("requirements",),
    "design-generated": ("requirements", "design"),
    "tasks-generated": ("requirements", "design", "tasks"),
    "implementation-in-progress": ("requirements", "design", "tasks"),
    "implementation-complete": ("requirements", "design", "tasks"),
}


def read_json(path: Path) -> dict[str, object]:
    try:
        return table(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path.as_posix()}: {error}") from error


def approved(spec: dict[str, object]) -> bool:
    approvals = table(spec["approvals"])
    return spec.get("ready_for_implementation") is True and all(
        table(approvals[phase]).get("generated") is True
        and table(approvals[phase]).get("approved") is True
        for phase in ("requirements", "design", "tasks")
    )


def validate_spec(spec: dict[str, object], name: str) -> tuple[str, bool]:
    phase = str(spec["phase"])
    if spec.get("feature_name") != name or phase not in PHASES:
        raise ValueError(f"inconsistent spec metadata: {name}: {phase}")
    approvals = table(spec["approvals"])
    for stage in ("requirements", "design", "tasks"):
        values = table(approvals[stage])
        if any(type(values.get(key)) is not bool for key in ("generated", "approved")):
            raise ValueError(f"invalid approval flags: {name}: {stage}")
        if values["approved"] and not values["generated"]:
            raise ValueError(f"approval without generated stage: {name}: {stage}")
    for stage in GENERATED_STAGES[phase]:
        if table(approvals[stage])["generated"] is not True:
            raise ValueError(f"inconsistent generated {stage}: {name}: {phase}")
    return phase, table(approvals["tasks"])["generated"] is True


def spec_facts(
    root: Path, ledger: dict[str, object], meta: dict[str, object], errors: list[str]
) -> tuple[dict[str, str], int]:
    phases: dict[str, str] = {}
    generated = 0
    scopes = strings(meta["approved_spec_scopes"])
    for path in sorted((root / ".kiro/specs").glob("*/spec.json")):
        name = path.parent.name
        try:
            spec = read_json(path)
            phase, has_tasks = validate_spec(spec, name)
            phases[name] = phase
            generated += int(has_tasks)
            if name not in ledger:
                errors.append(f"unregistered spec: {name}")
            else:
                source = table(ledger[name])["phase_source"]
                if source != path.relative_to(root).as_posix():
                    errors.append(f"wrong phase source: {name}: {source}")
            implementing = phase in {"implementation-in-progress", "implementation-complete"}
            if implementing and name not in scopes:
                errors.append(f"unapproved implementation scope: {name}")
            if (implementing or name in scopes) and not approved(spec):
                errors.append(f"not implementation-approved: {name}")
        except (KeyError, ValueError) as error:
            errors.append(f"{path.relative_to(root).as_posix()}: {error}")
    for name in set(ledger) - set(phases):
        errors.append(f"missing actual spec: {name}")
    for name in set(scopes) - set(phases):
        errors.append(f"unknown approved spec scope: {name}")
    return phases, generated


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"invalid status_since: {value}")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"invalid status_since: {value}") from error
    if result.tzinfo is None:
        if len(value) != 10:
            raise ValueError(f"invalid status_since (timezone required): {value}")
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def closure(root: Path, identity: str, entry: dict[str, object]) -> bool:
    """Evidence JSON pins entry_id, ordered close_targets and executed=true.

    closure_evidence is its repository path; required deletion targets must be absent.
    done entries may retain owned code with an empty target list and acceptance evidence.
    """
    executed = entry.get("closure_executed", False)
    if type(executed) is not bool:
        raise ValueError(f"invalid closure_executed: {identity}")
    if not executed and entry.get("status") not in {"done", "removed"}:
        return False
    reference = entry.get("closure_evidence")
    if not isinstance(reference, str) or not reference:
        raise ValueError(f"missing closure evidence: {identity}")
    try:
        evidence = read_json(root / exact_path(reference))
    except ValueError as error:
        raise ValueError(f"invalid closure evidence: {identity}: {error}") from error
    targets = strings(entry["close_targets"])
    if (
        evidence.get("entry_id") != identity
        or evidence.get("executed") is not True
        or strings(evidence.get("close_targets")) != targets
    ):
        raise ValueError(f"mismatched closure evidence: {identity}: {reference}")
    if entry.get("closure_required") is True:
        if not targets:
            raise ValueError(f"closure evidence has no targets: {identity}")
        for target in targets:
            if (root / exact_path(target)).exists():
                raise ValueError(f"closure target still exists: {identity}: {target}")
    return True


def lifecycle(root: Path, identity: str, entry: dict[str, object], now: datetime) -> bool:
    state = entry.get("status")
    if not isinstance(state, str) or state not in STATES:
        raise ValueError(f"unknown state: {identity}: {state}")
    line = entry.get("line")
    if not isinstance(line, str) or line not in LINES:
        raise ValueError(f"unknown line: {identity}: {entry.get('line')}")
    if type(entry.get("closure_required")) is not bool:
        raise ValueError(f"invalid closure_required: {identity}")
    for target in strings(entry["close_targets"]):
        exact_path(target)
    closed = closure(root, identity, entry)
    if state == "retiring":
        since = timestamp(entry.get("status_since"))
        if since > now:
            raise ValueError(f"future status_since: {identity}")
        if not entry.get("accountable_owner") or not strings(entry["close_targets"]):
            raise ValueError(f"retirement requires owner and targets: {identity}")
        if entry["closure_required"] and not closed and now - since > timedelta(days=14):
            raise ValueError(f"overdue retirement: {identity}: started {since.isoformat()}")
    return closed
