from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt

from ecommerce_auth.errors import InvalidTokenError
from ecommerce_auth.jwks import JwksClient, SigningKeyProvider
from ecommerce_auth.roles import Role
from ecommerce_auth.settings import JwtSettings

ALGORITHM = "RS256"


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    user_id: str
    role: Role
    email: str | None = None
    issued_at: datetime | None = None


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _issued_at(value: object) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, UTC)


class TokenVerifier:
    def __init__(self, settings: JwtSettings, jwks_client: SigningKeyProvider) -> None:
        self._settings = settings
        self._jwks_client = jwks_client

    async def verify(self, token: str) -> AuthenticatedUser:
        try:
            claims = await self._decode(token)
            return AuthenticatedUser(
                user_id=claims["sub"],
                role=Role(claims["role"]),
                email=_optional_text(claims.get("email")),
                issued_at=_issued_at(claims.get("iat")),
            )
        except (jwt.PyJWTError, ValueError, KeyError) as error:
            raise InvalidTokenError("The access token is invalid or expired") from error

    async def _decode(self, token: str) -> dict[str, Any]:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != ALGORITHM:
            raise jwt.InvalidAlgorithmError("unsupported algorithm")
        key = await self._jwks_client.get_key(header["kid"])
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            audience=self._settings.audience,
            issuer=self._settings.issuer,
            leeway=self._settings.leeway_seconds,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        return claims


@dataclass(slots=True)
class ManagedTokenVerifier:
    verifier: TokenVerifier
    http_client: httpx.AsyncClient

    async def aclose(self) -> None:
        await self.http_client.aclose()


def create_token_verifier(settings: JwtSettings) -> ManagedTokenVerifier:
    http_client = httpx.AsyncClient()
    verifier = TokenVerifier(settings, JwksClient(settings, http_client))
    return ManagedTokenVerifier(verifier=verifier, http_client=http_client)
