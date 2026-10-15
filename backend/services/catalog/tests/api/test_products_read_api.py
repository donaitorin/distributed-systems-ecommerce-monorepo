from urllib.parse import unquote

import httpx
import pytest
from catalog_testing.support import SteppingClock, valid_product


async def create(client: httpx.AsyncClient, admin: dict[str, str], **overrides: object) -> None:
    response = await client.post("/api/v1/products", json=valid_product(**overrides), headers=admin)
    assert response.status_code == 201


async def test_list_is_public_and_empty_at_first(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/products")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "next_cursor": None,
        "prev_cursor": None,
        "total": 0,
        "total_exact": True,
    }


async def test_list_shows_the_newest_first_and_hides_deleted_products(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> None:
    for sku in ("C-1", "A-1", "B-1"):
        await create(client, admin, sku=sku)
        clock.advance()
    await client.delete("/api/v1/products/B-1", headers=admin | {"If-Match": "*"})

    response = await client.get("/api/v1/products")

    assert [item["sku"] for item in response.json()["items"]] == ["A-1", "C-1"]


async def test_list_respects_the_limit(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> None:
    for index in range(13):
        await create(client, admin, sku=f"P-{index:02d}")
        clock.advance()

    response = await client.get("/api/v1/products", params={"limit": 12})

    body = response.json()
    assert len(body["items"]) == 12
    assert body["next_cursor"] is not None
    assert body["total"] == 13


@pytest.mark.parametrize("limit", ["0", "2", "100", "-1", "abc"])
async def test_list_rejects_a_limit_outside_the_allowed_page_sizes(
    client: httpx.AsyncClient, limit: str
) -> None:
    response = await client.get("/api/v1/products", params={"limit": limit})

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["errors"][0]["location"] == "query.limit"


async def test_get_returns_the_product_with_an_etag_and_string_decimals(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    await create(client, admin, price="89.9", weight_kg="0.35")

    response = await client.get("/api/v1/products/RS-001")

    body = response.json()
    assert response.status_code == 200
    assert response.headers["ETag"] == '"1"'
    assert body["price"] == "89.90"
    assert body["weight_kg"] == "0.350"
    assert body["stock"] == 150
    assert body["version"] == 1
    assert body["category"] is None
    assert set(body) == {
        "sku",
        "name",
        "description",
        "category",
        "price",
        "stock",
        "weight_kg",
        "version",
        "created_at",
        "updated_at",
    }


async def test_get_embeds_the_category(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    category = next(
        item for item in (await client.get("/api/v1/categories")).json() if item["slug"] == "books"
    )
    await create(client, admin, category_id=category["id"])

    body = (await client.get("/api/v1/products/RS-001")).json()

    assert body["category"] == {"id": category["id"], "name": "Books", "slug": "books"}


@pytest.mark.parametrize("sku", ["rs-001", "Rs-001", "RS-001"])
async def test_get_ignores_sku_casing(
    client: httpx.AsyncClient, admin: dict[str, str], sku: str
) -> None:
    await create(client, admin)

    response = await client.get(f"/api/v1/products/{sku}")

    assert response.status_code == 200
    assert response.json()["sku"] == "RS-001"


@pytest.mark.parametrize("sku", ["MISSING", "has%20space", "bad;sku"])
async def test_get_unknown_sku_is_a_404_problem(client: httpx.AsyncClient, sku: str) -> None:
    response = await client.get(f"/api/v1/products/{sku}")

    body = response.json()
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["title"] == "Product not found"
    assert body["status"] == 404
    assert body["instance"] == f"/api/v1/products/{unquote(sku)}"
    assert body["request_id"] == response.headers["X-Request-ID"]


async def test_get_a_deleted_product_is_a_404(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    await create(client, admin)
    await client.delete("/api/v1/products/RS-001", headers=admin | {"If-Match": '"1"'})

    response = await client.get("/api/v1/products/RS-001")

    assert response.status_code == 404


async def test_hostile_text_is_returned_literally(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    name = "<script>alert('xss')</script> Robert'); DROP TABLE products;--"
    await create(client, admin, name=name, description='"quoted", with comma — ™')

    body = (await client.get("/api/v1/products/RS-001")).json()

    assert body["name"] == name
    assert body["description"] == '"quoted", with comma — ™'
