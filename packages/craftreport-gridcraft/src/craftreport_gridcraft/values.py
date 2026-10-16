"""App-owned immutable candidate values, without pending runtime substitutes."""

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import require_immutable, require_positive, require_text
from craftreport.data.values import SnapshotRef
from craftreport.policies.values import QualityEvaluation
from craftreport.reporting.prepared import PreparedReport
from craftreport.runtime.values import RunPins
from craftreport.themes.values import SemanticRole
from craftreport_gridcraft.app_values import BrowserTarget, matched

DECLARATION = json.dumps(
    {
        "release": "0.7.0",
        "archive": "ad10af2baf9c7ed4ccbd81e32b37698f5075cdf4f26b726fee7fc7938a3a8d27",
        "javascript": "cd4d0aa76dfb703870a6b5dbf63c88217221ebb7aac5c491f51c0e1b2d8fcbd9",
        "wasm": "d1f2cfa583aea14443f0f68ee55403c18296cae237d1cfa7a2fdc3d886d4eb74",
        "browser": "Chromium 156.0.8078.4; Windows headless SwiftShader; 1600x1100",
        "shape": [4, 3, 4, 1],
        "owned": "Report!A1:L40",
        "chart": "A18:H38",
        "numbers": [0, 9999],
        "category_serialized_utf8_bytes": 16,
        "literal_serialized_utf8_bytes": 32,
        "excluded_unicode_categories": ["Cc", "Cf", "Cs", "Zl", "Zp"],
        "summary_serialized_utf8_bytes": 1024,
        "theme": (
            "public/gridcraft-fixed-theme@1.0.0:"
            "f8c0a8b07dae4377cc31f62de1bf9d76e027a239a73535fa6762e4e57ed5d980"
        ),
        "table": (
            "report_table; category/Category/text/row_label; "
            "value/Value/int64/output; literal/Literal/text/note"
        ),
        "chart_source": (
            "report_line; series/Series/series_value/int64/nullable/output; "
            "Report!$G$5; Report!$F$6:$F$9; Report!$G$6:$G$9; gap=1"
        ),
    },
    sort_keys=True,
    separators=(",", ":"),
)


@dataclass(frozen=True, slots=True)
class Profile:
    pin: VersionPin
    operation_status: Literal["untested"] = "untested"

    def __post_init__(self) -> None:
        if type(self.pin) is not VersionPin or self.operation_status != "untested":
            raise ValueError("Profile support requires accepted real-effect evidence")


PROFILE = Profile(
    VersionPin("gridcraft/browser-fixed", "1.0.0", sha256(DECLARATION.encode()).hexdigest())
)


def profile_matches(target: BrowserTarget) -> bool:
    declaration: dict[str, object] = json.loads(DECLARATION)
    return target.profile_pin == PROFILE.pin and (
        target.archive_digest,
        target.javascript_digest,
        target.wasm_digest,
    ) == (declaration["archive"], declaration["javascript"], declaration["wasm"])


@dataclass(frozen=True, slots=True)
class OwnedLayout:
    target: BrowserTarget
    run: RunPins

    @property
    def profile(self) -> Profile:
        return Profile(self.target.profile_pin)

    @property
    def deployment_id(self) -> str:
        return self.target.deployment_id

    @property
    def context_id(self) -> str:
        return self.target.context_id

    @property
    def page_id(self) -> str:
        return self.target.page_id

    @property
    def navigation_generation(self) -> int:
        return self.target.navigation_generation

    @property
    def document_marker(self) -> str:
        return self.target.document_marker

    @property
    def definition(self) -> VersionPin:
        return self.run.definition

    @property
    def template(self) -> VersionPin:
        return self.run.template

    @property
    def theme(self) -> VersionPin:
        return self.run.theme

    @property
    def pack(self) -> VersionPin:
        return self.run.pack

    @property
    def snapshot(self) -> SnapshotRef:
        return self.run.snapshot

    @property
    def prepared_digest(self) -> str:
        return self.run.prepared_digest

    def __post_init__(self) -> None:
        require_immutable(self)
        matched(self.target, self.run)
        for value in (self.deployment_id, self.context_id, self.page_id, self.document_marker):
            require_text(value, "layout identity")
        require_positive(self.navigation_generation, "navigation generation")
        VersionPin("prepared", "1", self.prepared_digest)


@dataclass(frozen=True, slots=True)
class Cell:
    address: str
    value: str | int | None
    role: SemanticRole


@dataclass(frozen=True, slots=True)
class MappingPlan:
    prepared: PreparedReport
    quality: QualityEvaluation
    layout: OwnedLayout
    cells: tuple[Cell, ...]


@dataclass(frozen=True, slots=True)
class AppIssue:
    code: Literal["unsupported", "untested", "limit", "conflict", "unavailable"]
    location: tuple[str | int, ...]
    stage: Literal["admit", "bootstrap"] = "admit"
    effect: Literal["none"] = "none"

    def __post_init__(self) -> None:
        require_immutable(self)
        if (
            self.code not in ("unsupported", "untested", "limit", "conflict", "unavailable")
            or self.stage not in ("admit", "bootstrap")
            or self.effect != "none"
        ):
            raise ValueError("Invalid app issue")
        if type(self.location) is not tuple or any(
            type(part) not in (str, int) for part in self.location
        ):
            raise ValueError("Immutable typed issue location required")
