from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from sqlalchemy import URL

from ecommerce_auth import JwtSettings

DEFAULT_DATABASE_PORT = 5432
DATABASE_DRIVER = "postgresql+asyncpg"
DEFAULT_LATE_APPROVAL_DELAY_SECONDS = 90.0
DEFAULT_SETTLE_INTERVAL_SECONDS = 2.0


def database_url_from_env(environ: Mapping[str, str]) -> URL:
    return URL.create(
        DATABASE_DRIVER,
        username=environ["PAYMENTS_DB_USER"],
        password=environ["PAYMENTS_DB_PASSWORD"],
        host=environ["PAYMENTS_DB_HOST"],
        port=int(environ.get("PAYMENTS_DB_PORT", DEFAULT_DATABASE_PORT)),
        database=environ["PAYMENTS_DB_NAME"],
    )


def positive_seconds_from_env(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number of seconds") from error
    if not 0 < value <= 86_400:
        raise ValueError(f"{name} must be above 0 and at most 86400 seconds")
    return value


@dataclass(frozen=True, slots=True)
class PaymentsSettings:
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
