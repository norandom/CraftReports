"""Immutable runtime pins, independent of report and application implementations."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable, require_text
from craftreport.data.requirements import InputRequirements
from craftreport.data.values import Scalar, SnapshotRef


def counter(value: int, *, absent: bool = False) -> None:
    if type(value) is not int or not (0 if absent else 1) <= value < 2**63:
        raise ValueError("Invalid runtime counter")


@dataclass(frozen=True, slots=True)
class TargetIdentity:
    adapter_id: str
    mode: Literal["native", "browser", "headless"]
    session_id: str
    document_id: str

    def __post_init__(self) -> None:
        for value in (self.adapter_id, self.session_id, self.document_id):
            if type(value) is not str:
                raise ValueError("Target identities require text")
            require_text(value, "target identity")
        if self.mode not in ("native", "browser", "headless"):
            raise ValueError("Unsupported target mode")


def validate_inputs(value: "BindingSpec | PreparedRunInputs | RunPins") -> None:
    require_immutable(value)
    if any(
        type(pin) is not VersionPin
        for pin in (value.definition, value.template, value.theme, value.pack)
    ):
        raise ValueError("Exact version pins required")
    for digest in (value.parameter_digest, value.validation_scope):
        VersionPin("digest", "1", digest)
    if type(value.resolved_parameters) is not tuple:
        raise ValueError("Immutable parameters required")
    names: set[str] = set()
    for pair in value.resolved_parameters:
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or type(pair[1]) not in (str, bool, int, Decimal, date, datetime, type(None))
        ):
            raise ValueError("Invalid parameter")
        require_text(pair[0], "parameter name")
        if pair[0] in names:
            raise ValueError("Duplicate parameter")
        names.add(pair[0])


@dataclass(frozen=True, slots=True)
class BindingSpec:
    binding_id: str
    feed_id: str
    requirements: InputRequirements
    requirements_digest: str
    definition: VersionPin
    template: VersionPin
    theme: VersionPin
    pack: VersionPin
    resolved_parameters: tuple[tuple[str, Scalar], ...]
    parameter_digest: str
    validation_scope: str
    target: TargetIdentity

    def __post_init__(self) -> None:
        validate_inputs(self)
        for identity in (self.binding_id, self.feed_id):
            if type(identity) is not str:
                raise ValueError("Binding identities require text")
            require_text(identity, "binding identity")
        VersionPin("requirements", "1", self.requirements_digest)
        if (
            type(self.requirements) is not InputRequirements
            or type(self.target) is not TargetIdentity
        ):
            raise ValueError("Invalid binding requirements or target")


@dataclass(frozen=True, slots=True)
class PreparedRunInputs:
    snapshot: SnapshotRef
    definition: VersionPin
    template: VersionPin
    theme: VersionPin
    pack: VersionPin
    resolved_parameters: tuple[tuple[str, Scalar], ...]
    parameter_digest: str
    validation_scope: str
    prepared_operation_id: str
    prepared_result_ref: str
    prepared_digest: str

    def __post_init__(self) -> None:
        validate_prepared(self)


def validate_prepared(value: "PreparedRunInputs | RunPins") -> None:
    validate_inputs(value)
    if type(value.snapshot) is not SnapshotRef:
        raise ValueError("Exact snapshot reference required")
    for identity in (value.prepared_operation_id, value.prepared_result_ref):
        if type(identity) is not str:
            raise ValueError("Prepared identities require text")
        require_text(identity, "prepared identity")
    VersionPin("prepared", "1", value.prepared_digest)


@dataclass(frozen=True, slots=True)
class RunPins:
    run_id: str
    binding_id: str
    binding_generation: int
    snapshot: SnapshotRef
    definition: VersionPin
    template: VersionPin
    theme: VersionPin
    pack: VersionPin
    resolved_parameters: tuple[tuple[str, Scalar], ...]
    parameter_digest: str
    validation_scope: str
    prepared_operation_id: str
    prepared_result_ref: str
    prepared_digest: str
    target: TargetIdentity

    def __post_init__(self) -> None:
        validate_prepared(self)
        counter(self.binding_generation)
        for identity in (self.run_id, self.binding_id):
            if type(identity) is not str:
                raise ValueError("Run identities require text")
            require_text(identity, "run identity")
        if type(self.target) is not TargetIdentity:
            raise ValueError("Exact target required")


@dataclass(frozen=True, slots=True)
class BindingState:
    spec: BindingSpec
    generation: int
    revision: int
    intent: Literal["stopped"] = "stopped"
    selected_run_id: str | None = None

    def __post_init__(self) -> None:
        require_immutable(self)
        counter(self.generation)
        counter(self.revision)
        if type(self.spec) is not BindingSpec or self.intent != "stopped":
            raise ValueError("Invalid binding state")
        if self.selected_run_id is not None:
            require_text(self.selected_run_id, "selected run")


@dataclass(frozen=True, slots=True)
class BindRequest:
    spec: BindingSpec
    expected_generation: int

    def __post_init__(self) -> None:
        counter(self.expected_generation, absent=True)
        if type(self.spec) is not BindingSpec:
            raise ValueError("Exact binding specification required")


@dataclass(frozen=True, slots=True)
class InspectRequest:
    kind: Literal["binding", "run"]
    identity: str

    def __post_init__(self) -> None:
        if self.kind not in ("binding", "run") or type(self.identity) is not str:
            raise ValueError("Invalid inspection identity")
        require_text(self.identity, "inspection identity")


@dataclass(frozen=True, slots=True)
class PreparationIssue:
    code: Literal["incomplete_binding", "preparation_mismatch", "preparation_unavailable"]
    locations: tuple[tuple[str | int, ...], ...] = ()

    def __post_init__(self) -> None:
        require_immutable(self)
        if self.code not in (
            "incomplete_binding",
            "preparation_mismatch",
            "preparation_unavailable",
        ):
            raise ValueError("Invalid preparation issue")
        if type(self.locations) is not tuple or any(
            type(location) is not tuple or any(type(part) not in (str, int) for part in location)
            for location in self.locations
        ):
            raise ValueError("Invalid preparation locations")
