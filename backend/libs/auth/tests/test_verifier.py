import time
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from ecommerce_auth import (
    DEFAULT_AUDIENCE,
    InvalidTokenError,
    JwksClient,
    KeysUnavailableError,
    Role,
    TokenVerifier,
    create_token_verifier,
)
from ecommerce_auth.testing import STUB_ISSUER, StubTokenIssuer, build_stub_verifier, stub_settings


@pytest.fixture
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def verifier(issuer: StubTokenIssuer) -> TokenVerifier:
    return build_stub_verifier(issuer)


@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.ADMIN])
async def test_valid_token_yields_the_authenticated_user(
    issuer: StubTokenIssuer, verifier: TokenVerifier, role: Role
) -> None:
    token = issuer.issue(subject="user-1", role=role)

    user = await verifier.verify(token)

    assert (user.user_id, user.role) == ("user-1", role)


async def test_the_user_carries_the_email_and_issue_time_claims(
    issuer: StubTokenIssuer, verifier: TokenVerifier
) -> None:
    user = await verifier.verify(
        issuer.issue(subject="user-1", email="ada@example.com", iat=1_700_000_000)
    )

    assert user.email == "ada@example.com"
    assert user.issued_at == datetime.fromtimestamp(1_700_000_000, UTC)


@pytest.mark.parametrize("email", [None, "", 7])
async def test_a_missing_or_malformed_email_claim_reads_as_none(
    issuer: StubTokenIssuer, verifier: TokenVerifier, email: object
) -> None:
    user = await verifier.verify(issuer.issue(email=email))

    assert user.email is None


async def test_a_token_without_an_issue_time_still_verifies(
    issuer: StubTokenIssuer, verifier: TokenVerifier
) -> None:
    now = int(time.time())
    token = issuer.issue_with_claims(
        {
            "sub": "user-1",
            "role": "customer",
            "aud": DEFAULT_AUDIENCE,
            "iss": STUB_ISSUER,
            "exp": now + 60,
        }
    )

    user = await verifier.verify(token)

    assert user.issued_at is None


async def test_a_boolean_issue_time_is_ignored(
    issuer: StubTokenIssuer, verifier: TokenVerifier
) -> None:
    user = await verifier.verify(issuer.issue(iat=True))

    assert user.issued_at is None


async def test_expired_token_is_rejected(issuer: StubTokenIssuer, verifier: TokenVerifier) -> None:
    token = issuer.issue(expires_in_seconds=-60)

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_token_within_the_leeway_is_accepted(issuer: StubTokenIssuer) -> None:
    verifier = build_stub_verifier(issuer, stub_settings(leeway_seconds=30))

    user = await verifier.verify(issuer.issue(expires_in_seconds=-10))

    assert user.role is Role.CUSTOMER


async def test_wrong_audience_is_rejected(issuer: StubTokenIssuer, verifier: TokenVerifier) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(issuer.issue(audience="another-api"))


async def test_missing_audience_is_rejected(
    issuer: StubTokenIssuer, verifier: TokenVerifier
) -> None:
    now = int(time.time())
    token = issuer.issue_with_claims(
        {"sub": "u", "role": "customer", "iss": STUB_ISSUER, "exp": now + 300}
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_configured_audience_is_enforced(issuer: StubTokenIssuer) -> None:
    verifier = build_stub_verifier(issuer, stub_settings(audience="custom-api"))

    assert (await verifier.verify(issuer.issue(audience="custom-api"))).role is Role.CUSTOMER
    with pytest.raises(InvalidTokenError):
        await verifier.verify(issuer.issue(audience=DEFAULT_AUDIENCE))


async def test_wrong_issuer_is_rejected(issuer: StubTokenIssuer, verifier: TokenVerifier) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(issuer.issue(issuer="someone-else"))


@pytest.mark.parametrize("missing", ["sub", "exp", "iss", "aud", "role"])
async def test_token_missing_a_required_claim_is_rejected(
    issuer: StubTokenIssuer, verifier: TokenVerifier, missing: str
) -> None:
    claims = {
        "sub": "u",
        "role": "customer",
        "iss": STUB_ISSUER,
        "aud": DEFAULT_AUDIENCE,
        "exp": int(time.time()) + 300,
    }
    del claims[missing]

    with pytest.raises(InvalidTokenError):
        await verifier.verify(issuer.issue_with_claims(claims))


@pytest.mark.parametrize("role", ["superuser", "", "ADMIN"])
async def test_unknown_role_is_rejected(
    issuer: StubTokenIssuer, verifier: TokenVerifier, role: str
) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(issuer.issue(role=role))


async def test_token_signed_by_another_key_is_rejected(verifier: TokenVerifier) -> None:
    attacker = StubTokenIssuer()

    with pytest.raises(InvalidTokenError):
        await verifier.verify(attacker.issue())


async def test_token_with_unknown_kid_is_rejected(verifier: TokenVerifier) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(StubTokenIssuer("unknown-kid").issue())


async def test_symmetric_algorithm_is_rejected(verifier: TokenVerifier) -> None:
    token = jwt.encode(
        {
            "sub": "u",
            "role": "admin",
            "iss": STUB_ISSUER,
            "aud": DEFAULT_AUDIENCE,
            "exp": 9999999999,
        },
        "x" * 32,
        algorithm="HS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_unsigned_token_is_rejected(verifier: TokenVerifier) -> None:
    token = jwt.encode(
        {
            "sub": "u",
            "role": "admin",
            "iss": STUB_ISSUER,
            "aud": DEFAULT_AUDIENCE,
            "exp": 9999999999,
        },
        "",
        algorithm="none",
        headers={"kid": "test-key"},
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_token_without_kid_is_rejected(
    issuer: StubTokenIssuer, verifier: TokenVerifier
) -> None:
    token = jwt.encode(
        {
            "sub": "u",
            "role": "admin",
            "iss": STUB_ISSUER,
            "aud": DEFAULT_AUDIENCE,
            "exp": 9999999999,
        },
        issuer.private_key,
        algorithm="RS256",
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
async def test_malformed_token_is_rejected(verifier: TokenVerifier, token: str) -> None:
    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_unavailable_keys_surface_as_keys_unavailable() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    settings = stub_settings()
    verifier = TokenVerifier(settings, JwksClient(settings, httpx.AsyncClient(transport=transport)))

    with pytest.raises(KeysUnavailableError):
        await verifier.verify(StubTokenIssuer().issue())


async def test_managed_verifier_closes_its_http_client() -> None:
    managed = create_token_verifier(stub_settings())

    await managed.aclose()

    assert managed.http_client.is_closed


class InMemoryKeys:
    def __init__(self, issuer: StubTokenIssuer) -> None:
        self._issuer = issuer

    async def get_key(self, kid: str) -> RSAPublicKey:
        if kid != self._issuer.kid:
            raise jwt.InvalidKeyError(f"unknown signing key: {kid}")
        return self._issuer.private_key.public_key()


async def test_any_key_provider_can_back_the_verifier(issuer: StubTokenIssuer) -> None:
    verifier = TokenVerifier(stub_settings(), InMemoryKeys(issuer))

    user = await verifier.verify(issuer.issue(subject="user-1", role=Role.ADMIN))

    assert (user.user_id, user.role) == ("user-1", Role.ADMIN)


async def test_a_key_provider_that_does_not_know_the_kid_rejects_the_token() -> None:
    verifier = TokenVerifier(stub_settings(), InMemoryKeys(StubTokenIssuer(kid="other")))

    with pytest.raises(InvalidTokenError):
        await verifier.verify(StubTokenIssuer().issue())
