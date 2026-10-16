"""Pinned Delta-ink regression, not OCR or universal Unicode fit certification."""

import io
from pathlib import Path
from typing import cast

from PIL import Image


def selected_column(pixels: bytes, column: str, *, merged: bool = False) -> bool:
    """Pinned candidate column edge only; exact row/value need subsequent clipboard checks."""
    left = dict(
        zip(
            "ABCDEFGHIJKLM",
            (28, 133, 238, 343, 447, 552, 657, 762, 867, 971, 1076, 1181, 1286),
            strict=True,
        )
    )[column]
    width = 51 if column == "M" else 105
    right = 866 if merged else left + width
    with Image.open(io.BytesIO(pixels)) as source:
        if source.size != (1600, 1100):
            return False
        picture = source.convert("RGB")
        for x in range(left - 2, left + 2):
            edge = cast(
                tuple[tuple[int, int, int], ...],
                picture.crop((x, 215, x + 1, 1040)).get_flattened_data(),
            )
            green = [
                y + 215
                for y, (r, g, b) in enumerate(edge)
                if g > 80 and g > r * 1.5 and g > b * 1.2
            ]
            if len(green) < 10:
                continue
            opposite = {
                yy
                for xx in range(right - 3, right + 2)
                for yy in green
                for r, g, b in [cast(tuple[int, int, int], picture.getpixel((xx, yy)))]
                if g > 80 and g > r * 1.5 and g > b * 1.2
            }
            if len(opposite) < 10:
                continue
            for y in green:
                top = cast(
                    tuple[tuple[int, int, int], ...],
                    picture.crop((left + 4, y, left + width - 10, y + 1)).get_flattened_data(),
                )
                if sum(g > 80 and g > r * 1.5 and g > b * 1.2 for r, g, b in top) >= width - 25:
                    return True
    return False


def label_ink(path: Path) -> dict[str, object]:
    with Image.open(path) as source:
        assert source.size == (1600, 1100)
        picture = source.convert("RGB")
        rows: list[int] = []
        for y in range(215, 1040):
            pixels = cast(
                tuple[tuple[int, int, int], ...],
                picture.crop((70, y, 550, y + 1)).get_flattened_data(),
            )
            if sum(max(p) - min(p) < 5 and 180 <= max(p) <= 240 for p in pixels) > 400:
                rows.append(y)
        bands: list[list[int]] = []
        for y in rows:
            if not bands or y > bands[-1][-1] + 1:
                bands.append([])
            bands[-1].append(y)
        assert len(bands) == 3, bands
        baseline = bands[-2][-1]
        assert 250 < baseline < 900 and 15 <= bands[-1][0] - baseline <= 25
        counts: dict[str, int] = {}
        for name, left, right in (("first", 28, 233), ("Gamma", 350, 395), ("Delta", 475, 520)):
            pixels = cast(
                tuple[tuple[int, int, int], ...],
                picture.crop((left, baseline + 2, right, baseline + 13)).get_flattened_data(),
            )
            counts[name] = sum(max(p) < 220 and max(p) - min(p) < 30 for p in pixels)
    assert counts["first"] >= 10 and counts["Gamma"] >= 10, counts
    return {
        "baseline": baseline,
        "bands": bands,
        "ink": counts,
        "threshold": "max(R,G,B)<220 and max-min<30",
        "delta_visible": counts["Delta"] >= 10,
    }
