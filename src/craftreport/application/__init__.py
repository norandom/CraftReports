"""Framework-independent execution ports and application services."""

from craftreport.application.ports import CommandContext, Facade, ReadContext
from craftreport.application.registry import ImmutableOperationRegistry, OperationBinding

__all__ = [
    "CommandContext",
    "Facade",
    "ImmutableOperationRegistry",
    "OperationBinding",
    "ReadContext",
]
