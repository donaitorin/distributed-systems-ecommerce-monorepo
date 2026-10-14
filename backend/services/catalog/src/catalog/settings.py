from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from ecommerce_auth import JwtSettings


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    database_url: str
    jwt: JwtSettings
    log_level: str = "INFO"
    root_path: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=environ["CATALOG_DATABASE_URL"],
            jwt=JwtSettings.from_env(environ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
        )
