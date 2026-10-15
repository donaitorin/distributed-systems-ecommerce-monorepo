from collections.abc import AsyncIterator
from unittest.mock import patch

import httpx
import pytest
from accounts_testing.support import accounts_settings
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from accounts.infra.database import create_engine
from accounts.main import SERVICE_NAME, build, create_accounts_app

UNREACHABLE_DATABASE = "postgresql+asyncpg://accounts_user:pw@127.0.0.1:1/accounts_db"


@pytest.fixture
def engine() -> AsyncEngine:
    return create_engine(UNREACHABLE_DATABASE)


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_accounts_app(accounts_settings(), engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


async def test_health_does_not_need_the_database(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200


async def test_ready_depends_only_on_the_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed"}


async def test_the_token_verifier_is_created_without_reaching_the_jwks_endpoint(
    engine: AsyncEngine,
) -> None:
    app = create_accounts_app(accounts_settings(), engine)

    assert app.state.token_verifier is not None


async def test_a_request_with_an_unreachable_key_set_is_unauthorized_not_a_crash(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/accounts/me", headers={"Authorization": "Bearer not.a.jwt"}
    )

    assert response.status_code == 401


async def test_openapi_describes_the_accounts_service(client: httpx.AsyncClient) -> None:
    response = await client.get("/openapi.json")
    document = response.json()

    assert document["info"]["title"] == SERVICE_NAME == "accounts"
    assert "/api/v1/accounts" in document["paths"]
    assert "/api/v1/accounts/me/addresses/{address_id}" in document["paths"]


async def test_session_factory_is_bound_to_the_engine(engine: AsyncEngine) -> None:
    app = create_accounts_app(accounts_settings(), engine)

    factory = app.state.session_factory
    assert isinstance(factory, async_sessionmaker)
    assert factory.kw["bind"] is engine


async def test_engine_is_disposed_on_shutdown(engine: AsyncEngine) -> None:
    with patch.object(engine.sync_engine, "dispose") as dispose:
        app = create_accounts_app(accounts_settings(), engine)

        async with app.router.lifespan_context(app):
            dispose.assert_not_called()

        dispose.assert_called_once()


async def test_root_path_comes_from_the_settings(engine: AsyncEngine) -> None:
    app = create_accounts_app(accounts_settings(root_path="/accounts"), engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        response = await http_client.get("/openapi.json")

    assert response.json()["servers"] == [{"url": "/accounts"}]


def test_build_creates_the_app_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    environ = {
        "ACCOUNTS_DB_HOST": "127.0.0.1",
        "ACCOUNTS_DB_PORT": "1",
        "ACCOUNTS_DB_NAME": "accounts_db",
        "ACCOUNTS_DB_USER": "accounts_user",
        "ACCOUNTS_DB_PASSWORD": "pw",
        "JWT_JWKS_URL": "http://auth:8000/api/v1/auth/.well-known/jwks.json",
        "JWT_ISSUER": "ecommerce-auth",
    }
    for key, value in environ.items():
        monkeypatch.setenv(key, value)

    assert build().title == SERVICE_NAME
