"""Fixed workbook candidate values; no live or export capability is registered."""

from craftreport_gridcraft.app_values import (
    AppSettings,
    ArtifactRef,
    BrowserTarget,
    SavedCandidate,
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
    "ArtifactRef",
    "support_descriptor",
]
