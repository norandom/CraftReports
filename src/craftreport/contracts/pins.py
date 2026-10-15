"""One generic version pin shared by runtime and reporting consumers."""

import re
from dataclasses import dataclass

from craftreport.contracts.values import require_text


@dataclass(frozen=True, slots=True)
class VersionPin:
    identity: str
    version: str
    content_digest: str

    def __post_init__(self) -> None:
        if type(self.identity) is not str or type(self.version) is not str:
            raise ValueError("identity and version must be text")
        require_text(self.identity, "identity")
        require_text(self.version, "version")
        if (
            type(self.content_digest) is not str
            or re.fullmatch("[0-9a-f]{64}", self.content_digest) is None
        ):
            raise ValueError("content_digest must be lowercase SHA-256 hex")
