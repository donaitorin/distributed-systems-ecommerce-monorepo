import pytest

from accounts.settings import AccountsSettings, database_url_from_env

ENVIRON = {
    "ACCOUNTS_DB_HOST": "db",
    "ACCOUNTS_DB_PORT": "6543",
    "ACCOUNTS_DB_NAME": "accounts_db",
    "ACCOUNTS_DB_USER": "accounts_user",
    "ACCOUNTS_DB_PASSWORD": "p@ss/word",
    "JWT_JWKS_URL": "http://auth:8000/api/v1/auth/.well-known/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
}


def test_the_database_url_is_built_from_the_environment() -> None:
    url = database_url_from_env(ENVIRON)

    assert (url.host, url.port, url.database, url.username) == (
        "db",
        6543,
        "accounts_db",
        "accounts_user",
    )
    assert url.password == "p@ss/word"
    assert url.drivername == "postgresql+asyncpg"


def test_the_port_defaults_to_the_postgres_port() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "ACCOUNTS_DB_PORT"}

    assert database_url_from_env(environ).port == 5432


def test_settings_read_jwt_logging_and_root_path() -> None:
    settings = AccountsSettings.from_env(ENVIRON | {"LOG_LEVEL": "DEBUG", "ROOT_PATH": "/accounts"})

    assert settings.jwt.issuer == "ecommerce-auth"
    assert settings.jwt.jwks_url.endswith("jwks.json")
    assert (settings.log_level, settings.root_path) == ("DEBUG", "/accounts")


def test_settings_default_the_log_level_and_root_path() -> None:
    settings = AccountsSettings.from_env(ENVIRON)

    assert (settings.log_level, settings.root_path) == ("INFO", "")


def test_a_missing_variable_fails_loudly() -> None:
    with pytest.raises(KeyError):
        AccountsSettings.from_env({})
