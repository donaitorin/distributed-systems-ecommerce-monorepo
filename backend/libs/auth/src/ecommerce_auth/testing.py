import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from ecommerce_auth.jwks import JwksClient
from ecommerce_auth.roles import Role
from ecommerce_auth.settings import DEFAULT_AUDIENCE, JwtSettings
from ecommerce_auth.verifier import TokenVerifier

STUB_JWKS_URL = "http://auth.test/.well-known/jwks.json"
STUB_ISSUER = "ecommerce-auth"


def stub_settings(**overrides: Any) -> JwtSettings:
    values: dict[str, Any] = {"jwks_url": STUB_JWKS_URL, "issuer": STUB_ISSUER} | overrides
    return JwtSettings(**values)


class StubTokenIssuer:
    def __init__(self, kid: str = "test-key", private_key: rsa.RSAPrivateKey | None = None) -> None:
        self.kid = kid
        self.private_key = private_key or rsa.generate_private_key(
            public_exponent=65537, key_size=2048
        )

    def jwks_document(self) -> dict[str, Any]:
        jwk = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def issue(
        self,
        subject: str | None = None,
        role: Role | str = Role.CUSTOMER,
        audience: str = DEFAULT_AUDIENCE,
        issuer: str = STUB_ISSUER,
        expires_in_seconds: float = 300,
        **extra_claims: Any,
    ) -> str:
        now = time.time()
        claims: dict[str, Any] = {
            "sub": subject if subject is not None else str(uuid4()),
            "role": str(role),
            "aud": audience,
            "iss": issuer,
            "iat": int(now),
            "exp": int(now + expires_in_seconds),
        } | extra_claims
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid})

    def issue_with_claims(self, claims: Mapping[str, Any]) -> str:
        return jwt.encode(
            dict(claims), self.private_key, algorithm="RS256", headers={"kid": self.kid}
        )


def build_stub_verifier(
    issuer: StubTokenIssuer, settings: JwtSettings | None = None
) -> TokenVerifier:
    resolved = settings or stub_settings()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=issuer.jwks_document())
    )
    jwks_client = JwksClient(resolved, httpx.AsyncClient(transport=transport))
    return TokenVerifier(resolved, jwks_client)
