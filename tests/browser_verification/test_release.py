"""Real ZIP and HTTPX boundary payloads exercise release acquisition."""

import hashlib
import io
import json
import stat
import time
import zipfile
from pathlib import Path

import httpx
import pytest

from scripts.browser_verification import release
from scripts.browser_verification.config import OwnedDeployment, RunConfig
from scripts.browser_verification.contracts import Rejected, Succeeded


def archive() -> bytes:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as zipped:
        for name in ("index.html", "app.js", "app_bg.wasm"):
            zipped.writestr(name, b"synthetic official payload")
    return target.getvalue()


def test_acquire_latest(tmp_path: Path) -> None:
    payload = archive()
    digest = hashlib.sha256(payload).hexdigest()
    metadata = {
        "tag_name": "v0.7.0",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-14T15:36:59Z",
        "html_url": "https://github.com/storytold/gridcraft/releases/tag/v0.7.0",
        "assets": [
            {
                "id": 123,
                "name": "gridcraft-web-0.7.0.zip",
                "size": len(payload),
                "digest": "sha256:" + digest,
                "browser_download_url": "https://github.com/storytold/gridcraft/releases/download/v0.7.0/gridcraft-web-0.7.0.zip",
            }
        ],
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, json=metadata)
            if request.url.path.endswith("latest")
            else httpx.Response(200, content=payload)
        )

    config = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        selected = release.resolve_release(config, client=client)
        assert isinstance(selected, Succeeded)
        acquired = release.acquire(selected.payload, tmp_path / "cache", client=client)
    assert isinstance(acquired, Succeeded)
    assert acquired.payload.release.sha256 == digest
    assert len(acquired.payload.files) == 3


def selected(tmp_path: Path, payload: bytes) -> release.ReleaseIdentity:
    return release.ReleaseIdentity(
        version="0.7.0",
        release_url=release.PUBLIC + "tag/v0.7.0",
        acquired_at=release.datetime.now(release.UTC),
        published_at=release.datetime.now(release.UTC),
        asset_id=123,
        asset_name="gridcraft-web-0.7.0.zip",
        asset_url=release.PUBLIC + "download/v0.7.0/gridcraft-web-0.7.0.zip",
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        trust_source=release.LATEST,
        bound=10,
    )


def metadata(
    payload: bytes,
    *,
    tag: str = "v0.7.0",
    count: int = 1,
    digest: str | None = "auto",
    stable: bool = True,
) -> bytes:
    version = tag.removeprefix("v")
    asset = {
        "id": 123,
        "name": f"gridcraft-web-{version}.zip",
        "size": len(payload),
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest() if digest == "auto" else digest,
        "browser_download_url": release.PUBLIC + f"download/{tag}/gridcraft-web-{version}.zip",
    }
    return json.dumps(
        {
            "tag_name": tag,
            "draft": False,
            "prerelease": not stable,
            "published_at": "2026-10-14T15:36:59Z",
            "html_url": release.PUBLIC + "tag/" + tag,
            "assets": [asset] * count,
        }
    ).encode("utf-8")


@pytest.mark.parametrize(
    "tag,count,digest,stable,reason",
    [
        ("v0.6.0", 1, "auto", True, "older"),
        ("garbage", 1, "auto", True, "metadata"),
        ("v0.7.0", 0, "auto", True, "unique"),
        ("v0.7.0", 2, "auto", True, "unique"),
        ("v0.7.0", 1, None, True, "trusted"),
        ("v0.7.0", 1, "md5:bad", True, "invalid"),
        ("v0.7.0", 1, "auto", False, "stable"),
        ("v0.7.1rc1", 1, "auto", True, "stable"),
    ],
)
def test_rejected_metadata(
    tmp_path: Path, tag: str, count: int, digest: str | None, stable: bool, reason: str
) -> None:
    data = metadata(archive(), tag=tag, count=count, digest=digest, stable=stable)
    config = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=data))
    ) as client:
        outcome = release.resolve_release(config, client=client)
    assert isinstance(outcome, Rejected)
    assert reason in outcome.finding.observed[0]


def test_independent_configured_trust(tmp_path: Path) -> None:
    payload = archive()
    config = RunConfig(
        deployment=OwnedDeployment(mode="owned-linux"),
        output_root=tmp_path,
        trusted_release_sha256=hashlib.sha256(payload).hexdigest(),
        trust_source="operator independently verified publisher record",
    )
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=metadata(payload, digest=None))
        )
    ) as client:
        assert isinstance(release.resolve_release(config, client=client), Succeeded)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=metadata(payload, digest="sha256:" + "a" * 64))
        )
    ) as client:
        assert isinstance(release.resolve_release(config, client=client), Rejected)


