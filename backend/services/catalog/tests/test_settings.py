import pytest

from catalog.settings import CatalogSettings

ENVIRON = {
    "CATALOG_DATABASE_URL": "postgresql+asyncpg://catalog_user:pw@postgres:5432/catalog_db",
    "JWT_JWKS_URL": "http://dev-auth:8080/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
}


def test_from_env_reads_database_and_jwt_settings_with_defaults() -> None:
    settings = CatalogSettings.from_env(ENVIRON)

    assert settings.database_url.endswith("/catalog_db")
    assert settings.jwt.audience == "ecommerce-api"
    assert settings.jwt.jwks_url == "http://dev-auth:8080/jwks.json"
    assert settings.log_level == "INFO"
    assert settings.root_path == ""


def test_from_env_reads_optional_overrides() -> None:
    settings = CatalogSettings.from_env(
        ENVIRON | {"LOG_LEVEL": "DEBUG", "ROOT_PATH": "/catalog", "JWT_AUDIENCE": "other"}
    )

    assert settings.log_level == "DEBUG"
    assert settings.root_path == "/catalog"
    assert settings.jwt.audience == "other"


def test_database_url_is_required() -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != "CATALOG_DATABASE_URL"}

    with pytest.raises(KeyError):
        CatalogSettings.from_env(environ)
