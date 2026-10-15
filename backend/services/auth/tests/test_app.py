from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from auth_testing.support import FakeHasher, SteppingClock, auth_settings, new_signing_key
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from auth.infra.database import create_engine
from auth.infra.keys import KeyStore, KeyStoreError
from auth.main import SERVICE_NAME, build, create_auth_app

UNREACHABLE_DATABASE = "postgresql+asyncpg://auth_user:pw@127.0.0.1:1/auth_db"


@pytest.fixture
def engine() -> AsyncEngine:
    return create_engine(UNREACHABLE_DATABASE)


@pytest.fixture
def keys() -> KeyStore:
    key = new_signing_key()
    return KeyStore([key], key.kid)


@pytest.fixture
async def client(engine: AsyncEngine, keys: KeyStore) -> AsyncIterator[httpx.AsyncClient]:
    app = create_auth_app(auth_settings(), engine, keys=keys, hasher=FakeHasher())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


async def test_health_does_not_need_the_database(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200


async def test_ready_reports_the_database_as_failed_when_unreachable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed"}


async def test_jwks_is_served_without_the_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/auth/.well-known/jwks.json")

    assert response.status_code == 200
    assert len(response.json()["keys"]) == 1


async def test_openapi_describes_the_auth_service(client: httpx.AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.json()["info"]["title"] == SERVICE_NAME == "auth"


async def test_session_factory_is_bound_to_the_engine(engine: AsyncEngine, keys: KeyStore) -> None:
    app = create_auth_app(auth_settings(), engine, keys=keys, hasher=FakeHasher())

    factory = app.state.session_factory
    assert isinstance(factory, async_sessionmaker)
    assert factory.kw["bind"] is engine


async def test_engine_is_disposed_on_shutdown(engine: AsyncEngine, keys: KeyStore) -> None:
    with patch.object(engine.sync_engine, "dispose") as dispose:
        app = create_auth_app(auth_settings(), engine, keys=keys, hasher=FakeHasher())

        async with app.router.lifespan_context(app):
            dispose.assert_not_called()

        dispose.assert_called_once()


async def test_root_path_comes_from_the_settings(engine: AsyncEngine, keys: KeyStore) -> None:
    app = create_auth_app(auth_settings(root_path="/auth"), engine, keys=keys, hasher=FakeHasher())

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        response = await http_client.get("/openapi.json")

    assert response.json()["servers"] == [{"url": "/auth"}]


def test_the_app_loads_keys_from_the_configured_directory(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    settings = auth_settings(keys_dir=tmp_path, generate_key_if_missing=True)

    app = create_auth_app(settings, engine, clock=SteppingClock(), hasher=FakeHasher())
    written = list(tmp_path.glob("*.pem"))

    assert len(app.state.jwks["keys"]) == 1
    assert [item["kid"] for item in app.state.jwks["keys"]] == [path.stem for path in written]


def test_the_app_refuses_to_start_without_a_signing_key(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    with pytest.raises(KeyStoreError):
        create_auth_app(auth_settings(keys_dir=tmp_path), engine, hasher=FakeHasher())


def test_build_creates_the_app_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environ = {
        "AUTH_DB_HOST": "127.0.0.1",
        "AUTH_DB_PORT": "1",
        "AUTH_DB_NAME": "auth_db",
        "AUTH_DB_USER": "auth_user",
        "AUTH_DB_PASSWORD": "pw",
        "AUTH_KEYS_DIR": str(tmp_path),
        "AUTH_GENERATE_KEY_IF_MISSING": "true",
        "AUTH_ARGON2_MEMORY_KIB": "8",
        "AUTH_ARGON2_TIME_COST": "1",
    }
    for key, value in environ.items():
        monkeypatch.setenv(key, value)

    app = build()

    assert app.title == SERVICE_NAME
