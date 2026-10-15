"""Pure immutable runtime/profile values and reviewed pixel comparison."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from PIL import Image, ImageChops
from pydantic import Field

from .contracts import ActionReceipt, CellCheck, Sha256, TargetIdentity, Value

GRAPHICS = ("--use-angle=swiftshader", "--enable-unsafe-swiftshader")


class RuntimeProfile(Value):
    browser_version: str
    browser_revision: str = "1248"
    executable: str
    os: str
    headed: bool
    visible: bool
    window_handle: int | None
    viewport: tuple[int, int] = (1600, 1100)
    device_scale: int = 1
    locale: str = "en-US"
    graphics_arguments: tuple[str, ...] = GRAPHICS
    graphics_renderer: str


class RenderProfile(Value):
    browser_version: str
    browser_revision: str
    os: str
    headed: bool
    viewport: tuple[int, int]
    device_scale: int
    locale: str
    graphics_arguments: tuple[str, ...]
    graphics_renderer: str

    @classmethod
    def observed(cls, runtime: RuntimeProfile) -> RenderProfile:
        return cls.model_validate(runtime.model_dump(include=set(cls.model_fields)))


class Crop(Value):
    file: str
    sha256: Sha256
    box: tuple[int, int, int, int]
    masks: tuple[tuple[int, int, int, int], ...] = ()
    channel_delta: int = Field(ge=0, le=255)
    changed_fraction: float = Field(ge=0, le=0.01)


class VisualProfile(Value):
    schema_version: Literal[1]
    profile_id: str
    build_sha256: Sha256
    fixture_sha256: Sha256
    runtime: RenderProfile
    review_sha256: Sha256
    crops: dict[str, Crop]
    root: Path = Path(".")

    @classmethod
    def read(cls, path: Path) -> VisualProfile:
        profile = cls.model_validate_json(path.read_text(encoding="utf-8")).model_copy(
            update={"root": path.parent}
        )
        required = {
            "chart-before",
            "chart-after",
            "middle-before",
            "middle-after",
            "range-before",
            "range-after",
            "bold",
            "number",
            "dialog",
            "title",
            "legend",
            "series",
            "background",
            "home",
            "home-inactive",
            "expanded-controls",
        }
        if set(profile.crops) != required:
            raise ValueError("incomplete-visual-profile")
        if (
            hashlib.sha256((path.parent / "review.json").read_bytes()).hexdigest()
            != profile.review_sha256
        ):
            raise ValueError("baseline-review-hash-mismatch")
        return profile

    def require_runtime(self, build: str, runtime: RuntimeProfile) -> None:
        if build != self.build_sha256 or RenderProfile.observed(runtime) != self.runtime:
            raise ValueError("visual-profile-mismatch")


class VisualCapture(Value):
    check: str
    crop_name: str
    screenshot: str
    cropped: str


class ChartObservation(Value):
    target: TargetIdentity
    phase: Literal["before", "after"]
    profile_id: str
    category: str
    category_nonce: str
    captures: tuple[VisualCapture, ...]
    cells_before: tuple[CellCheck, ...]
    cells: tuple[CellCheck, ...]
    copy_receipt: ActionReceipt


def compare_crop(observed: Path, crop: Crop, root: Path) -> bool:
    """Compare an already cropped candidate; baseline bytes are immutable inputs."""
    reference = root / crop.file
    if hashlib.sha256(reference.read_bytes()).hexdigest() != crop.sha256:
        raise ValueError("baseline-hash-mismatch")
    with Image.open(reference) as baseline, Image.open(observed) as candidate:
        if candidate.size != baseline.size:
            return False
        difference = ImageChops.difference(candidate.convert("RGB"), baseline.convert("RGB"))
        for mask in crop.masks:
            difference.paste((0, 0, 0), mask)
        red, green, blue = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
        changed = sum(maximum.histogram()[crop.channel_delta + 1 :])
        return changed / (baseline.width * baseline.height) <= crop.changed_fraction
