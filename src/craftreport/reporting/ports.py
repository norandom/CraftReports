"""Immutable selections and source-authorized configured pack reads."""

from dataclasses import dataclass
from typing import Literal, Protocol

from craftreport.contracts.identity import Principal
from craftreport.reporting.definitions import text
from craftreport.reporting.prepared import ResolvedPack


@dataclass(frozen=True, slots=True)
class PackSelection:
    namespace: str
    name: str
    version: str

    def __post_init__(self) -> None:
        for value in (self.namespace, self.name, self.version):
            text(value, ("selection",))

    @property
    def identity(self) -> str:
        return f"{self.namespace}/{self.name}"


@dataclass(frozen=True, slots=True)
class PackSummary:
    identity: str
    version: str
    attribution: str
    artifact_visibility_scope: str


@dataclass(frozen=True, slots=True)
class PackFailure:
    code: Literal["not_found"] = "not_found"
    location: tuple[Literal["selection"]] = ("selection",)


class PackReader(Protocol):
    def discover(self, principal: Principal) -> tuple[PackSummary, ...]: ...

    def read(
        self, selection: PackSelection, principal: Principal
    ) -> ResolvedPack | PackFailure: ...
