"""Public content activates through the same contained production pack loader."""

from hashlib import sha256
from pathlib import Path

import pytest

from craftreport.adapters.canonical import WireFailure
from craftreport.adapters.pack_reader import ConfiguredPackReader, PackSource
from craftreport.adapters.report_codecs import decode_manifest, decode_theme, theme_identifier
from craftreport.contracts.identity import Principal
from craftreport.policies.values import CheckId
from craftreport.reporting.definitions import DatasetRef, ParameterRef
from craftreport.reporting.ports import PackFailure, PackSelection
from craftreport.reporting.prepared import ResolvedPack
from craftreport.themes.values import SemanticRole

ROOT = Path(__file__).resolve().parents[2]
SELECTION = PackSelection("public", "supplied_portfolio", "1.0.0")
PUBLIC = Principal("public-demo", "adopter", frozenset({"public_source", "public_artifact"}))


def stage_public_pack(root: Path) -> ConfiguredPackReader:
    definition = (ROOT / "examples/reports/supplied_portfolio.json").read_bytes()
    theme = (ROOT / "examples/themes/house.json").read_bytes()
    manifest = (ROOT / "examples/templates/public_report/manifest.json").read_bytes()
    for name, content in (
        ("definition.json", definition),
        ("template.json", definition),
        ("theme.json", theme),
        ("manifest.json", manifest),
    ):
        (root / name).write_bytes(content)
    return ConfiguredPackReader((PackSource(root, "public_source", "public_artifact"),))


def test_public_table_chart_contract_and_independent_pins(tmp_path: Path) -> None:
    reader = stage_public_pack(tmp_path)
    pack = reader.read(SELECTION, PUBLIC)
    assert isinstance(pack, ResolvedPack)
    definition = pack.definition
    assert definition.report_id == "public/supplied_portfolio"
    assert definition.version == "1.0.0"
    assert definition.title == ParameterRef("title")
    assert definition.parameters[0].default == "Synthetic portfolio"
    assert isinstance(definition.table.source, DatasetRef)
    assert definition.table.source == definition.chart.source
    assert definition.table.source.name == "portfolio"
    assert [(f.name, f.kind, f.unit, f.nullable) for f in definition.table.source.fields] == [
        ("date", "date", None, False),
        ("nav", "decimal", "USD", True),
        ("benchmark", "decimal", "USD", True),
        ("note", "text", None, False),
    ]
    assert tuple(c.field for c in definition.table.columns) == ("date", "nav", "benchmark", "note")
    assert definition.chart.category_field == "date"
    assert tuple(s.field for s in definition.chart.series) == ("nav", "benchmark")
    assert definition.chart.null_behavior == "gap"
    assert definition.release_policy.required_checks == (
        CheckId.DEFINITION,
        CheckId.BINDINGS,
        CheckId.SEMANTIC_RESOLUTION,
        CheckId.LAYOUT_FIT,
    )
    assert definition.compliance_statement is None
    manifest = decode_manifest((tmp_path / "manifest.json").read_bytes())
    for reference in (manifest.definition, manifest.template, manifest.theme):
        assert reference.sha256 == sha256((tmp_path / reference.path).read_bytes()).hexdigest()
    assert pack.definition_pin == pack.template
    assert pack.theme.version_pin.content_digest == theme_identifier(pack.theme)
    styles = dict(pack.theme.styles)
    assert set(styles) == set(SemanticRole)
    assert styles[SemanticRole.SOURCE].fill == "#BDD7EE"
    assert styles[SemanticRole.INPUT].fill == "#FFFF00"
    assert styles[SemanticRole.KEY_RESULT].fill == "#000080"
    assert reader.discover(PUBLIC)[0].identity == SELECTION.identity
    artifact_only = Principal("public-demo", "artifact-only", frozenset({"public_artifact"}))
    assert reader.discover(artifact_only) == ()
    assert reader.read(SELECTION, artifact_only) == PackFailure()


def test_public_theme_and_asset_tampering_rejects(tmp_path: Path) -> None:
    stage_public_pack(tmp_path)
    theme_path = tmp_path / "theme.json"
    modified = theme_path.read_bytes().replace(b"#BDD7EE", b"#BDD7EF")
    with pytest.raises(WireFailure):
        decode_theme(modified)
    theme_path.write_bytes(modified)
    with pytest.raises(WireFailure):
        ConfiguredPackReader((PackSource(tmp_path, "public_source", "public_artifact"),))
