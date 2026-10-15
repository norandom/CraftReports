"""Inward snapshot reader and trusted finalization injection boundaries."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from craftreport.application.service_values import Missing, ServiceUnavailable, VersionConflict
from craftreport.contracts import JsonObject
from craftreport.data.values import Snapshot, SnapshotRef

type SnapshotFinalizer = Callable[[JsonObject, datetime, datetime], tuple[Snapshot, bytes]]


class SnapshotReader(Protocol):
    async def read(
        self, ref: SnapshotRef
    ) -> Snapshot | Missing | VersionConflict | ServiceUnavailable: ...