@pytest.mark.parametrize("fault", ["http", "timeout", "raw-metadata"])
def test_lookup_failure_never_returns_cache(tmp_path: Path, fault: str) -> None:
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if fault == "timeout":
            raise httpx.ReadTimeout("secret credential rawpayload", request=request)
        return httpx.Response(
            503 if fault == "http" else 200, content=b"secret credential rawpayload"
        )

    config = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    (tmp_path / "older.zip").write_bytes(archive())
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        outcome = release.resolve_release(config, client=client)
    assert isinstance(outcome, Rejected)
    assert "secret" not in outcome.model_dump_json()
    assert requests == [release.LATEST] * (1 if fault == "raw-metadata" else 2)


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        "C:/escape",
        "a\\b",
        "a/./b",
        "a//b",
        "CON",
        "file.",
        "file ",
        "x:y",
        "//server/x",
    ],
)
def test_unsafe_zip_paths(tmp_path: Path, name: str) -> None:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as zipped:
        info = zipfile.ZipInfo("placeholder")
        info.filename = name
        zipped.writestr(info, b"unsafe")
    payload = target.getvalue()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        result = release.acquire(selected(tmp_path, payload), tmp_path / "cache", client=client)
    assert isinstance(result, Rejected)
    assert "unsafe" in result.finding.observed[0]


@pytest.mark.parametrize("mode", ["alias", "duplicate", "symlink", "missing", "not-zip"])
def test_unsafe_or_incomplete_archive(tmp_path: Path, mode: str) -> None:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w") as zipped:
        zipped.writestr("index.html", b"html")
        if mode == "alias":
            zipped.writestr("INDEX.html", b"alias")
        if mode == "duplicate":
            with pytest.warns(UserWarning):
                zipped.writestr("index.html", b"duplicate")
        if mode == "symlink":
            info = zipfile.ZipInfo("link")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zipped.writestr(info, b"../outside")
    payload = b"not a ZIP" if mode == "not-zip" else target.getvalue()
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        assert isinstance(
            release.acquire(selected(tmp_path, payload), tmp_path / "cache", client=client),
            Rejected,
        )


@pytest.mark.parametrize("corruption", ["archive", "file", "extra"])
def test_cache_reverified_without_redownload(tmp_path: Path, corruption: str) -> None:
    payload = archive()
    identity = selected(tmp_path, payload)
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        first = release.acquire(identity, tmp_path / "cache", client=client)
        assert isinstance(first, Succeeded)
        assert isinstance(release.acquire(identity, tmp_path / "cache", client=client), Succeeded)
        if corruption == "archive":
            first.payload.archive.write_bytes(b"corrupt")
        else:
            (first.payload.root / ("index.html" if corruption == "file" else "extra")).write_bytes(
                b"corrupt"
            )
        assert isinstance(release.acquire(identity, tmp_path / "cache", client=client), Rejected)
    assert len(calls) == 1


def test_bounds_and_corrupt_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = archive()
    identity = selected(tmp_path, payload)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"corrupt"))
    ) as client:
        assert isinstance(release.acquire(identity, tmp_path / "bad", client=client), Rejected)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        for key in ("MAX_ARCHIVE", "MAX_MEMBERS", "MAX_EXPANDED"):
            with monkeypatch.context() as patch:
                patch.setattr(release, key, 1)
                assert isinstance(
                    release.acquire(identity, tmp_path / key, client=client), Rejected
                )
    with pytest.raises(release.ReleaseError, match="deadline"):
        release.remaining(time.monotonic() - 1)


def test_transient_network_retry_is_read_only(tmp_path: Path) -> None:
    payload = archive()
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(503 if len(calls) == 1 else 200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        result = release.acquire(selected(tmp_path, payload), tmp_path / "cache", client=client)
    assert isinstance(result, Succeeded)
    assert calls == ["GET", "GET"]


def test_fetch_total_deadline(tmp_path: Path) -> None:
    class DelayedStream(httpx.SyncByteStream):
        def __iter__(self):
            time.sleep(0.02)
            yield b"late"

    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=DelayedStream()))
    ) as client:
        with pytest.raises(release.ReleaseError, match="deadline"):
            release.fetch(client, release.LATEST, 100, time.monotonic() + 0.001)


def test_official_url_identity_and_metadata_limits(tmp_path: Path) -> None:
    config = RunConfig(deployment=OwnedDeployment(mode="owned-linux"), output_root=tmp_path)
    data = metadata(archive()).replace(
        b"https://github.com/", b"https://secret:credential@evil.invalid/"
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=data))
    ) as client:
        result = release.resolve_release(config, client=client)
    assert isinstance(result, Rejected)
    assert "identity" in result.finding.observed[0]
    assert "secret" not in result.model_dump_json()


def test_trusted_archive_with_malformed_deflate_is_rejected(tmp_path: Path) -> None:
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("index.html", b"synthetic compressed application")
    corrupted = bytearray(target.getvalue())
    # Local header is 30 bytes followed by filename and extra fields. BTYPE=3
    # is reserved, so this first compressed byte must fail actual decompression.
    filename_size = int.from_bytes(corrupted[26:28], "little")
    extra_size = int.from_bytes(corrupted[28:30], "little")
    corrupted[30 + filename_size + extra_size] = 7
    payload = bytes(corrupted)
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        result = release.acquire(selected(tmp_path, payload), tmp_path / "cache", client=client)
    assert isinstance(result, Rejected)
    assert result.finding.stage == "release"
    assert result.finding.status == "blocked"
    assert "invalid block type" not in result.model_dump_json()
