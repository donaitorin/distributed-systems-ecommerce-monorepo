from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Self

from sqlalchemy import URL

from auth.domain.tokens import (
    ACCESS_TOKEN_TTL,
    REFRESH_FAMILY_TTL,
    REFRESH_TOKEN_TTL,
    REUSE_GRACE,
)
from auth.infra.hashing import (
    DEFAULT_CONCURRENCY,
    DEFAULT_MEMORY_COST_KIB,
    DEFAULT_PARALLELISM,
    DEFAULT_TIME_COST,
    HashingSettings,
)
from ecommerce_auth import DEFAULT_AUDIENCE

DEFAULT_DATABASE_PORT = 5432
DATABASE_DRIVER = "postgresql+asyncpg"
DEFAULT_ISSUER = "ecommerce-auth"
DEFAULT_KEYS_DIR = "/keys"
TRUE_VALUES = frozenset({"1", "true", "yes"})


def database_url_from_env(environ: Mapping[str, str]) -> URL:
    return URL.create(
        DATABASE_DRIVER,
        username=environ["AUTH_DB_USER"],
        password=environ["AUTH_DB_PASSWORD"],
        host=environ["AUTH_DB_HOST"],
        port=int(environ.get("AUTH_DB_PORT", DEFAULT_DATABASE_PORT)),
        database=environ["AUTH_DB_NAME"],
    )


def positive_int(environ: Mapping[str, str], name: str, default: int) -> int:
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def seconds(environ: Mapping[str, str], name: str, default: timedelta) -> timedelta:
    return timedelta(seconds=positive_int(environ, name, int(default.total_seconds())))


def hashing_from_env(environ: Mapping[str, str]) -> HashingSettings:
    return HashingSettings(
        memory_cost_kib=positive_int(environ, "AUTH_ARGON2_MEMORY_KIB", DEFAULT_MEMORY_COST_KIB),
        time_cost=positive_int(environ, "AUTH_ARGON2_TIME_COST", DEFAULT_TIME_COST),
        parallelism=positive_int(environ, "AUTH_ARGON2_PARALLELISM", DEFAULT_PARALLELISM),
        concurrency=positive_int(environ, "AUTH_HASH_CONCURRENCY", DEFAULT_CONCURRENCY),
    )


@dataclass(frozen=True, slots=True)
class AuthSettings:
    database_url: URL
    issuer: str = DEFAULT_ISSUER
    audience: str = DEFAULT_AUDIENCE
    keys_dir: Path = Path(DEFAULT_KEYS_DIR)
    active_kid: str | None = None
    generate_key_if_missing: bool = False
    access_token_ttl: timedelta = ACCESS_TOKEN_TTL
    refresh_token_ttl: timedelta = REFRESH_TOKEN_TTL
    refresh_family_ttl: timedelta = REFRESH_FAMILY_TTL
    refresh_reuse_grace: timedelta = REUSE_GRACE
    hashing: HashingSettings = field(default_factory=HashingSettings)
    log_level: str = "INFO"
    root_path: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            issuer=environ.get("JWT_ISSUER", DEFAULT_ISSUER),
            audience=environ.get("JWT_AUDIENCE", DEFAULT_AUDIENCE),
            keys_dir=Path(environ.get("AUTH_KEYS_DIR", DEFAULT_KEYS_DIR)),
            active_kid=environ.get("AUTH_ACTIVE_KID") or None,
            generate_key_if_missing=environ.get("AUTH_GENERATE_KEY_IF_MISSING", "").lower()
            in TRUE_VALUES,
            access_token_ttl=seconds(environ, "AUTH_ACCESS_TOKEN_TTL_SECONDS", ACCESS_TOKEN_TTL),
            refresh_token_ttl=seconds(environ, "AUTH_REFRESH_TOKEN_TTL_SECONDS", REFRESH_TOKEN_TTL),
            refresh_family_ttl=seconds(
                environ, "AUTH_REFRESH_FAMILY_TTL_SECONDS", REFRESH_FAMILY_TTL
            ),
            refresh_reuse_grace=seconds(environ, "AUTH_REFRESH_REUSE_GRACE_SECONDS", REUSE_GRACE),
            hashing=hashing_from_env(environ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
        )
