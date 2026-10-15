"""Actual external files exercise production activation and authorization."""

import json
import os
import subprocess
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO, cast

import pytest
from test_prepare import definition as definition
from test_themes import theme as theme

from craftreport.adapters import pack_reader as p
from craftreport.adapters import report_codecs as c
from craftreport.adapters.canonical import WireFailure, canonical_bytes
from craftreport.contracts.identity import Principal
from craftreport.contracts.values import JsonObject
from craftreport.reporting.definitions import ReportDefinition
from craftreport.reporting.ports import PackFailure, PackSelection
from craftreport.reporting.prepared import ResolvedPack
from craftreport.themes.values import Theme

ALLOWED = Principal("deployment", "reader", frozenset({"source"}))
DENIED = Principal("deployment", "reader", frozenset({"artifact"}))
SELECTION = PackSelection("public", "example", "1.0.0")


@pytest.fixture
def assets(definition: ReportDefinition, theme: Theme) -> dict[str, bytes]:
    theme = replace(
        theme, version_pin=replace(theme.version_pin, content_digest=c.theme_identifier(theme))
    )
    return {
        "definition.json": c.encode_definition(definition),
        "template.json": json.dumps(json.loads(c.encode_definition(definition)), indent=2).encode(),
        "theme.json": c.encode_theme(theme),
    }


def write_pack(root: Path, assets: dict[str, bytes], **changes: object) -> JsonObject:
    root.mkdir(parents=True, exist_ok=True)
    for name, data in assets.items():
        (root / name).write_bytes(data)
    definition = c.decode_definition(assets["definition.json"])
    theme = c.decode_theme(assets["theme.json"])
    manifest: dict[str, object] = {
        "schema_version": "1",
        "namespace": "public",
        "name": "example",
        "version": "1.0.0",
        "engine_version_range": ">=0.1,<1",
        **{
            name: {"path": name + ".json", "sha256": sha256(assets[name + ".json"]).hexdigest()}
            for name in ("definition", "template", "theme")
        },
        "required_capabilities": [
            {"identity": r.identity, "version_range": r.version_range, "target_mode": r.target_mode}
            for r in definition.required_capabilities
        ],
        "permitted_overrides": [list(v) for v in theme.permitted_overrides],
        "source_visibility_scope": "source",
        "artifact_visibility_scope": "artifact",
        "attribution": "Synthetic",
    }
    manifest.update(changes)
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return cast(JsonObject, json.loads(json.dumps(manifest)))


def reader(root: Path) -> p.ConfiguredPackReader:
    return p.ConfiguredPackReader((p.PackSource(root, "source", "artifact"),))


def test_real_files_pins_freeze_and_separate_scopes(
    tmp_path: Path, assets: dict[str, bytes]
) -> None:
    manifest = write_pack(tmp_path, assets)
    loaded = reader(tmp_path)
    pack = loaded.read(SELECTION, ALLOWED)
    assert isinstance(pack, ResolvedPack)
    assert pack.definition_pin == pack.template
    assert pack.definition_pin.content_digest == c.definition_identifier(pack.definition)
    assert pack.pin.version_pin.content_digest == sha256(canonical_bytes(manifest)).hexdigest()
    assert pack.pin.artifact_visibility_scope == "artifact"
    assert loaded.discover(ALLOWED)[0].identity == "public/example"
    assert loaded.discover(DENIED) == ()
    assert (
        loaded.read(SELECTION, DENIED)
        == loaded.read(replace(SELECTION, name="missing"), DENIED)
        == PackFailure()
    )
    assert loaded.read(replace(SELECTION, version="1"), ALLOWED) == PackFailure()
    for file in tmp_path.iterdir():
        file.unlink()
    assert loaded.read(SELECTION, ALLOWED) is pack
    with pytest.raises(FrozenInstanceError):
        pack.definition.title = "changed"  # pyright: ignore[reportAttributeAccessIssue]


