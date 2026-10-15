"""Immutable deployment-configured pack activation from contained opened files."""

import os
import re
import stat
import sys
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import BinaryIO, cast

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from craftreport.adapters.canonical import WireFailure, canonical_bytes
from craftreport.adapters.report_codecs import (
    decode_definition,
    decode_manifest,
    decode_theme,
    definition_identifier,
)
from craftreport.adapters.report_models import AssetReference
from craftreport.contracts.identity import Principal
from craftreport.contracts.pins import VersionPin
from craftreport.contracts.values import JsonObject
from craftreport.reporting.definitions import ReportDefinition, text
from craftreport.reporting.ports import PackFailure, PackSelection, PackSummary
from craftreport.reporting.prepare import validate_template
from craftreport.reporting.prepared import ResolvedPack
from craftreport.themes.values import PackPin, Theme


@dataclass(frozen=True, slots=True)
class PackSource:
    root: Path
    source_visibility_scope: str
    artifact_visibility_scope: str


def _final_path(handle: int) -> Path:
    if os.name == "nt":
        import ctypes

        function = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        function.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong]
        function.restype = ctypes.c_ulong
        buffer = ctypes.create_unicode_buffer(32768)
        length = function(handle, buffer, len(buffer), 0)
        if not 0 < length < len(buffer):
            raise ValueError("Containment unavailable")
        return Path(buffer.value.removeprefix("\\\\?\\"))
    if sys.platform == "linux":
        return Path(os.readlink(f"/proc/self/fd/{handle}"))
    raise ValueError("Unsupported containment platform")


@contextmanager
def _anchor(root: Path) -> Generator[tuple[int, Path]]:
    if not root.is_absolute() or str(root).startswith(("\\\\", "//")):
        raise ValueError("Local absolute root required")
    if os.name == "nt":
        import ctypes

        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        ]
        create.restype = ctypes.c_void_p
        handle = cast(int, create(str(root), 1, 3, None, 3, 0x02000000, None))
        if handle in (None, -1, ctypes.c_void_p(-1).value):
            raise OSError("Cannot anchor root")
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
    elif sys.platform == "linux":
        handle = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        close = os.close
    else:
        raise ValueError("Unsupported containment platform")
    try:
        anchor = _final_path(handle)
        if not anchor.is_dir() or str(anchor).startswith(("\\\\", "//")):
            raise ValueError("Invalid root")
        yield handle, anchor
    finally:
        close(handle)


def _opened(handle: BinaryIO) -> Path:
    descriptor = handle.fileno()
    if os.name == "nt":
        import msvcrt

        descriptor = msvcrt.get_osfhandle(descriptor)
    return _final_path(descriptor)


def _read(root: Path, anchor: tuple[int, Path], relative: str, maximum: int) -> bytes:
    if (
        not relative.endswith(".json")
        or any(c in relative for c in ("\\", ":"))
        or any(part in ("", ".", "..") for part in relative.split("/"))
    ):
        raise ValueError("Unsupported asset path")
    candidate = root / relative
    if not candidate.resolve(strict=True).is_relative_to(anchor[1]):
        raise ValueError("Asset outside root")
    if os.name == "nt":
        stream = candidate.open("rb")
    else:
        stream = os.fdopen(os.open(relative, os.O_RDONLY | os.O_NONBLOCK, dir_fd=anchor[0]), "rb")
    with stream:
        if not _opened(stream).is_relative_to(anchor[1]) or _final_path(anchor[0]) != anchor[1]:
            raise ValueError("Opened asset outside anchored root")
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Asset must be a regular file")
        data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("Asset exceeds limit")
        return data


def _asset(root: Path, anchor: tuple[int, Path], reference: AssetReference, maximum: int) -> bytes:
    data = _read(root, anchor, reference.path, maximum)
    if sha256(data).hexdigest() != reference.sha256:
        raise ValueError("Asset hash mismatch")
    return data


