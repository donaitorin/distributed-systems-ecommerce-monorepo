import pytest

from catalog.settings import CatalogSettings, MediaSettings, database_url_from_env

ENVIRON = {
    "CATALOG_DB_HOST": "postgres",
    "CATALOG_DB_NAME": "catalog_db",
    "CATALOG_DB_USER": "catalog_user",
    "CATALOG_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://dev-auth:8080/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "OBJECT_STORAGE_ACCESS_KEY": "access",
    "OBJECT_STORAGE_SECRET_KEY": "secret",
    "OBJECT_STORAGE_ENDPOINT": "http://object-storage:8333",
    "OBJECT_STORAGE_MEDIA_BUCKET": "media",
    "MEDIA_PUBLIC_BASE_URL": "http://localhost:8000/media",
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


def test_the_search_timeout_defaults_to_two_seconds() -> None:
    assert CatalogSettings.from_env(ENVIRON).search_timeout_ms == 2000


def test_the_search_timeout_can_be_configured() -> None:
    settings = CatalogSettings.from_env(ENVIRON | {"CATALOG_SEARCH_TIMEOUT_MS": "750"})

    assert settings.search_timeout_ms == 750


@pytest.mark.parametrize("value", ["0", "-5", "abc", "", "1.5", "60001"])
def test_an_invalid_search_timeout_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="CATALOG_SEARCH_TIMEOUT_MS"):
        CatalogSettings.from_env(ENVIRON | {"CATALOG_SEARCH_TIMEOUT_MS": value})


def test_media_settings_come_from_the_object_storage_variables() -> None:
    settings = CatalogSettings.from_env(ENVIRON)

    assert settings.media == MediaSettings(
        s3=settings.media.s3,
        bucket="media",
        public_base_url="http://localhost:8000/media",
    )
    assert settings.media.s3.endpoint_url == "http://object-storage:8333"
    assert settings.media.s3.access_key == "access"


@pytest.mark.parametrize(
    "missing",
    [
        "OBJECT_STORAGE_ACCESS_KEY",
        "OBJECT_STORAGE_SECRET_KEY",
        "OBJECT_STORAGE_MEDIA_BUCKET",
        "MEDIA_PUBLIC_BASE_URL",
    ],
)
def test_the_media_variables_are_required(missing: str) -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != missing}

    with pytest.raises(KeyError):
        CatalogSettings.from_env(environ)


def test_the_import_settings_default_to_the_imports_bucket_and_fifty_megabytes() -> None:
    settings = CatalogSettings.from_env(ENVIRON)

    assert settings.imports_bucket == "imports"
    assert settings.import_max_bytes == 50 * 1024 * 1024


def test_the_import_settings_can_be_configured() -> None:
    settings = CatalogSettings.from_env(
        ENVIRON | {"OBJECT_STORAGE_IMPORTS_BUCKET": "bulk", "IMPORT_MAX_BYTES": "1048576"}
    )

    assert settings.imports_bucket == "bulk"
    assert settings.import_max_bytes == 1048576


@pytest.mark.parametrize("value", ["0", "-1", "abc", ""])
def test_an_invalid_import_size_limit_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="IMPORT_MAX_BYTES"):
        CatalogSettings.from_env(ENVIRON | {"IMPORT_MAX_BYTES": value})
