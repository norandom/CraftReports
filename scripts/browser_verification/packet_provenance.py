"""Typed retained release records and frozen external provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from .contracts import ContentIdentity, Outcome, Succeeded
from .release import BundleIdentity, ReleaseIdentity

if TYPE_CHECKING:
    from .packet import PacketInputs


def verify_provenance(inputs: PacketInputs) -> None:
    directory = inputs.config.run_directory
    bundle = TypeAdapter(Outcome[BundleIdentity]).validate_json(
        (directory / "bundle.json").read_bytes()
    )
    release = TypeAdapter(Outcome[ReleaseIdentity]).validate_json(
        (directory / "release.json").read_bytes()
    )
    if not isinstance(bundle, Succeeded) or not isinstance(release, Succeeded):
        raise ValueError("missing-release-provenance")
    identity = bundle.payload
    if (
        identity.release != release.payload
        or identity.release.sha256 != inputs.deployment.build_sha256
    ):
        raise ValueError("release-build-mismatch")
    if inputs.config.trusted_release_sha256 not in (None, identity.release.sha256):
        raise ValueError("configured-release-mismatch")
    required = [ContentIdentity(path=str(identity.archive), sha256=identity.release.sha256)]
    for member in identity.files:
        path = (identity.root / member.path).resolve()
        if not path.is_relative_to(identity.root.resolve()):
            raise ValueError("foreign-bundle-member")
        required.append(ContentIdentity(path=str(path), sha256=member.sha256))
    selection = inputs.config.deployment
    if selection.mode == "external":
        from .packet import hash_content

        manifest = BundleIdentity.model_validate_json(selection.build_manifest.read_bytes())
        if (
            manifest.release != identity.release
            or manifest.files != identity.files
            or selection.origin != inputs.deployment.origin
        ):
            raise ValueError("external-build-mismatch")
        required.append(hash_content(selection.build_manifest))
    if not identity.files or any(item not in inputs.source_content for item in required):
        raise ValueError("unfrozen-release-provenance")
