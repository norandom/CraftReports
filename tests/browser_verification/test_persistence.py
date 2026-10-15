"""Real file boundary safety independent of browser UI."""

import hashlib
from pathlib import Path

import pytest

from scripts.browser_verification.persistence import persist


def test_exclusive_real_bytes(tmp_path: Path) -> None:
    source = tmp_path / "download"
    source.write_bytes(b"actual download bytes")
    destination = tmp_path / "result.xlsx"
    size, digest = persist(source, destination)
    assert destination.read_bytes() == source.read_bytes()
    assert (size, digest) == (
        source.stat().st_size,
        hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    with pytest.raises(FileExistsError):
        persist(source, destination)
    assert destination.read_bytes() == b"actual download bytes"


@pytest.mark.parametrize("size", [0, 4_000_001])
def test_missing_or_oversized_download_cannot_persist(tmp_path: Path, size: int) -> None:
    source = tmp_path / "download"
    source.write_bytes(b"x" * size)
    with pytest.raises(ValueError):
        persist(source, tmp_path / "result.xlsx")
    assert not (tmp_path / "result.xlsx").exists()