def _load(
    source: PackSource,
    engine: Version,
    declaration: Callable[[bytes], ReportDefinition],
    theme_decoder: Callable[[bytes], Theme],
    identify: Callable[[ReportDefinition], str],
) -> ResolvedPack:
    with _anchor(source.root) as anchor:
        manifest = decode_manifest(_read(source.root, anchor, "manifest.json", 65536))
        selection = PackSelection(manifest.namespace, manifest.name, manifest.version)
        if any(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", v) is None
            for v in (selection.namespace, selection.name)
        ):
            raise ValueError("Invalid qualified identity")
        Version(selection.version)
        if engine not in SpecifierSet(manifest.engine_version_range):
            raise ValueError("Incompatible engine")
        for configured, supplied in (
            (source.source_visibility_scope, manifest.source_visibility_scope),
            (source.artifact_visibility_scope, manifest.artifact_visibility_scope),
        ):
            text(configured, ("scope",))
            if configured != supplied:
                raise ValueError("Scope mismatch")
        definition = declaration(_asset(source.root, anchor, manifest.definition, 65536))
        template = declaration(_asset(source.root, anchor, manifest.template, 65536))
        theme = theme_decoder(_asset(source.root, anchor, manifest.theme, 32768))
    pin = VersionPin(definition.report_id, definition.version, identify(definition))
    template_pin = VersionPin(template.report_id, template.version, identify(template))
    validate_template(definition, template_pin, identify)
    if (
        definition != template
        or manifest.required_capabilities != definition.required_capabilities
        or manifest.permitted_overrides != theme.permitted_overrides
    ):
        raise ValueError("Declaration mismatch")
    pack_pin = VersionPin(
        selection.identity,
        selection.version,
        sha256(canonical_bytes(cast(JsonObject, manifest.model_dump(mode="json")))).hexdigest(),
    )
    return ResolvedPack(
        PackPin(pack_pin, manifest.attribution, source.artifact_visibility_scope),
        definition,
        pin,
        template_pin,
        theme,
    )


@dataclass(frozen=True, slots=True, init=False)
class ConfiguredPackReader:
    _packs: tuple[tuple[PackSelection, str, ResolvedPack], ...]

    def __init__(
        self,
        sources: tuple[PackSource, ...],
        *,
        engine_version: str | None = None,
        declaration: Callable[[bytes], ReportDefinition] = decode_definition,
        theme_decoder: Callable[[bytes], Theme] = decode_theme,
        identify: Callable[[ReportDefinition], str] = definition_identifier,
    ) -> None:
        packs: list[tuple[PackSelection, str, ResolvedPack]] = []
        try:
            engine = Version(
                engine_version if engine_version is not None else version("craftreport")
            )
            for source in sources:
                pack = _load(source, engine, declaration, theme_decoder, identify)
                namespace, name = pack.pin.version_pin.identity.split("/")
                selection = PackSelection(namespace, name, pack.pin.version_pin.version)
                if any(
                    s.identity == selection.identity
                    and Version(s.version) == Version(selection.version)
                    for s, _, _ in packs
                ):
                    raise ValueError("Duplicate pack")
                packs.append((selection, source.source_visibility_scope, pack))
        except (OSError, ValueError, TypeError, RecursionError):
            raise WireFailure("invalid_pack") from None
        object.__setattr__(self, "_packs", tuple(packs))

    def discover(self, principal: Principal) -> tuple[PackSummary, ...]:
        return tuple(
            PackSummary(
                s.identity, s.version, pack.pin.attribution, pack.pin.artifact_visibility_scope
            )
            for s, scope, pack in self._packs
            if scope in principal.permitted_scopes
        )

    def read(self, selection: PackSelection, principal: Principal) -> ResolvedPack | PackFailure:
        return next(
            (
                pack
                for s, scope, pack in self._packs
                if scope in principal.permitted_scopes and s == selection
            ),
            PackFailure(),
        )
