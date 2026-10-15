from datetime import timedelta
from pathlib import Path

import pytest

from auth.settings import AuthSettings, database_url_from_env

ENVIRON = {
    "AUTH_DB_HOST": "postgres",
    "AUTH_DB_NAME": "auth_db",
    "AUTH_DB_USER": "auth_user",
    "AUTH_DB_PASSWORD": "pw",
}


def test_defaults_match_the_documented_policy() -> None:
    settings = AuthSettings.from_env(ENVIRON)

    assert settings.database_url.host == "postgres"
    assert settings.database_url.port == 5432
    assert settings.database_url.drivername == "postgresql+asyncpg"
    assert settings.issuer == "ecommerce-auth"
    assert settings.audience == "ecommerce-api"
    assert settings.keys_dir == Path("/keys")
    assert settings.active_kid is None
    assert settings.generate_key_if_missing is False
    assert settings.access_token_ttl == timedelta(minutes=15)
    assert settings.refresh_token_ttl == timedelta(days=7)
    assert settings.refresh_family_ttl == timedelta(days=30)
    assert settings.refresh_reuse_grace == timedelta(seconds=10)
    assert settings.hashing.memory_cost_kib == 19456
    assert settings.hashing.time_cost == 2
    assert settings.log_level == "INFO"
    assert settings.root_path == ""


def test_every_value_can_be_overridden() -> None:
    settings = AuthSettings.from_env(
        ENVIRON
        | {
            "AUTH_DB_PORT": "15432",
            "JWT_ISSUER": "issuer",
            "JWT_AUDIENCE": "audience",
            "AUTH_KEYS_DIR": "/srv/keys",
            "AUTH_ACTIVE_KID": "kid-1",
            "AUTH_GENERATE_KEY_IF_MISSING": "true",
            "AUTH_ACCESS_TOKEN_TTL_SECONDS": "60",
            "AUTH_REFRESH_TOKEN_TTL_SECONDS": "120",
            "AUTH_REFRESH_FAMILY_TTL_SECONDS": "600",
            "AUTH_REFRESH_REUSE_GRACE_SECONDS": "3",
            "AUTH_ARGON2_MEMORY_KIB": "64",
            "AUTH_ARGON2_TIME_COST": "5",
            "AUTH_ARGON2_PARALLELISM": "2",
            "AUTH_HASH_CONCURRENCY": "8",
            "LOG_LEVEL": "DEBUG",
            "ROOT_PATH": "/auth",
        }
    )

    assert settings.database_url.port == 15432
    assert settings.issuer == "issuer"
    assert settings.audience == "audience"
    assert settings.keys_dir == Path("/srv/keys")
    assert settings.active_kid == "kid-1"
    assert settings.generate_key_if_missing is True
    assert settings.access_token_ttl == timedelta(seconds=60)
    assert settings.refresh_token_ttl == timedelta(seconds=120)
    assert settings.refresh_family_ttl == timedelta(seconds=600)
    assert settings.refresh_reuse_grace == timedelta(seconds=3)
    assert (settings.hashing.memory_cost_kib, settings.hashing.time_cost) == (64, 5)
    assert (settings.hashing.parallelism, settings.hashing.concurrency) == (2, 8)
    assert settings.log_level == "DEBUG"
    assert settings.root_path == "/auth"


def test_an_empty_active_kid_means_the_newest_key() -> None:
    assert AuthSettings.from_env(ENVIRON | {"AUTH_ACTIVE_KID": ""}).active_kid is None


@pytest.mark.parametrize("value", ["0", "-5", "abc", ""])
def test_durations_must_be_positive_integers(value: str) -> None:
    with pytest.raises(ValueError, match="AUTH_ACCESS_TOKEN_TTL_SECONDS"):
        AuthSettings.from_env(ENVIRON | {"AUTH_ACCESS_TOKEN_TTL_SECONDS": value})


@pytest.mark.parametrize(
    "missing", ["AUTH_DB_HOST", "AUTH_DB_NAME", "AUTH_DB_USER", "AUTH_DB_PASSWORD"]
)
def test_every_database_variable_is_required(missing: str) -> None:
    environ = {key: value for key, value in ENVIRON.items() if key != missing}

    with pytest.raises(KeyError):
        AuthSettings.from_env(environ)


@pytest.mark.parametrize("password", ["p@ss:w/rd", "100%#?&=", "with space", "quote'\"s"])
def test_special_characters_in_the_password_are_escaped(password: str) -> None:
    url = database_url_from_env(ENVIRON | {"AUTH_DB_PASSWORD": password})

    assert url.password == password
    assert url.render_as_string(hide_password=False).count("@") == 1
