from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final, Self

from ecommerce_auth import JwtSettings
from ecommerce_resilience import BreakerConfig, ReadRetryPolicy

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
    catalog_breaker: BreakerConfig = field(default_factory=BreakerConfig)
    catalog_retry: ReadRetryPolicy = field(default_factory=ReadRetryPolicy)
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
            catalog_breaker=breaker_from_env(environ),
            catalog_retry=retry_from_env(environ),
            media_public_base_url=environ.get(
                "MEDIA_PUBLIC_BASE_URL", DEFAULT_MEDIA_PUBLIC_BASE_URL
            ),
            ttl_seconds=int(environ.get("CART_TTL_SECONDS", CART_TTL_SECONDS)),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
        )


def breaker_from_env(environ: Mapping[str, str]) -> BreakerConfig:
    defaults = BreakerConfig()
    return BreakerConfig(
        failure_threshold=int(
            environ.get("CATALOG_BREAKER_FAILURE_THRESHOLD", defaults.failure_threshold)
        ),
        open_seconds=float(environ.get("CATALOG_BREAKER_OPEN_SECONDS", defaults.open_seconds)),
        half_open_probes=int(
            environ.get("CATALOG_BREAKER_HALF_OPEN_PROBES", defaults.half_open_probes)
        ),
    )


def retry_from_env(environ: Mapping[str, str]) -> ReadRetryPolicy:
    defaults = ReadRetryPolicy()
    return ReadRetryPolicy(
        attempts=int(environ.get("CATALOG_RETRY_ATTEMPTS", defaults.attempts)),
        initial_delay_seconds=float(
            environ.get("CATALOG_RETRY_INITIAL_DELAY_SECONDS", defaults.initial_delay_seconds)
        ),
        max_delay_seconds=float(
            environ.get("CATALOG_RETRY_MAX_DELAY_SECONDS", defaults.max_delay_seconds)
        ),
    )