def test_temporary_private_same_codec(
    tmp_path: Path, assets: dict[str, bytes], definition: ReportDefinition
) -> None:
    private = dict(assets)
    private["definition.json"] = private["template.json"] = c.encode_definition(
        replace(definition, title="PRIVATE_TEST_ONLY")
    )
    root = tmp_path / "external-private"
    write_pack(root, private, namespace="private")
    loaded = reader(root)
    assert loaded.discover(DENIED) == ()
    assert "PRIVATE_TEST_ONLY" not in repr(
        loaded.read(PackSelection("private", "example", "1.0.0"), DENIED)
    )
    pack = loaded.read(PackSelection("private", "example", "1.0.0"), ALLOWED)
    assert isinstance(pack, ResolvedPack) and pack.definition.title == "PRIVATE_TEST_ONLY"
    assert (
        loaded.read(
            PackSelection("private", "example", "1.0.0"),
            replace(ALLOWED, permitted_scopes=frozenset()),
        )
        == PackFailure()
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "latest"},
        {"engine_version_range": ">=99"},
        {"engine_version_range": "bad"},
        {"source_visibility_scope": "broadened"},
        {"artifact_visibility_scope": "public"},
        {"execute": "private sentinel"},
        {"required_capabilities": []},
        {"permitted_overrides": []},
    ],
)
def test_reject_manifest(
    tmp_path: Path, assets: dict[str, bytes], changes: dict[str, object]
) -> None:
    write_pack(tmp_path, assets, **changes)
    with pytest.raises(WireFailure, match="invalid_pack") as failure:
        reader(tmp_path)
    assert "sentinel" not in str(failure.value) and str(tmp_path) not in str(failure.value)


@pytest.mark.parametrize("asset", ["definition.json", "template.json", "theme.json"])
def test_independent_raw_hashes(tmp_path: Path, assets: dict[str, bytes], asset: str) -> None:
    write_pack(tmp_path, assets)
    (tmp_path / asset).write_bytes(assets[asset] + b" ")
    with pytest.raises(WireFailure):
        reader(tmp_path)


def test_raw_vs_semantic_and_distinct_template(
    tmp_path: Path, assets: dict[str, bytes], definition: ReportDefinition
) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    write_pack(first, assets)
    write_pack(second, {**assets, "definition.json": assets["definition.json"] + b" "})
    a, b = reader(first).read(SELECTION, ALLOWED), reader(second).read(SELECTION, ALLOWED)
    assert isinstance(a, ResolvedPack) and isinstance(b, ResolvedPack)
    assert a.definition_pin == b.definition_pin and a.pin != b.pin
    write_pack(
        second,
        {**assets, "template.json": c.encode_definition(replace(definition, title="different"))},
    )
    with pytest.raises(WireFailure):
        reader(second)
    with pytest.raises(WireFailure):
        p.ConfiguredPackReader((p.PackSource(first, "source", "artifact"),) * 2)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.json",
        "/absolute.json",
        "C:asset.json",
        "C:/asset.json",
        "//server/share.json",
        "https://example/a.json",
        "asset.py",
    ],
)
def test_path_rejection(tmp_path: Path, assets: dict[str, bytes], path: str) -> None:
    write_pack(
        tmp_path,
        assets,
        definition={"path": path, "sha256": sha256(assets["definition.json"]).hexdigest()},
    )
    with pytest.raises(WireFailure):
        reader(tmp_path)


