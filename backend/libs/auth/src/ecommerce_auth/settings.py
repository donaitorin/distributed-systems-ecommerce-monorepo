from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

DEFAULT_AUDIENCE = "ecommerce-api"
DEFAULT_KEYS_CACHE_TTL_SECONDS = 300.0


@dataclass(frozen=True, slots=True)
class JwtSettings:
    jwks_url: str
    issuer: str
    audience: str = DEFAULT_AUDIENCE
    keys_cache_ttl_seconds: float = DEFAULT_KEYS_CACHE_TTL_SECONDS
    keys_refetch_cooldown_seconds: float = 30.0
    request_timeout_seconds: float = 3.0
    leeway_seconds: float = 5.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            jwks_url=environ["JWT_JWKS_URL"],
            issuer=environ["JWT_ISSUER"],
            audience=environ.get("JWT_AUDIENCE", DEFAULT_AUDIENCE),
            keys_cache_ttl_seconds=float(
                environ.get("JWT_JWKS_CACHE_TTL_SECONDS", DEFAULT_KEYS_CACHE_TTL_SECONDS)
            ),
        )
