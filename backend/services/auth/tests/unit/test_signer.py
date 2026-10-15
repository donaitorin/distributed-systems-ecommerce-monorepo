from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest
from auth_testing.support import AUDIENCE, ISSUER, new_signing_key, verifier_for

from auth.domain.user import Role
from auth.infra.keys import KeyStore
from auth.infra.signer import JwtAccessTokenIssuer
from ecommerce_auth import InvalidTokenError
from ecommerce_auth import Role as LibRole

NOW = datetime.now(UTC)
TTL = timedelta(minutes=15)


def unverified_claims(token: str) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(token, options={"verify_signature": False})
    return claims


EMAIL = "ada@example.com"


def issuer_for(store: KeyStore) -> JwtAccessTokenIssuer:
    return JwtAccessTokenIssuer(store, ISSUER, AUDIENCE, TTL)


async def test_tokens_verify_with_the_shared_auth_library() -> None:
    key = new_signing_key()
    store = KeyStore([key], key.kid)
    user_id = uuid4()

    token = issuer_for(store).issue(user_id, EMAIL, Role.ADMIN, NOW)

    user = await verifier_for(store.jwks_document()).verify(token.value)
    assert user.user_id == str(user_id)
    assert user.role is LibRole.ADMIN


def test_the_token_carries_the_expected_claims_and_header() -> None:
    key = new_signing_key()
    store = KeyStore([key], key.kid)

    token = issuer_for(store).issue(uuid4(), EMAIL, Role.CUSTOMER, NOW)

    claims = jwt.decode(token.value, options={"verify_signature": False})
    assert claims["iss"] == ISSUER
    assert claims["aud"] == AUDIENCE
    assert claims["role"] == "customer"
    assert claims["email"] == EMAIL
    assert claims["exp"] - claims["iat"] == int(TTL.total_seconds())
    assert claims["jti"]
    header = jwt.get_unverified_header(token.value)
    assert header == {"alg": "RS256", "typ": "JWT", "kid": key.kid}
    assert token.expires_in == int(TTL.total_seconds())


def test_every_token_has_its_own_jti() -> None:
    key = new_signing_key()
    issuer = issuer_for(KeyStore([key], key.kid))
    user_id = uuid4()

    first = jwt.decode(
        issuer.issue(user_id, EMAIL, Role.CUSTOMER, NOW).value, options={"verify_signature": False}
    )
    second = jwt.decode(
        issuer.issue(user_id, EMAIL, Role.CUSTOMER, NOW).value, options={"verify_signature": False}
    )

    assert first["jti"] != second["jti"]


async def test_during_a_rotation_tokens_from_both_keys_verify() -> None:
    old, new = new_signing_key(), new_signing_key()
    before_rotation = issuer_for(KeyStore([old], old.kid)).issue(uuid4(), EMAIL, Role.CUSTOMER, NOW)
    both = KeyStore([old, new], new.kid)
    after_rotation = issuer_for(both).issue(uuid4(), EMAIL, Role.CUSTOMER, NOW)
    verifier = verifier_for(both.jwks_document())

    assert (await verifier.verify(before_rotation.value)).role is LibRole.CUSTOMER
    assert (await verifier.verify(after_rotation.value)).role is LibRole.CUSTOMER
    assert jwt.get_unverified_header(after_rotation.value)["kid"] == new.kid


async def test_a_token_signed_by_a_removed_key_is_rejected() -> None:
    old, new = new_signing_key(), new_signing_key()
    token = issuer_for(KeyStore([old], old.kid)).issue(uuid4(), EMAIL, Role.CUSTOMER, NOW)
    verifier = verifier_for(KeyStore([new], new.kid).jwks_document())

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token.value)