def junction(link: Path, target: Path) -> None:
    if os.name == "nt":
        command = f'New-Item -ItemType Junction -Path "{link}" -Target "{target}" | Out-Null'
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command], check=True, capture_output=True
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def test_actual_junction_escape_and_open_race(
    tmp_path: Path, assets: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, outside = tmp_path / "root", tmp_path / "outside"
    outside.mkdir()
    (outside / "definition.json").write_bytes(assets["definition.json"])
    write_pack(
        root,
        assets,
        definition={
            "path": "link/definition.json",
            "sha256": sha256(assets["definition.json"]).hexdigest(),
        },
    )
    junction(root / "link", outside)
    with pytest.raises(WireFailure):
        reader(root)
    (root / "link").rmdir() if os.name == "nt" else (root / "link").unlink()
    (root / "link").mkdir()
    (root / "link" / "definition.json").write_bytes(assets["definition.json"])
    original = Path.open

    def replace_link() -> None:
        (root / "link" / "definition.json").unlink()
        (root / "link").rmdir()
        junction(root / "link", outside)

    def replace_before_open(path: Path, mode: str = "r") -> BinaryIO:
        if path == root / "link" / "definition.json":
            replace_link()
        return cast(BinaryIO, original(path, mode))

    original_open = os.open

    def replace_before_os_open(
        path: str | Path, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if path == "link/definition.json":
            replace_link()
        return original_open(path, flags, mode, dir_fd=dir_fd)

    if os.name == "nt":
        monkeypatch.setattr(Path, "open", replace_before_open)
    else:
        monkeypatch.setattr(os, "open", replace_before_os_open)
    with pytest.raises(WireFailure):
        reader(root)


def test_missing_and_oversized_are_atomic(tmp_path: Path, assets: dict[str, bytes]) -> None:
    write_pack(tmp_path, assets)
    (tmp_path / "theme.json").unlink()
    with pytest.raises(WireFailure):
        reader(tmp_path)
    write_pack(tmp_path, assets)
    (tmp_path / "manifest.json").write_bytes(b" " * 65537)
    with pytest.raises(WireFailure):
        reader(tmp_path)


def test_semantic_tamper_even_with_updated_raw_hash(
    tmp_path: Path, assets: dict[str, bytes]
) -> None:
    tampered = json.loads(assets["theme.json"])
    tampered["null_marker"] = "changed"
    altered = {**assets, "theme.json": json.dumps(tampered).encode()}
    root = tmp_path / "source"
    write_pack(root, assets)
    manifest = json.loads((root / "manifest.json").read_bytes())
    (root / "theme.json").write_bytes(altered["theme.json"])
    manifest["theme"]["sha256"] = sha256(altered["theme.json"]).hexdigest()
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(WireFailure):
        reader(root)


@pytest.mark.parametrize("path", [("definition",), ("required_capabilities", 0)])
def test_nested_manifest_unknowns(
    tmp_path: Path, assets: dict[str, bytes], path: tuple[str | int, ...]
) -> None:
    write_pack(tmp_path, assets)
    manifest = json.loads((tmp_path / "manifest.json").read_bytes())
    node = manifest
    for key in path:
        node = node[key]
    node["execute"] = "sentinel"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(WireFailure):
        reader(tmp_path)


def test_no_ambient_search_and_manifest_whitespace(
    tmp_path: Path, assets: dict[str, bytes]
) -> None:
    write_pack(tmp_path / "nested", assets)
    with pytest.raises(WireFailure):
        reader(tmp_path)
    first = reader(tmp_path / "nested").read(SELECTION, ALLOWED)
    manifest = tmp_path / "nested" / "manifest.json"
    manifest.write_text(json.dumps(json.loads(manifest.read_bytes()), indent=2), encoding="utf-8")
    assert reader(tmp_path / "nested").read(SELECTION, ALLOWED) == first


def test_unavailable_containment_fails_closed(
    tmp_path: Path, assets: dict[str, bytes], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_pack(tmp_path, assets)

    def unavailable(handle: int) -> Path:
        raise OSError("private platform diagnostic")

    monkeypatch.setattr(p, "_final_path", unavailable)
    with pytest.raises(WireFailure, match="invalid_pack") as failure:
        reader(tmp_path)
    assert "private" not in str(failure.value)


@pytest.mark.skipif(os.name != "nt", reason="Windows directory handle sharing contract")
def test_windows_root_rename_blocked_until_anchor_closes(tmp_path: Path) -> None:
    root, renamed = tmp_path / "root", tmp_path / "renamed"
    root.mkdir()
    with p._anchor(root):  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(PermissionError):
            root.rename(renamed)
        assert root.is_dir() and not renamed.exists()
    root.rename(renamed)
    assert renamed.is_dir() and not root.exists()
