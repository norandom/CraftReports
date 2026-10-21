"""Fixed workbook candidate values; no live or export capability is registered."""

from craftreport_gridcraft.app_values import (
    AppSettings,
    ArtifactRef,
    BrowserTarget,
    SavedCandidate,
    StagedArtifact,
    TargetObservation,
)
from craftreport_gridcraft.codecs import support_descriptor
from craftreport_gridcraft.values import PROFILE, AppIssue, MappingPlan, OwnedLayout

__all__ = [
    "PROFILE",
    "AppIssue",
    "MappingPlan",
    "OwnedLayout",
    "AppSettings",
    "BrowserTarget",
    "TargetObservation",
    "SavedCandidate",
    "StagedArtifact",
    "ArtifactRef",
    "support_descriptor",
]
