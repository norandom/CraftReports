"""Validated deployment selection and run-owned output namespace."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from .contracts import AbsolutePath, Origin, Positive, Sha256, Text, Value


class Bounds(Value):
    readiness: Positive = 90
    action: Positive = 20
    cleanup: Positive = 30


class OwnedDeployment(Value):
    mode: Literal["owned-wsl", "owned-linux"]
    bind_address: Literal["127.0.0.1", "0.0.0.0"] = "127.0.0.1"
    port: Annotated[int, Field(gt=0, le=65535, strict=True)] | None = None

    @field_validator("port")
    @classmethod
    def preserve_probe(cls, port: int | None) -> int | None:
        if port == 8871:
            raise ValueError("port 8871 belongs to the existing probe")
        return port


class ExternalDeployment(Value):
    mode: Literal["external"] = "external"
    origin: Origin
    build_manifest: AbsolutePath


type Deployment = Annotated[OwnedDeployment | ExternalDeployment, Field(discriminator="mode")]


class RunConfig(Value):
    run_id: UUID = Field(default_factory=uuid4)
    deployment: Deployment
    headed: Annotated[bool, Field(strict=True)] = True
    profile_id: Literal["chromium-download-fallback"] = "chromium-download-fallback"
    bounds: Bounds = Field(default_factory=Bounds)
    output_root: AbsolutePath
    trusted_release_sha256: Sha256 | None = None
    trust_source: Text | None = None
    predecessor_run: UUID | None = None

    @model_validator(mode="after")
    def paired_trust(self) -> RunConfig:
        if (self.trusted_release_sha256 is None) != (self.trust_source is None):
            raise ValueError("trusted release digest and provenance must be supplied together")
        if self.predecessor_run == self.run_id:
            raise ValueError("recovery must have a distinct run identity")
        return self

    @property
    def run_directory(self) -> Path:
        return self.output_root / str(self.run_id)

    @property
    def destination(self) -> Path:
        return self.run_directory / "output" / "result.xlsx"
