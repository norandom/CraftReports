"""Injected exact publication decisions and principal-scoped queries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from craftreport.application.service_values import Missing, ServiceUnavailable
from craftreport.data.ports import SnapshotReader

if TYPE_CHECKING:
    from craftreport.runtime.publication import LatestRequest, LatestSelection, PublicationDecision


class PublicationDecisionReader(Protocol):
    async def read_decision(
        self, operation_id: str
    ) -> PublicationDecision | Missing | ServiceUnavailable: ...


class SnapshotQueries(SnapshotReader, Protocol):
    async def latest(
        self, request: LatestRequest
    ) -> LatestSelection | Missing | ServiceUnavailable: ...
