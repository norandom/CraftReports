"""Compatibility boundary; report capability activation belongs to task 8."""

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from craftreport.contracts.identity import CapabilityRequirement, CapabilityVersion


def is_compatible(version: CapabilityVersion, requirement: CapabilityRequirement) -> bool:
    try:
        return version.identity == requirement.identity and Version(
            version.version
        ) in SpecifierSet(requirement.version_range)
    except (InvalidVersion, InvalidSpecifier):
        return False
