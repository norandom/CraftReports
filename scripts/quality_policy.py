"""Typed policy, ownership and narrow waiver validation for quality measurement."""

import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import cast

RULES = {"function-lloc", "module-lloc", "capability-lloc", "C901"}


def table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected a configuration table")
    return cast(dict[str, object], value)


def strings(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("expected a string list")
    items = cast(list[object], value)
    if not all(isinstance(item, str) and item for item in items):
        raise ValueError("expected nonempty strings")
    return cast(list[str], items)


def read_config(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


def exact_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(character in value for character in "*?[]\\:")
        or ".." in path.parts
        or value == "."
    ):
        raise ValueError(f"not an exact repository path: {value}")
    return path


@dataclass(frozen=True)
class Ownership:
    entries: tuple[tuple[str, PurePosixPath], ...]

    def resolve(self, path: str) -> str:
        relative = PurePosixPath(path)
        matches = [
            (len(prefix.parts), owner)
            for owner, prefix in self.entries
            if relative.is_relative_to(prefix)
        ]
        if not matches:
            raise ValueError(f"unknown ownership: {path}")
        specificity = max(size for size, _ in matches)
        owners = {owner for size, owner in matches if size == specificity}
        if len(owners) != 1:
            raise ValueError(f"ambiguous ownership: {path}: {sorted(owners)}")
        return owners.pop()


def load_ownership(root: Path) -> Ownership:
    capabilities = table(read_config(root / "breadth.toml")["capability"])
    entries = [
        (owner, exact_path(path))
        for owner, value in capabilities.items()
        for path in strings(table(value)["owner"])
    ]
    return Ownership(tuple(entries))


@dataclass(frozen=True)
class Waiver:
    id: str
    capability_id: str
    exact_path_or_rule: str


@dataclass(frozen=True)
class CapabilityLimit:
    capability_id: str
    rule: str
    value: int
    owner: str
    rationale: str
    approval_reference: str


@dataclass(frozen=True)
class Policy:
    approved: frozenset[str]
    limits: dict[str, int]
    versions: dict[str, str]
    excluded: tuple[PurePosixPath, ...]
    waivers: tuple[Waiver, ...]
    capability_limits: tuple[CapabilityLimit, ...] = ()

    def capability_limit(self, owner: str) -> int:
        return next(
            (entry.value for entry in self.capability_limits if entry.capability_id == owner),
            self.limits["capability-lloc"],
        )


def validate_limit_approval(
    fields: dict[str, object], config: dict[str, object], root: Path
) -> str:
    reference = ".kiro/specs/craftreport-browser-verification/budget-amendment.md"
    scope = table(table(config.get("scope_approval"))["browser-verification"])
    if (
        fields.get("approved") is not True
        or scope.get("approved") is not True
        or scope.get("capability_id") != "browser-verification"
        or scope.get("budget_amendment_reference") != reference
        or fields.get("approval_reference") != reference
    ):
        raise ValueError("capability limit requires exact approved owner-decision reference/scope")
    path = root / exact_path(reference)
    if not path.is_file() or path.resolve() != path.absolute():
        raise ValueError("capability limit approval reference must be an existing repository file")
    return reference


def validate_capability_limit(
    entry: object,
    config: dict[str, object],
    root: Path,
    ownership: Ownership,
    approved: frozenset[str],
) -> CapabilityLimit:
    fields = table(entry)
    expected = {
        "capability_id",
        "rule",
        "value",
        "approved",
        "owner",
        "rationale",
        "approval_reference",
    }
    if set(fields) != expected:
        raise ValueError("capability limit requires exact typed fields")
    owner, rule, value = fields.get("capability_id"), fields.get("rule"), fields.get("value")
    if not isinstance(owner, str) or owner != "browser-verification" or owner not in approved:
        raise ValueError("capability limit has unsupported or unapproved capability")
    if owner not in {item[0] for item in ownership.entries}:
        raise ValueError("capability limit has unknown ownership")
    if not isinstance(rule, str) or rule != "capability-lloc":
        raise ValueError("capability limit has unsupported rule")
    if type(value) is not int or value != 2800:
        raise ValueError("capability limit requires approved integer value 2800")
    metadata: dict[str, str] = {}
    for key in ("owner", "rationale"):
        item = fields.get(key)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"capability limit requires nonempty {key}")
        metadata[key] = item
    reference = validate_limit_approval(fields, config, root)
    return CapabilityLimit(owner, rule, value, metadata["owner"], metadata["rationale"], reference)


