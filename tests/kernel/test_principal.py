"""Trusted identity, secret handling and startup-policy boundary evidence."""

import asyncio
from dataclasses import FrozenInstanceError

import pytest
from starlette.requests import Request
from starlette.types import Message

from craftreport.application.ports import (
    AccessAction,
    AccessAllowed,
    AccessDecision,
    AccessDenied,
    CatalogAccess,
)
from craftreport.contracts import Principal
from craftreport.interfaces.principal import (
    AuthenticatedIdentity,
    AuthenticationRejected,
    PrincipalBoundary,
)

ALICE = AuthenticatedIdentity("alice", frozenset({"read"}))
BOB = AuthenticatedIdentity("bob", frozenset({"write"}))


class Policy:
    async def authorize(self, principal: Principal, action: AccessAction) -> AccessDecision:
        return AccessAllowed() if "read" in principal.permitted_scopes else AccessDenied()


class Verifier:
    async def authenticate(self, bearer_token: str) -> AuthenticatedIdentity | None:
        return ALICE if bearer_token == "valid" else None


def request(*headers: tuple[str, str]) -> Request:
    return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers]})


def test_generated_credentials_resolve_two_separate_immutable_scopes() -> None:
    boundary, credentials = PrincipalBoundary.conformance(
        "127.0.0.1", "test-deployment", (ALICE, BOB), Policy()
    )
    for credential in credentials:
        principal = asyncio.run(
            boundary.resolve(request(("authorization", f"Bearer {credential.token}")))
        )
        assert principal == Principal(
            "test-deployment", credential.identity.subject, credential.identity.permitted_scopes
        )
        with pytest.raises(FrozenInstanceError):
            setattr(principal, "subject", "mallory")
        assert credential.token not in repr(credential)
    assert credentials[0].token != credentials[1].token
    _, fresh = PrincipalBoundary.conformance("127.0.0.1", "test-deployment", (ALICE,), Policy())
    assert fresh[0].token not in {item.token for item in credentials}
    with pytest.raises(AuthenticationRejected):
        asyncio.run(boundary.resolve(request(("authorization", f"Bearer {fresh[0].token}"))))


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "::1", "localhost", "192.168.1.2", "127.0.0.2"])
def test_conformance_refuses_every_bind_except_exact_ipv4_loopback(host: str) -> None:
    with pytest.raises(ValueError, match="127.0.0.1"):
        PrincipalBoundary.conformance(host, "deployment", (ALICE,), Policy())


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Bearer",
        "Basic valid",
        "Bearer invalid",
        "Bearer valid extra",
        "Bearer valid,other",
        "Bearer válid",
    ],
)
def test_missing_invalid_or_malformed_credentials_are_safe_denials(
    authorization: str | None,
) -> None:
    boundary = PrincipalBoundary("production", Verifier(), Policy())
    headers = () if authorization is None else (("authorization", authorization),)
    with pytest.raises(AuthenticationRejected, match="^Authentication required$"):
        asyncio.run(boundary.resolve(request(*headers)))


def test_production_requires_both_providers_and_defaults_to_deny() -> None:
    for boundary in (
        PrincipalBoundary("production"),
        PrincipalBoundary("production", Verifier()),
        PrincipalBoundary("production", policy=Policy()),
    ):
        with pytest.raises(AuthenticationRejected):
            asyncio.run(boundary.resolve(request(("authorization", "Bearer valid"))))
    boundary = PrincipalBoundary("production")
    assert isinstance(
        asyncio.run(
            boundary.access_policy.authorize(
                Principal("production", "alice", frozenset()), CatalogAccess()
            )
        ),
        AccessDenied,
    )


def test_payload_forwarding_and_ai_origin_cannot_supply_authority() -> None:
    boundary = PrincipalBoundary("server-deployment", Verifier(), Policy())
    spoofed = request(
        ("authorization", "bEaReR valid"),
        ("x-forwarded-user", "bob"),
        ("x-principal", "bob"),
        ("x-deployment-scope", "stolen"),
        ("x-permitted-scopes", "admin"),
        ("x-ai-origin", "true"),
    )
    spoofed.scope["query_string"] = b"subject=bob&deployment_scope=stolen"
    spoofed.scope["identity"] = {"subject": "bob", "permitted_scopes": ["admin"]}

    async def receive() -> Message:
        return {
            "type": "http.request",
            "body": (
                b'{"principal":{"subject":"bob","deployment_scope":"stolen",'
                b'"permitted_scopes":["admin"]}}'
            ),
        }

    spoofed = Request(spoofed.scope, receive)
    principal = asyncio.run(boundary.resolve(spoofed))
    assert principal == Principal("server-deployment", "alice", frozenset({"read"}))
    assert boundary.access_policy is boundary.policy
    with pytest.raises(AuthenticationRejected):
        asyncio.run(
            boundary.resolve(
                request(
                    ("x-forwarded-user", "alice"), ("x-forwarded-authorization", "Bearer valid")
                )
            )
        )


def test_duplicate_authorization_headers_fail_closed() -> None:
    boundary = PrincipalBoundary("production", Verifier(), Policy())
    with pytest.raises(AuthenticationRejected):
        asyncio.run(
            boundary.resolve(
                request(("authorization", "Bearer valid"), ("authorization", "Bearer valid"))
            )
        )


def test_authenticator_failure_does_not_disclose_secrets() -> None:
    class BrokenVerifier:
        async def authenticate(self, bearer_token: str) -> AuthenticatedIdentity | None:
            raise RuntimeError(f"private configuration: {bearer_token}")

    boundary = PrincipalBoundary("production", BrokenVerifier(), Policy())
    with pytest.raises(AuthenticationRejected) as caught:
        asyncio.run(boundary.resolve(request(("authorization", "Bearer secret"))))
    assert str(caught.value) == "Authentication required"
    assert caught.value.__suppress_context__


def test_conformance_binding_is_rechecked_at_server_startup() -> None:
    boundary, _ = PrincipalBoundary.conformance("127.0.0.1", "test", (ALICE,), Policy())
    boundary.validate_bind("127.0.0.1")
    with pytest.raises(ValueError, match="127.0.0.1"):
        boundary.validate_bind("0.0.0.0")
    PrincipalBoundary("production", Verifier(), Policy()).validate_bind("0.0.0.0")


@pytest.mark.parametrize("identities", [(), (ALICE, ALICE)])
def test_conformance_configuration_rejects_empty_or_duplicate_subjects(
    identities: tuple[AuthenticatedIdentity, ...],
) -> None:
    with pytest.raises(ValueError, match="distinct nonempty subjects"):
        PrincipalBoundary.conformance("127.0.0.1", "test", identities, Policy())
