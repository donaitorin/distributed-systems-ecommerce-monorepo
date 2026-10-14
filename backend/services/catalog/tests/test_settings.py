import pytest

from catalog.settings import CatalogSettings, database_url_from_env

ENVIRON = {
    "CATALOG_DB_HOST": "postgres",
    "CATALOG_DB_NAME": "catalog_db",
    "CATALOG_DB_USER": "catalog_user",
    "CATALOG_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://dev-auth:8080/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
}


def test_from_env_reads_database_and_jwt_settings_with_defaults() -> None:
    settings = CatalogSettings.from_env(ENVIRON)

    assert settings.database_url.host == "postgres"
    assert settings.database_url.port == 5432
    assert settings.database_url.database == "catalog_db"
    assert settings.database_url.drivername == "postgresql+asyncpg"
    assert settings.jwt.audience == "ecommerce-api"
    assert settings.jwt.jwks_url == "http://dev-auth:8080/jwks.json"
    assert settings.log_level == "INFO"
    assert settings.root_path == ""


def test_from_env_reads_optional_overrides() -> None:
    settings = CatalogSettings.from_env(
        ENVIRON
        | {
            "CATALOG_DB_PORT": "15432",
            "LOG_LEVEL": "DEBUG",
            "ROOT_PATH": "/catalog",
            "JWT_AUDIENCE": "other",
        }
    )

    assert settings.database_url.port == 15432
    assert settings.log_level == "DEBUG"
    assert settings.root_path == "/catalog"
    assert settings.jwt.audience == "other"


@pytest.mark.parametrize(
    "password",
    ["p@ss:w/rd", "100%#?&=", "with space", "ünïcode", "quote'\"s", "a@b@c"],
)
def test_special_characters_in_the_password_are_escaped(password: str) -> None:
    url = database_url_from_env(ENVIRON | {"CATALOG_DB_PASSWORD": password})

    rendered = url.render_as_string(hide_password=False)

    assert url.password == password
    assert url.host == "postgres"
    assert rendered.count("@") == 1
    assert "/" not in rendered.split("@")[0].removeprefix("postgresql+asyncpg://")


@pytest.mark.parametrize(
    "missing",
    ["CATALOG_DB_HOST", "CATALOG_DB_NAME", "CATALOG_DB_USER", "CATALOG_DB_PASSWORD"],
)
def test_every_database_variable_is_required(missing: str) -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != missing}

    with pytest.raises(KeyError):
        CatalogSettings.from_env(environ)
