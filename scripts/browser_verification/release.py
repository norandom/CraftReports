"""Official metadata, independently trusted bytes and immutable bounded ZIP cache."""

from __future__ import annotations

import hashlib
import io
import re
import stat
import time
import zipfile
import zlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
from packaging.version import Version
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import RunConfig
from .contracts import (
    AbsolutePath,
    ContentIdentity,
    Outcome,
    Rejected,
    Sha256,
    StageFinding,
    Succeeded,
    Text,
    Value,
)

LATEST = "https://api.github.com/repos/storytold/gridcraft/releases/latest"
PUBLIC = "https://github.com/storytold/gridcraft/releases/"
MAX_ARCHIVE = 64 * 1024 * 1024
MAX_EXPANDED = 256 * 1024 * 1024
MAX_MEMBERS = 512


class ReleaseError(ValueError):
    """Safe fixed diagnostic, never an external exception payload."""


class Asset(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    id: int = Field(gt=0)
    name: str
    size: int = Field(gt=0)
    digest: str | None = None
    browser_download_url: str


class Metadata(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    tag_name: str
    draft: bool
    prerelease: bool
    published_at: datetime
    html_url: str
    assets: tuple[Asset, ...]


class ReleaseIdentity(Value):
    version: Text
    source: Text = LATEST
    release_url: Text
    acquired_at: datetime
    published_at: datetime
    asset_id: int = Field(gt=0, strict=True)
    asset_name: Text
    asset_url: Text
    size: int = Field(gt=0, le=MAX_ARCHIVE, strict=True)
    sha256: Sha256
    trust_source: Text
    bound: float = Field(gt=0, allow_inf_nan=False)


class BundleIdentity(Value):
    release: ReleaseIdentity
    archive: AbsolutePath
    root: AbsolutePath
    files: tuple[ContentIdentity, ...]


def reject(reason: str) -> Rejected:
    return Rejected(
        finding=StageFinding(
            stage="release",
            requirements=("1.1", "1.2", "1.3", "6.6"),
            status="blocked",
            observed=(reason,),
        )
    )


def remaining(deadline: float) -> float:
    bound = deadline - time.monotonic()
    if bound <= 0:
        raise ReleaseError("release deadline exceeded")
    return bound


def fetch(client: httpx.Client, url: str, limit: int, deadline: float) -> bytes:
    for attempt in range(2):
        try:
            with client.stream(
                "GET", url, timeout=remaining(deadline), follow_redirects=True
            ) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes(65536):
                    remaining(deadline)
                    size += len(chunk)
                    if size > limit:
                        raise ReleaseError("download size bound exceeded")
                    chunks.append(chunk)
                return b"".join(chunks)
        except httpx.HTTPError:
            if attempt:
                raise
    raise ValueError("download unavailable")


def select(config: RunConfig, data: bytes) -> ReleaseIdentity:
    metadata = Metadata.model_validate_json(data)
    version = Version(metadata.tag_name.removeprefix("v"))
    if metadata.draft or metadata.prerelease or version.is_prerelease or version.is_devrelease:
        raise ReleaseError("latest release is not stable")
    if version < Version("0.6.1"):
        raise ReleaseError("latest release is older than 0.6.1")
    name = f"gridcraft-web-{version}.zip"
    assets = [asset for asset in metadata.assets if asset.name == name]
    if len(assets) != 1:
        raise ReleaseError("latest release requires one unique prebuilt web asset")
    asset = assets[0]
    release_url = PUBLIC + "tag/" + metadata.tag_name
    asset_url = PUBLIC + "download/" + metadata.tag_name + "/" + name
    if metadata.html_url != release_url or asset.browser_download_url != asset_url:
        raise ReleaseError("official release URL identity mismatch")
    digest = asset.digest.removeprefix("sha256:") if asset.digest else config.trusted_release_sha256
    if not digest or (asset.digest and not asset.digest.startswith("sha256:")):
        raise ReleaseError("missing or invalid independent trusted release digest")
    if config.trusted_release_sha256 and digest != config.trusted_release_sha256:
        raise ReleaseError("published and configured trusted digests disagree")
    return ReleaseIdentity(
        version=str(version),
        release_url=release_url,
        acquired_at=datetime.now(UTC),
        published_at=metadata.published_at,
        asset_id=asset.id,
        asset_name=name,
        asset_url=asset_url,
        size=asset.size,
        sha256=digest,
        trust_source=LATEST if asset.digest else config.trust_source or "",
        bound=config.bounds.readiness,
    )


def resolve_release(
    config: RunConfig, *, client: httpx.Client | None = None
) -> Outcome[ReleaseIdentity]:
    try:
        if client is None:
            with httpx.Client() as owned:
                return resolve_release(config, client=owned)
        return Succeeded(
            payload=select(
                config,
                fetch(client, LATEST, 1024 * 1024, time.monotonic() + config.bounds.readiness),
            )
        )
    except ReleaseError as error:
        return reject(str(error))
    except (httpx.HTTPError, ValueError, ValidationError):
        return reject("latest lookup or metadata rejected; no cached fallback")


def members(zipped: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = zipped.infolist()
    if len(entries) > MAX_MEMBERS or sum(item.file_size for item in entries) > MAX_EXPANDED:
        raise ReleaseError("archive expansion bounds exceeded")
    aliases: set[str] = set()
    for item in entries:
        name = item.filename.removesuffix("/")
        parts = name.split("/")
        if (
            item.orig_filename != item.filename
            or not name
            or "\\" in name
            or any(unsafe_part(part) for part in parts)
        ):
            raise ReleaseError("unsafe archive member path")
        alias = name.casefold()
        if alias in aliases or stat.S_ISLNK(item.external_attr >> 16):
            raise ReleaseError("duplicate alias or symlink archive member")
        aliases.add(alias)
    return entries


def unsafe_part(part: str) -> bool:
    return (
        part in ("", ".", "..")
        or part.endswith((".", " "))
        or any(char in part for char in ':<>"|?*')
        or any(ord(char) < 32 for char in part)
        or bool(re.fullmatch(r"(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", part))
    )


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()) or any(
        parent.is_symlink() for parent in (path, *path.parents)
    ):
        raise ReleaseError("cache path escapes owned root or follows symlink")
    return path


def unpack(data: bytes, root: Path, deadline: float) -> tuple[ContentIdentity, ...]:
    with zipfile.ZipFile(io.BytesIO(data)) as zipped:
        entries = members(zipped)
        files: list[ContentIdentity] = []
        existing = root.exists()
        for item in entries:
            remaining(deadline)
            path = safe_path(root, item.filename)
            if item.is_dir():
                continue
            content = zipped.read(item)
            if existing:
                if path.stat().st_size != len(content) or path.read_bytes() != content:
                    raise ReleaseError("corrupt extracted cache")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as destination:
                    destination.write(content)
            files.append(
                ContentIdentity(path=item.filename, sha256=hashlib.sha256(content).hexdigest())
            )
        expected = {item.path for item in files}
        if any(path.is_symlink() for path in root.rglob("*")):
            raise ReleaseError("symlink in extracted cache")
        if {
            path.relative_to(root).as_posix() for path in root.rglob("*") if not path.is_dir()
        } != expected:
            raise ReleaseError("unexpected extracted cache member")
        if not all(
            any(item.path.endswith(extension) for item in files)
            for extension in (".html", ".js", ".wasm")
        ):
            raise ReleaseError("missing HTML/JS/WASM assets")
        return tuple(files)


def acquire(
    release: ReleaseIdentity, root: Path, *, client: httpx.Client | None = None
) -> Outcome[BundleIdentity]:
    try:
        if client is None:
            with httpx.Client() as owned:
                return acquire(release, root, client=owned)
        if not root.is_absolute():
            raise ReleaseError("cache root must be absolute")
        deadline = time.monotonic() + release.bound
        root.mkdir(parents=True, exist_ok=True)
        archive = safe_path(root, release.sha256 + ".zip")
        target = safe_path(root, release.sha256)
        if archive.exists():
            if archive.stat().st_size > MAX_ARCHIVE:
                raise ReleaseError("cache archive size exceeded")
            data = archive.read_bytes()
        else:
            data = fetch(client, release.asset_url, MAX_ARCHIVE, deadline)
        if len(data) != release.size or hashlib.sha256(data).hexdigest() != release.sha256:
            raise ReleaseError("archive size or trusted checksum mismatch")
        if not archive.exists():
            with archive.open("xb") as destination:
                destination.write(data)
        files = unpack(data, target, deadline)
        return Succeeded(
            payload=BundleIdentity(release=release, archive=archive, root=target, files=files)
        )
    except ReleaseError as error:
        return reject(str(error))
    except (httpx.HTTPError, OSError, ValueError, zipfile.BadZipFile, zlib.error, RuntimeError):
        return reject("archive acquisition, trust, safe extraction or cache verification failed")
