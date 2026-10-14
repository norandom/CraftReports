"""Shared HTTP authentication boundary for REST and Streamable HTTP MCP."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from typing import Protocol

from starlette.requests import Request

from craftreport.application.ports import AccessAction, AccessDecision, AccessDenied, AccessPolicy
from craftreport.contracts import Principal
from craftreport.contracts.values import require_text


@dataclass(frozen=True, slots=True)
class AuthenticatedIdentity:
    """Verified provider output, never constructed from caller identity fields."""

    subject: str
    permitted_scopes: frozenset[str]

    def __post_init__(self) -> None:
        require_text(self.subject, "subject")
        object.__setattr__(self, "permitted_scopes", frozenset(self.permitted_scopes))
        for scope in self.permitted_scopes:
            require_text(scope, "permitted scope")


class Authenticator(Protocol):
    """Deployment-supplied verifier; invalid credentials return None."""

    async def authenticate(self, bearer_token: str) -> AuthenticatedIdentity | None: ...


class AuthenticationRejected(Exception):
    """Safe boundary failure; interfaces map this to unauthenticated responses."""

    def __init__(self) -> None:
        super().__init__("Authentication required")


class DenyAccess:
    """Default policy never grants any operation, discovery or receipt access."""

    async def authorize(self, principal: Principal, action: AccessAction) -> AccessDecision:
        return AccessDenied()


@dataclass(frozen=True, slots=True)
class TestCredential:
    """Ephemeral secret delivered only to the owned conformance client."""

    __test__ = False
    identity: AuthenticatedIdentity
    token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class _ConformanceAuthenticator:
    credentials: tuple[TestCredential, ...] = field(repr=False)

    async def authenticate(self, bearer_token: str) -> AuthenticatedIdentity | None:
        for credential in self.credentials:
            if secrets.compare_digest(credential.token, bearer_token):
                return credential.identity
        return None


@dataclass(frozen=True, slots=True)
class PrincipalBoundary:
    """Composition wires access_policy into the shared Facade guards.

    No request body, query, forwarding header or AI-origin marker establishes
    identity. Production needs both verification and authorization providers.
    """

    deployment_scope: str
    authenticator: Authenticator | None = field(default=None, repr=False)
    policy: AccessPolicy | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require_text(self.deployment_scope, "deployment scope")

    @property
    def access_policy(self) -> AccessPolicy:
        return self.policy if self.policy is not None else DenyAccess()

    def validate_bind(self, bind_host: str) -> None:
        """Server startup must check its actual bind before opening a listener."""
        if isinstance(self.authenticator, _ConformanceAuthenticator) and bind_host != "127.0.0.1":
            raise ValueError("Conformance authentication requires binding only 127.0.0.1")

    async def resolve(self, request: Request) -> Principal:
        if self.authenticator is None or self.policy is None:
            raise AuthenticationRejected()
        headers = request.headers.getlist("authorization")
        if len(headers) != 1:
            raise AuthenticationRejected()
        match = re.fullmatch(r"(?i:Bearer) +([A-Za-z0-9._~+/-]+=*)", headers[0])
        if match is None:
            raise AuthenticationRejected()
        try:
            identity = await self.authenticator.authenticate(match[1])
            if not isinstance(identity, AuthenticatedIdentity):
                raise AuthenticationRejected()
            return Principal(self.deployment_scope, identity.subject, identity.permitted_scopes)
        except Exception:
            # Neither credentials nor provider diagnostics cross the HTTP boundary.
            raise AuthenticationRejected() from None

    @classmethod
    def conformance(
        cls,
        bind_host: str,
        deployment_scope: str,
        identities: tuple[AuthenticatedIdentity, ...],
        policy: AccessPolicy,
    ) -> tuple[PrincipalBoundary, tuple[TestCredential, ...]]:
        if bind_host != "127.0.0.1":
            raise ValueError("Conformance authentication requires binding only 127.0.0.1")
        if not identities or len({identity.subject for identity in identities}) != len(identities):
            raise ValueError("Conformance identities must have distinct nonempty subjects")
        credentials = tuple(
            TestCredential(identity, secrets.token_urlsafe(32)) for identity in identities
        )
        boundary = cls(deployment_scope, _ConformanceAuthenticator(credentials), policy)
        boundary.validate_bind(bind_host)
        return boundary, credentials
