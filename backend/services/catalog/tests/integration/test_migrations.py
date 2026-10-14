from collections.abc import Callable

import httpx
import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import make_url, text

from catalog.infra.database import create_engine, database_readiness_check
from catalog.infra.models import Base
from catalog.main import create_catalog_app
from catalog.settings import CatalogSettings
from ecommerce_auth import JwtSettings

pytestmark = pytest.mark.integration

EXPECTED_CATEGORIES = {
    "Accessories": "accessories",
    "Beauty": "beauty",
    "Books": "books",
    "Clothing": "clothing",
    "Electronics": "electronics",
    "Food & Beverage": "food-beverage",
    "Footwear": "footwear",
    "Games": "games",
    "Gifts": "gifts",
    "Health": "health",
    "Home & Office": "home-office",
    "Kitchen": "kitchen",
    "Misc": "misc",
    "Outdoors": "outdoors",
    "Pets": "pets",
    "Sports": "sports",
    "Stationery": "stationery",
    "Tools": "tools",
}


async def fetch_all(url: str, query: str) -> list[tuple[object, ...]]:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            return [tuple(row) for row in await connection.execute(text(query))]
    finally:
        await engine.dispose()


async def test_upgrade_creates_tables_and_seeds_the_eighteen_categories(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")

    rows = await fetch_all(empty_database_url, "SELECT name, slug FROM categories")

    assert {str(name): str(slug) for name, slug in rows} == EXPECTED_CATEGORIES
    assert len(rows) == 18


async def test_models_match_the_migrated_schema(migrated_database_url: str) -> None:
    engine = create_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
    finally:
        await engine.dispose()

    assert differences == []


async def test_downgrade_removes_everything_and_upgrade_can_run_again(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> None:
    alembic_runner(empty_database_url, "upgrade", "head")
    alembic_runner(empty_database_url, "downgrade", "base")

    tables = await fetch_all(
        empty_database_url,
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    assert tables == [("alembic_version",)]

    alembic_runner(empty_database_url, "upgrade", "head")
    count = await fetch_all(empty_database_url, "SELECT count(*) FROM categories")
    assert count == [(18,)]


async def test_database_readiness_check_passes_against_a_real_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    try:
        await database_readiness_check(engine).probe()
    finally:
        await engine.dispose()


async def test_ready_endpoint_is_green_with_a_reachable_database(
    migrated_database_url: str,
) -> None:
    settings = CatalogSettings(
        database_url=make_url(migrated_database_url),
        jwt=JwtSettings(jwks_url="http://dev-auth:8080/jwks.json", issuer="ecommerce-auth"),
    )
    app = create_catalog_app(settings)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}
