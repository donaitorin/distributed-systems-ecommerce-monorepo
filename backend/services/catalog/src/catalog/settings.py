from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from sqlalchemy import URL

from catalog.domain.imports import DEFAULT_IMPORT_MAX_BYTES
from ecommerce_auth import JwtSettings
from ecommerce_storage import S3Settings

DEFAULT_DATABASE_PORT = 5432
DATABASE_DRIVER = "postgresql+asyncpg"
DEFAULT_SEARCH_TIMEOUT_MS = 2000
DEFAULT_IMPORTS_BUCKET = "imports"
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


def import_max_bytes_from_env(environ: Mapping[str, str]) -> int:
    raw = environ.get("IMPORT_MAX_BYTES")
    if raw is None:
        return DEFAULT_IMPORT_MAX_BYTES
    try:
        limit = int(raw)
    except ValueError:
        limit = 0
    if limit < 1:
        raise ValueError("IMPORT_MAX_BYTES must be a positive integer")
    return limit


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
class MediaSettings:
    s3: S3Settings
    bucket: str
    public_base_url: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            s3=S3Settings.from_env(environ),
            bucket=environ["OBJECT_STORAGE_MEDIA_BUCKET"],
            public_base_url=environ["MEDIA_PUBLIC_BASE_URL"],
        )


@dataclass(frozen=True, slots=True)
class CatalogSettings:
    database_url: URL
    jwt: JwtSettings
    media: MediaSettings
    log_level: str = "INFO"
    root_path: str = ""
    search_timeout_ms: int = DEFAULT_SEARCH_TIMEOUT_MS
    imports_bucket: str = DEFAULT_IMPORTS_BUCKET
    import_max_bytes: int = DEFAULT_IMPORT_MAX_BYTES

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            jwt=JwtSettings.from_env(environ),
            media=MediaSettings.from_env(environ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
            root_path=environ.get("ROOT_PATH", ""),
            search_timeout_ms=search_timeout_from_env(environ),
            imports_bucket=environ.get("OBJECT_STORAGE_IMPORTS_BUCKET", DEFAULT_IMPORTS_BUCKET),
            import_max_bytes=import_max_bytes_from_env(environ),
        )
