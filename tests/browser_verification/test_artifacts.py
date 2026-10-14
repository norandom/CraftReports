"""Real ZIP semantic and hostile-input cases; inspection never repairs bytes."""

import hashlib
from contextlib import nullcontext
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from scripts.browser_verification.contracts import Rejected, Succeeded
from scripts.browser_verification.fixture import FixtureExpectation
from scripts.browser_verification.xlsx import inspect

FIXTURE = Path(__file__).parents[1] / "fixtures/browser_verification"
EXPECTED = FixtureExpectation.read(FIXTURE / "expected.json")


def rewritten(tmp_path: Path, changes: dict[str, tuple[str, str]], extra: str = "") -> Path:
    path = tmp_path / "candidate.xlsx"
    with ZipFile(FIXTURE / "reference.xlsx") as source, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            data = source.read(name)
            if name in changes:
                old, new = changes[name]
                assert old in data.decode("utf-8")
                data = data.decode("utf-8").replace(old, new).encode("utf-8")
            target.writestr(name, data)
        if extra:
            target.writestr(extra, b"unsafe")
    return path


def checked(path: Path, phase: str = "before") -> bool:
    before = hashlib.sha256(path.read_bytes()).digest()
    result = inspect(path, EXPECTED, "before" if phase == "before" else "after")
    assert hashlib.sha256(path.read_bytes()).digest() == before
    if isinstance(result, Succeeded):
        assert result.payload.passed
        return True
    assert isinstance(result, Rejected)
    assert result.finding.status == "failed"
    assert all("secret" not in value for value in result.finding.observed)
    return False


def test_original_and_edit(tmp_path: Path) -> None:
    assert checked(FIXTURE / "reference.xlsx")
    path = rewritten(tmp_path, {"xl/worksheets/sheet1.xml": ("<v>20</v>", "<v>25</v>")})
    assert checked(path, "after")
    assert not checked(path)
    assert not checked(FIXTURE / "reference.xlsx", "after")


@pytest.mark.parametrize(
    ("part", "old", "new"),
    [
        ("xl/sharedStrings.xml", "craftreport-browser-reference-v1", "secret-marker"),
        ("xl/sharedStrings.xml", "KEEP", "secret-sentinel"),
        (
            "xl/worksheets/sheet1.xml",
            '<c r="B3" s="2"><v>20</v></c>',
            '<c r="B3" s="2" t="inlineStr"><is><t>20</t></is></c>',
        ),
        ("xl/charts/chart1.xml", "Report!$A$2:$A$4", "Report!$D$2:$D$4"),
        ("xl/charts/chart1.xml", "Report!$B$2:$B$4", "Report!$B$1:$B$3"),
        ("xl/charts/chart1.xml", "Reference series", "secret-title"),
        ("xl/charts/chart1.xml", '<c:legendPos val="b"/>', '<c:legendPos val="t"/>'),
        ("xl/worksheets/sheet1.xml", '<drawing r:id="rId1"/>', ""),
        ("xl/styles.xml", "<b/>", '<b val="0"/>'),
        ("xl/styles.xml", 'numFmtId="1"', 'numFmtId="2"'),
        ("xl/drawings/drawing1.xml", "<xdr:col>5</xdr:col>", "<xdr:col>4</xdr:col>"),
        ("xl/drawings/drawing1.xml", "<xdr:row>16</xdr:row>", "<xdr:row>17</xdr:row>"),
        (
            "xl/_rels/workbook.xml.rels",
            'Target="worksheets/sheet1.xml"',
            'Target="https://secret.example/book" TargetMode="External"',
        ),
        (
            "xl/workbook.xml",
            "<workbook ",
            '<!DOCTYPE workbook [<!ENTITY secret "private">]><workbook ',
        ),
    ],
)
def test_semantic_and_security_corruption(tmp_path: Path, part: str, old: str, new: str) -> None:
    assert not checked(rewritten(tmp_path, {part: (old, new)}))


@pytest.mark.parametrize(
    "name", ["../secret.xml", "/secret.xml", "xl/../secret.xml", "xl/workbook.xml"]
)
def test_unsafe_members(tmp_path: Path, name: str) -> None:
    with pytest.warns(UserWarning) if name == "xl/workbook.xml" else nullcontext():
        path = rewritten(tmp_path, {}, name)
    assert not checked(path)


def test_symlink_and_oversize(tmp_path: Path) -> None:
    for symlink in (True, False):
        path = rewritten(tmp_path, {})
        with ZipFile(path, "a", ZIP_DEFLATED) as archive:
            info = ZipInfo("secret.xml")
            info.external_attr = (0o120777 << 16) if symlink else (0o100600 << 16)
            archive.writestr(info, b"x" if symlink else b"x" * 1_000_001)
        assert not checked(path)


def test_equivalent_parts_strings_and_references(tmp_path: Path) -> None:
    path = tmp_path / "equivalent.xlsx"
    names = {
        "xl/workbook.xml": "xl/book.xml",
        "xl/_rels/workbook.xml.rels": "xl/_rels/book.xml.rels",
        "xl/worksheets/sheet1.xml": "xl/worksheets/report.xml",
        "xl/worksheets/_rels/sheet1.xml.rels": "xl/worksheets/_rels/report.xml.rels",
        "xl/charts/chart1.xml": "xl/charts/line.xml",
        "xl/drawings/drawing1.xml": "xl/drawings/plot.xml",
        "xl/drawings/_rels/drawing1.xml.rels": "xl/drawings/_rels/plot.xml.rels",
        "xl/styles.xml": "xl/formats.xml",
    }
    with ZipFile(FIXTURE / "reference.xlsx") as source, ZipFile(path, "w") as target:
        for name in source.namelist():
            data = source.read(name).decode("utf-8")
            for old, new in names.items():
                data = data.replace(old, new).replace(old.split("/")[-1], new.split("/")[-1])
            data = data.replace("Report!$A$2:$A$4", "'Report'!A2:A4").replace(
                "Report!$B$2:$B$4", "'Report'!B2:B4"
            )
            data = data.replace(
                '<c r="A1" s="1" t="s"><v>0</v></c>',
                '<c r="A1" s="1" t="inlineStr"><is><t>Period</t></is></c>',
            )
            target.writestr(names.get(name, name), data)
    assert checked(path)


