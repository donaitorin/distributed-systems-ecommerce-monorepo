from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Self

from ecommerce_auth import JwtSettings

DEFAULT_REDIS_PORT: Final = 6379
DEFAULT_CATALOG_BASE_URL: Final = "http://catalog:8000"
DEFAULT_CATALOG_TIMEOUT_SECONDS: Final = 2.0
DEFAULT_MEDIA_PUBLIC_BASE_URL: Final = "/media"
CART_TTL_SECONDS: Final = 30 * 24 * 3600


@dataclass(frozen=True, slots=True)
class RedisSettings:
    host: str
    password: str
    port: int = DEFAULT_REDIS_PORT

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            host=environ["REDIS_CART_HOST"],
            password=environ["REDIS_CART_PASSWORD"],
            port=int(environ.get("REDIS_CART_PORT", DEFAULT_REDIS_PORT)),
        )


@dataclass(frozen=True, slots=True)
class CartSettings:
    redis: RedisSettings
    jwt: JwtSettings
    catalog_base_url: str = DEFAULT_CATALOG_BASE_URL
    catalog_timeout_seconds: float = DEFAULT_CATALOG_TIMEOUT_SECONDS
    media_public_base_url: str = DEFAULT_MEDIA_PUBLIC_BASE_URL
    ttl_seconds: int = CART_TTL_SECONDS
    log_level: str = "INFO"
    root_path: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            redis=RedisSettings.from_env(environ),
            jwt=JwtSettings.from_env(environ),
            catalog_base_url=environ.get("CATALOG_BASE_URL", DEFAULT_CATALOG_BASE_URL),
            catalog_timeout_seconds=float(
                environ.get("CATALOG_TIMEOUT_SECONDS", DEFAULT_CATALOG_TIMEOUT_SECONDS)
            ),
            media_public_base_url=environ.get(
                "MEDIA_PUBLIC_BASE_URL", DEFAULT_MEDIA_PUBLIC_BASE_URL
            ),
            ttl_seconds=int(environ.get("CART_TTL_SECONDS", CART_TTL_SECONDS)),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
        )
