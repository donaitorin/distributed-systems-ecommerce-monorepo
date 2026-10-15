import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

import httpx
import pytest
from catalog_testing.support import bearer, build_test_app, http_client, valid_product
from sqlalchemy import make_url, text

from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.main import create_catalog_app
from catalog.settings import CatalogSettings
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer

pytestmark = pytest.mark.integration


@pytest.fixture
async def real_client(
    migrated_database_url: str, issuer: StubTokenIssuer
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    engine = create_engine(migrated_database_url)
    session_factory = create_session_factory(engine)
    app = build_test_app(issuer, lambda: SqlAlchemyUnitOfWork(session_factory))
    async with http_client(app) as client:
        yield client, migrated_database_url
    await engine.dispose()


def sku_for(name: str) -> str:
    return f"API-{abs(hash(name)) % 10**8}"


async def test_full_lifecycle_against_postgres(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, _ = real_client
    admin = bearer(issuer, Role.ADMIN)
    sku = sku_for("lifecycle")
    categories = (await client.get("/api/v1/categories")).json()
    assert len(categories) == 18
    books = next(item for item in categories if item["slug"] == "books")

    created = await client.post(
        "/api/v1/products",
        json=valid_product(sku=sku.lower(), category_id=books["id"], price="89.9"),
        headers=admin,
    )
    assert created.status_code == 201
    assert created.headers["ETag"] == '"1"'
    assert created.json()["category"]["slug"] == "books"
    assert created.json()["price"] == "89.90"

    fetched = await client.get(f"/api/v1/products/{sku}")
    assert fetched.json() == created.json()

    body = valid_product(name="Trail Shoes", price="99.50", stock=1)
    del body["sku"]
    updated = await client.put(
        f"/api/v1/products/{sku}", json=body, headers=admin | {"If-Match": fetched.headers["ETag"]}
    )
    assert updated.status_code == 200
    assert updated.headers["ETag"] == '"2"'
    assert updated.json()["category"] is None

    stale = await client.put(
        f"/api/v1/products/{sku}", json=body, headers=admin | {"If-Match": '"1"'}
    )
    assert stale.status_code == 412

    assert (
        await client.delete(f"/api/v1/products/{sku}", headers=admin | {"If-Match": '"2"'})
    ).status_code == 204
    assert (await client.get(f"/api/v1/products/{sku}")).status_code == 404
    again = await client.post("/api/v1/products", json=valid_product(sku=sku), headers=admin)
    assert again.status_code == 409


async def test_concurrent_updates_with_the_same_etag_have_exactly_one_winner(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, _ = real_client
    admin = bearer(issuer, Role.ADMIN)
    sku = sku_for("race")
    await client.post("/api/v1/products", json=valid_product(sku=sku, stock=100), headers=admin)

    def attempt(stock: int) -> Any:
        body = valid_product(stock=stock)
        del body["sku"]
        return client.put(f"/api/v1/products/{sku}", json=body, headers=admin | {"If-Match": '"1"'})

    results = await asyncio.gather(*(attempt(stock) for stock in range(1, 9)))

    statuses = sorted(response.status_code for response in results)
    assert statuses == [200] + [412] * 7
    winner = next(response for response in results if response.status_code == 200)
    final = (await client.get(f"/api/v1/products/{sku}")).json()
    assert final["version"] == 2
    assert final["stock"] == winner.json()["stock"]


async def test_hostile_text_is_stored_literally_and_the_table_survives(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, database_url = real_client
    admin = bearer(issuer, Role.ADMIN)
    sku = sku_for("hostile")
    hostile = "Robert'); DROP TABLE products;--"

    created = await client.post(
        "/api/v1/products",
        json=valid_product(sku=sku, name=hostile, description="<script>alert('xss')</script>"),
        headers=admin,
    )

    assert created.status_code == 201
    fetched = (await client.get(f"/api/v1/products/{sku}")).json()
    assert fetched["name"] == hostile
    assert fetched["description"] == "<script>alert('xss')</script>"
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT to_regclass('public.products')")) == "products"
            )
    finally:
        await engine.dispose()


async def test_category_creation_and_conflicts_against_postgres(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, _ = real_client
    admin = bearer(issuer, Role.ADMIN)

    created = await client.post("/api/v1/categories", json={"name": "Garden  Tools"}, headers=admin)
    duplicate = await client.post(
        "/api/v1/categories", json={"name": "garden tools"}, headers=admin
    )
    slug_clash = await client.post(
        "/api/v1/categories", json={"name": "Garden-Tools"}, headers=admin
    )

    assert created.status_code == 201
    assert created.json()["slug"] == "garden-tools"
    assert duplicate.status_code == 409
    assert slug_clash.status_code == 409


async def test_the_listing_reflects_what_was_written(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, _ = real_client
    admin = bearer(issuer, Role.ADMIN)
    sku = sku_for("listing")
    await client.post("/api/v1/products", json=valid_product(sku=sku), headers=admin)

    listing = (await client.get("/api/v1/products", params={"limit": 12})).json()

    assert sku in [item["sku"] for item in listing["items"]]


async def test_every_page_of_a_search_over_http_is_complete_and_free_of_duplicates(
    real_client: tuple[httpx.AsyncClient, str], issuer: StubTokenIssuer
) -> None:
    client, _ = real_client
    admin = bearer(issuer, Role.ADMIN)
    categories = (await client.get("/api/v1/categories")).json()
    toys = next(item for item in categories if item["slug"] == "games")
    prefix = f"WALK{abs(hash('walk')) % 10**6}"
    for index in range(40):
        body = valid_product(
            sku=f"{prefix}-{index:02d}",
            name="Walking Boots",
            description="Waterproof boots",
            category_id=toys["id"],
            price=str(20 + index % 3),
        )
        assert (await client.post("/api/v1/products", json=body, headers=admin)).status_code == 201

    for sort in ("newest", "price_asc", "price_desc", "relevance"):
        seen: list[str] = []
        params: dict[str, str] = {
            "category": "games",
            "q": "walking boots",
            "sort": sort,
            "limit": "12",
        }
        while True:
            page = (await client.get("/api/v1/products", params=params)).json()
            seen += [item["sku"] for item in page["items"] if item["sku"].startswith(prefix)]
            if page["next_cursor"] is None:
                break
            params["cursor"] = page["next_cursor"]

        assert len(seen) == len(set(seen)) == 40, sort

    mismatch = await client.get(
        "/api/v1/products", params={**params, "category": "books", "cursor": params["cursor"]}
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["errors"][0]["type"] == "cursor_mismatch"


async def test_a_search_over_the_configured_time_limit_answers_503_over_http(
    seeded_database_url: str,
) -> None:
    settings = CatalogSettings.from_env(
        {
            "CATALOG_DB_HOST": "unused",
            "CATALOG_DB_NAME": "unused",
            "CATALOG_DB_USER": "unused",
            "CATALOG_DB_PASSWORD": "unused",
            "JWT_JWKS_URL": "http://dev-auth:8080/jwks.json",
            "JWT_ISSUER": "ecommerce-auth",
            "CATALOG_SEARCH_TIMEOUT_MS": "1",
            "OBJECT_STORAGE_ACCESS_KEY": "access",
            "OBJECT_STORAGE_SECRET_KEY": "secret",
            "OBJECT_STORAGE_MEDIA_BUCKET": "media",
            "MEDIA_PUBLIC_BASE_URL": "http://localhost:8000/media",
        }
    )
    settings = replace(settings, database_url=make_url(seeded_database_url))
    app = create_catalog_app(settings)

    async with app.router.lifespan_context(app), http_client(app) as client:
        slow = await client.get("/api/v1/products", params={"q": "refrigerator freezer"})

    assert slow.status_code == 503
    assert slow.headers["Retry-After"] == "1"
    assert slow.json()["title"] == "Search timed out"
