from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from sqlalchemy import URL

from ecommerce_auth import JwtSettings

DEFAULT_DATABASE_PORT = 5432
DATABASE_DRIVER = "postgresql+asyncpg"


def database_url_from_env(environ: Mapping[str, str]) -> URL:
    return URL.create(
        DATABASE_DRIVER,
        username=environ["CATALOG_DB_USER"],
        password=environ["CATALOG_DB_PASSWORD"],
        host=environ["CATALOG_DB_HOST"],
        port=int(environ.get("CATALOG_DB_PORT", DEFAULT_DATABASE_PORT)),
        database=environ["CATALOG_DB_NAME"],
    )


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    database_url: URL
    jwt: JwtSettings
    log_level: str = "INFO"
    root_path: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            jwt=JwtSettings.from_env(environ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
        )
