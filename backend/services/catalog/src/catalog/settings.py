from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from sqlalchemy import URL

from ecommerce_auth import JwtSettings

DEFAULT_DATABASE_PORT = 5432
DATABASE_DRIVER = "postgresql+asyncpg"
DEFAULT_SEARCH_TIMEOUT_MS = 2000
MAX_SEARCH_TIMEOUT_MS = 60_000


def database_url_from_env(environ: Mapping[str, str]) -> URL:
    return URL.create(
        DATABASE_DRIVER,
        username=environ["CATALOG_DB_USER"],
        password=environ["CATALOG_DB_PASSWORD"],
        host=environ["CATALOG_DB_HOST"],
        port=int(environ.get("CATALOG_DB_PORT", DEFAULT_DATABASE_PORT)),
        database=environ["CATALOG_DB_NAME"],
    )


def search_timeout_from_env(environ: Mapping[str, str]) -> int:
    raw = environ.get("CATALOG_SEARCH_TIMEOUT_MS")
    if raw is None:
        return DEFAULT_SEARCH_TIMEOUT_MS
    try:
        timeout = int(raw)
    except ValueError:
        timeout = 0
    if not 1 <= timeout <= MAX_SEARCH_TIMEOUT_MS:
        raise ValueError(
            f"CATALOG_SEARCH_TIMEOUT_MS must be an integer between 1 and {MAX_SEARCH_TIMEOUT_MS}"
        )
    return timeout


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    database_url: URL
    jwt: JwtSettings
    log_level: str = "INFO"
    root_path: str = ""
    search_timeout_ms: int = DEFAULT_SEARCH_TIMEOUT_MS

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            jwt=JwtSettings.from_env(environ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
            search_timeout_ms=search_timeout_from_env(environ),
        )