def load_capability_limits(
    config: dict[str, object], root: Path, ownership: Ownership, approved: frozenset[str]
) -> tuple[CapabilityLimit, ...]:
    entries = table(config.get("capability_limits", {})).get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("capability limit entries must be a list")
    result: list[CapabilityLimit] = []
    for entry in cast(list[object], entries):
        limit = validate_capability_limit(entry, config, root, ownership, approved)
        if any(previous.capability_id == limit.capability_id for previous in result):
            raise ValueError("duplicate capability limit")
        result.append(limit)
    return tuple(result)


def limits_from(config: dict[str, object]) -> dict[str, int]:
    limits = table(config["limits"])
    keys = {
        "function-lloc": "max_function_lloc",
        "module-lloc": "max_module_lloc",
        "capability-lloc": "max_capability_lloc",
        "C901": "max_function_cyclomatic_complexity",
    }
    result: dict[str, int] = {}
    for rule, key in keys.items():
        value = limits[key]
        if type(value) is not int or value <= 0:
            raise ValueError(f"invalid positive limit: {key}")
        result[rule] = value
    return result


def waiver_fields(value: object) -> dict[str, str]:
    fields = table(value)
    required = (
        "id",
        "capability_id",
        "exact_path_or_rule",
        "owner",
        "reason",
        "approval_reference",
        "expires_at",
    )
    result: dict[str, str] = {}
    for key in required:
        item = fields.get(key)
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"waiver requires nonempty {key}")
        result[key] = item
    return result


def validate_waiver(
    fields: dict[str, str], root: Path, ownership: Ownership, approved: frozenset[str]
) -> Waiver:
    scope, owner = fields["exact_path_or_rule"], fields["capability_id"]
    try:
        expires = date.fromisoformat(fields["expires_at"])
    except ValueError as error:
        raise ValueError("waiver requires ISO expiry date") from error
    if expires < datetime.now(UTC).date():
        raise ValueError(f"expired waiver: {fields['id']}")
    if owner not in approved or owner not in {entry[0] for entry in ownership.entries}:
        raise ValueError(f"waiver has unapproved capability: {owner}")
    if scope not in RULES:
        path = exact_path(scope)
        if (
            path.suffix not in {".py", ".pyi"}
            or not (root / scope).is_file()
            or ownership.resolve(scope) != owner
        ):
            raise ValueError(f"waiver must select an exact owned source file or rule: {scope}")
    return Waiver(fields["id"], owner, scope)


def load_waivers(
    value: object, root: Path, ownership: Ownership, approved: frozenset[str]
) -> tuple[Waiver, ...]:
    if not isinstance(value, list):
        raise ValueError("waiver entries must be a list")
    result: list[Waiver] = []
    for entry in cast(list[object], value):
        try:
            waiver = validate_waiver(waiver_fields(entry), root, ownership, approved)
        except ValueError as error:
            raise ValueError(f"invalid waiver: {error}") from error
        if waiver.id in {previous.id for previous in result}:
            raise ValueError(f"duplicate waiver id: {waiver.id}")
        result.append(waiver)
    return tuple(result)


def load_policy(root: Path, ownership: Ownership) -> Policy:
    config = read_config(root / "quality.toml")
    meta = table(config["meta"])
    if meta.get("numeric_limits_approved") is not True:
        raise ValueError("numeric limits are not approved")
    approved = frozenset(strings(meta["approved_capability_ids"]))
    measurement = table(config["measurement"])
    lloc, branching = table(measurement["lloc"]), table(measurement["branching"])
    versions: dict[str, str] = {}
    for tool, settings in (("radon", lloc), ("ruff", branching)):
        version = settings["version"]
        if not isinstance(version, str) or not version:
            raise ValueError(f"invalid tool version: {tool}")
        versions[tool] = version
    excluded = tuple(exact_path(path) for path in strings(lloc.get("excluded_paths", [])))
    waivers = load_waivers(table(config["waivers"])["entries"], root, ownership, approved)
    capability_limits = load_capability_limits(config, root, ownership, approved)
    return Policy(approved, limits_from(config), versions, excluded, waivers, capability_limits)
