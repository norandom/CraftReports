"""Immediate acquisition ownership foundation; runtime orchestration follows later."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from .contracts import Text, Value

ResourceKind = Literal["deployment", "process", "driver", "browser", "context", "connection"]
CloseState = Literal["pending", "graceful", "forced", "failed"]


class ResourceToken(Value):
    token_id: UUID
    kind: ResourceKind
    owner_run: UUID
    identity: Text
    acquisition: Literal["partial", "acquired"] = "partial"
    close_state: CloseState = "pending"


class ResourceRegistry:
    def __init__(self, run_id: UUID) -> None:
        self.run_id = run_id
        self._tokens: dict[UUID, ResourceToken] = {}
        self._cancel_requested = False

    def register(self, kind: ResourceKind, identity: str) -> ResourceToken:
        """Call immediately on acquisition, before any setup or readiness await."""
        token = ResourceToken(token_id=uuid4(), kind=kind, owner_run=self.run_id, identity=identity)
        if any(item.kind == kind and item.identity == token.identity for item in self.tokens):
            raise ValueError("resource is already registered")
        self._tokens[token.token_id] = token
        return token

    @property
    def tokens(self) -> tuple[ResourceToken, ...]:
        return tuple(self._tokens.values())

    @property
    def pending_cleanup(self) -> tuple[ResourceToken, ...]:
        return tuple(
            item for item in reversed(self.tokens) if item.close_state in ("pending", "failed")
        )

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested

    def request_cancel(self) -> None:
        """Retain supported cancellation intent without discarding late acquisitions."""
        self._cancel_requested = True

    def mark_acquired(self, token_id: UUID) -> ResourceToken:
        token = self._tokens[token_id]
        if token.close_state != "pending":
            raise ValueError("closed or cleanup-attempted resource cannot become acquired")
        updated = ResourceToken.model_validate(token.model_dump() | {"acquisition": "acquired"})
        self._tokens[token_id] = updated
        return updated

    def record_close(
        self, token_id: UUID, state: Literal["graceful", "forced", "failed"]
    ) -> ResourceToken:
        token = self._tokens[token_id]
        if token.close_state in ("graceful", "forced"):
            raise ValueError("resource close is already finalized")
        updated = ResourceToken.model_validate(token.model_dump() | {"close_state": state})
        self._tokens[token_id] = updated
        return updated