def test_recorded_artifact_binding(tmp_path: Path) -> None:
    from uuid import uuid4

    from scripts.browser_verification.contracts import ArtifactIdentity, TargetIdentity
    from scripts.browser_verification.xlsx import inspect_artifact

    path = rewritten(tmp_path, {"xl/worksheets/sheet1.xml": ("<v>20</v>", "<v>25</v>")})
    data = path.read_bytes()
    target = TargetIdentity(
        run_id=uuid4(),
        context_id=uuid4(),
        page_id=uuid4(),
        generation=1,
        origin="http://localhost:8872",
        mode="browser-wasm",
        build_sha256="a" * 64,
        fixture_id=uuid4(),
        fixture_marker=EXPECTED.marker.value,
        artifact_sha256=EXPECTED.fixture.sha256,
    )
    artifact = ArtifactIdentity(
        artifact_id=uuid4(),
        destination=path,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        target=target,
        route="download",
    )
    assert isinstance(inspect_artifact(artifact, EXPECTED), Succeeded)
    for invalid in (
        artifact.model_copy(update={"size": len(data) + 1}),
        artifact.model_copy(update={"sha256": "b" * 64}),
    ):
        assert isinstance(inspect_artifact(invalid, EXPECTED), Rejected)
    assert path.read_bytes() == data


def test_manifest_validation_and_immutability() -> None:
    import json

    from pydantic import ValidationError

    with pytest.raises(TypeError):
        EXPECTED.before["B3"] = EXPECTED.after["B3"]  # type: ignore[index]
    for old, new in (
        ('"schema_version": 1', '"schema_version": 2'),
        ('"type": "number", "value": 20', '"type": "number", "value": "20"'),
        ('"address": "B3"', '"address": "C3"'),
    ):
        text = (FIXTURE / "expected.json").read_text(encoding="utf-8").replace(old, new)
        with pytest.raises(ValidationError):
            FixtureExpectation.model_validate_json(text)
    malformed = json.loads((FIXTURE / "expected.json").read_text(encoding="utf-8"))
    del malformed["before"]["D2"]
    with pytest.raises(ValidationError):
        FixtureExpectation.model_validate_json(json.dumps(malformed))


@pytest.mark.parametrize("count,size", [(101, 0), (5, 900_000)])
def test_archive_count_and_total_bounds(tmp_path: Path, count: int, size: int) -> None:
    path = rewritten(tmp_path, {})
    with ZipFile(path, "a", ZIP_DEFLATED) as archive:
        for index in range(count):
            archive.writestr(f"extra{index}.bin", b"x" * size)
    assert not checked(path)


def test_after_string_number_is_wrong_type(tmp_path: Path) -> None:
    path = rewritten(
        tmp_path,
        {
            "xl/worksheets/sheet1.xml": (
                '<c r="B3" s="2"><v>20</v></c>',
                '<c r="B3" s="2" t="inlineStr"><is><t>25</t></is></c>',
            )
        },
    )
    assert not checked(path, "after")


@pytest.mark.parametrize(
    "target", ["../../../secret.xml", "%2e%2e/%2e%2e/secret.xml", "//secret.example/book"]
)
def test_unsafe_relationship_targets(tmp_path: Path, target: str) -> None:
    path = rewritten(
        tmp_path,
        {"xl/_rels/workbook.xml.rels": ('Target="worksheets/sheet1.xml"', f'Target="{target}"')},
    )
    assert not checked(path)


def test_utf16_dtd_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "utf16.xlsx"
    with ZipFile(FIXTURE / "reference.xlsx") as source, ZipFile(path, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "xl/workbook.xml":
                xml = data.decode("utf-8").replace('encoding="UTF-8"', 'encoding="UTF-16"')
                xml = xml.replace(
                    "<workbook ", '<!DOCTYPE workbook [<!ENTITY secret "private">]><workbook '
                )
                data = xml.encode("utf-16")
            target.writestr(name, data)
    assert not checked(path)


@pytest.mark.parametrize("column", ["A", "B"])
@pytest.mark.parametrize(
    "sheet", ["'Re''port'", "Re'port", "' Report'", "'Report '", "'[external.xlsx]Report'"]
)
def test_distinct_chart_source_sheet_is_rejected(tmp_path: Path, column: str, sheet: str) -> None:
    original = f"Report!${column}$2:${column}$4"
    replacement = f"{sheet}!${column}$2:${column}$4"
    assert not checked(rewritten(tmp_path, {"xl/charts/chart1.xml": (original, replacement)}))


@pytest.mark.parametrize("column", ["A", "B"])
def test_quoted_relative_reference_with_optional_equals(tmp_path: Path, column: str) -> None:
    original = f"Report!${column}$2:${column}$4"
    replacement = f"='Report'!{column}2:{column}4"
    assert checked(rewritten(tmp_path, {"xl/charts/chart1.xml": (original, replacement)}))
