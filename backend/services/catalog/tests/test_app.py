from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from catalog_testing.support import media_settings
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from catalog.infra.database import create_engine
from catalog.main import SERVICE_NAME, build, create_catalog_app
from catalog.settings import CatalogSettings
from ecommerce_auth import JwtSettings

UNREACHABLE_DATABASE = "postgresql+asyncpg://catalog_user:pw@127.0.0.1:1/catalog_db"
UNREACHABLE_ENVIRON = {
    "CATALOG_DB_HOST": "127.0.0.1",
    "CATALOG_DB_PORT": "1",
    "CATALOG_DB_NAME": "catalog_db",
    "CATALOG_DB_USER": "catalog_user",
    "CATALOG_DB_PASSWORD": "pw",
    "JWT_JWKS_URL": "http://auth:8000/jwks.json",
    "JWT_ISSUER": "ecommerce-auth",
    "OBJECT_STORAGE_ACCESS_KEY": "access",
    "OBJECT_STORAGE_SECRET_KEY": "secret",
    "OBJECT_STORAGE_ENDPOINT": "http://object-storage:8333",
    "OBJECT_STORAGE_MEDIA_BUCKET": "media",
    "MEDIA_PUBLIC_BASE_URL": "http://localhost:8000/media",
}


def make_settings(**overrides: Any) -> CatalogSettings:
    return CatalogSettings(
        database_url=make_url(UNREACHABLE_DATABASE),
        jwt=JwtSettings(jwks_url="http://auth:8000/jwks.json", issuer="ecommerce-auth"),
        media=media_settings(),
        **overrides,
    )


@pytest.fixture
def engine() -> AsyncEngine:
    return create_engine(UNREACHABLE_DATABASE)


@pytest.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[httpx.AsyncClient]:
    app = create_catalog_app(make_settings(), engine)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


async def test_health_does_not_need_the_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200


async def test_ready_reports_the_database_as_failed_when_unreachable(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "failed"}


async def test_openapi_describes_the_catalog_service(client: httpx.AsyncClient) -> None:
    response = await client.get("/openapi.json")

    assert response.json()["info"]["title"] == SERVICE_NAME == "catalog"


async def test_session_factory_is_bound_to_the_engine(engine: AsyncEngine) -> None:
    app = create_catalog_app(make_settings(), engine)

    factory = app.state.session_factory
    assert isinstance(factory, async_sessionmaker)
    assert factory.kw["bind"] is engine


async def test_engine_is_disposed_on_shutdown(engine: AsyncEngine) -> None:
    with patch.object(engine.sync_engine, "dispose") as dispose:
        app = create_catalog_app(make_settings(), engine)

        async with app.router.lifespan_context(app):
            dispose.assert_not_called()

        dispose.assert_called_once()


async def test_root_path_comes_from_the_settings(engine: AsyncEngine) -> None:
    app = create_catalog_app(make_settings(root_path="/catalog"), engine)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        response = await http_client.get("/openapi.json")

    assert response.json()["servers"] == [{"url": "/catalog"}]


def test_build_creates_the_app_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in UNREACHABLE_ENVIRON.items():
        monkeypatch.setenv(key, value)

    app = build()

    assert app.title == SERVICE_NAME
