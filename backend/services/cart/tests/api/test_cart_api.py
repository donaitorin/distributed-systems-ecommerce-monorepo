from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from cart_testing.support import (
    IMAGE_KEY,
    FakeCatalog,
    SteppingClock,
    Stores,
    bearer,
    build_test_app,
    http_client,
    product,
)
from fastapi import FastAPI

from cart.domain.cart import MAX_LINES
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer

CART = "/api/v1/cart"
ITEM = "/api/v1/cart/items/RS-001"
THUMBNAIL = f"/media/{IMAGE_KEY}-400.webp"


@pytest.fixture
def app(
    issuer: StubTokenIssuer, stores: Stores, catalog: FakeCatalog, clock: SteppingClock
) -> FastAPI:
    return build_test_app(issuer, stores, catalog, clock)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with http_client(app) as http:
        yield http


@pytest.fixture
def customer(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer)


async def test_the_cart_needs_a_token(client: httpx.AsyncClient) -> None:
    responses = [
        await client.get(CART),
        await client.put(ITEM, json={"quantity": 1}),
        await client.delete(ITEM),
        await client.delete(CART),
    ]

    assert [response.status_code for response in responses] == [401, 401, 401, 401]
    assert all(
        response.headers["content-type"] == "application/problem+json" for response in responses
    )


async def test_an_admin_can_also_shop(client: httpx.AsyncClient, issuer: StubTokenIssuer) -> None:
    response = await client.get(CART, headers=bearer(issuer, role=Role.ADMIN))

    assert response.status_code == 200


async def test_an_empty_cart(client: httpx.AsyncClient, customer: dict[str, str]) -> None:
    response = await client.get(CART, headers=customer)

    assert response.status_code == 200
    assert response.json() == {"items": [], "item_count": 0, "subtotal": "0.00"}
    assert response.headers["cache-control"] == "no-store"


async def test_adding_a_product_returns_the_cart_with_totals_and_the_image(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.put(ITEM, json={"quantity": 2}, headers=customer)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "items": [
            {
                "sku": "RS-001",
                "name": "Running Shoes",
                "quantity": 2,
                "price": "89.99",
                "line_total": "179.98",
                "thumbnail_url": THUMBNAIL,
                "flags": [],
            }
        ],
        "item_count": 2,
        "subtotal": "179.98",
    }


async def test_a_product_without_an_image_has_no_thumbnail(
    issuer: StubTokenIssuer, stores: Stores
) -> None:
    app = build_test_app(issuer, stores, FakeCatalog(product(image_key=None)))
    async with http_client(app) as http:
        response = await http.put(ITEM, json={"quantity": 1}, headers=bearer(issuer))

    assert response.json()["items"][0]["thumbnail_url"] is None


async def test_the_sku_in_the_path_is_case_insensitive(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.put("/api/v1/cart/items/rs-001", json={"quantity": 1}, headers=customer)

    assert response.json()["items"][0]["sku"] == "RS-001"


async def test_the_cart_belongs_to_the_token_subject(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    ada, grace = bearer(issuer, uuid4()), bearer(issuer, uuid4())
    await client.put(ITEM, json={"quantity": 1}, headers=ada)

    assert (await client.get(CART, headers=grace)).json()["items"] == []
    assert len((await client.get(CART, headers=ada)).json()["items"]) == 1


@pytest.mark.parametrize("quantity", [0, -1, 100, 1.5, "2", None])
async def test_the_quantity_must_be_between_one_and_ninety_nine(
    client: httpx.AsyncClient, customer: dict[str, str], quantity: object
) -> None:
    response = await client.put(ITEM, json={"quantity": quantity}, headers=customer)

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["errors"][0]["location"].startswith("body.quantity")


async def test_ninety_nine_is_accepted(client: httpx.AsyncClient, customer: dict[str, str]) -> None:
    response = await client.put(ITEM, json={"quantity": 99}, headers=customer)

    assert response.json()["item_count"] == 99


async def test_unknown_fields_and_a_malformed_price_are_rejected(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    extra = await client.put(ITEM, json={"quantity": 1, "price": "1.00"}, headers=customer)
    precision = await client.put(
        ITEM, json={"quantity": 1, "accepted_price": "1.005"}, headers=customer
    )

    assert (extra.status_code, precision.status_code) == (422, 422)


async def test_an_unknown_product_is_a_404_problem(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.put("/api/v1/cart/items/NOPE-1", json={"quantity": 1}, headers=customer)

    assert response.status_code == 404
    assert response.json()["title"] == "Product not found"
    assert response.headers["content-type"] == "application/problem+json"


async def test_an_unavailable_catalog_is_a_503_problem_with_retry_after(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: FakeCatalog
) -> None:
    catalog.unavailable = True

    response = await client.put(ITEM, json={"quantity": 1}, headers=customer)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert response.json()["title"] == "Catalog unavailable"


async def test_the_one_hundred_and_first_product_is_a_clear_409(
    issuer: StubTokenIssuer, stores: Stores
) -> None:
    items = [product(sku=f"P-{number:03d}") for number in range(MAX_LINES + 1)]
    app = build_test_app(issuer, stores, FakeCatalog(*items))
    headers = bearer(issuer)
    async with http_client(app) as http:
        for item in items[:MAX_LINES]:
            await http.put(f"{CART}/items/{item.sku}", json={"quantity": 1}, headers=headers)
        refused = await http.put(
            f"{CART}/items/{items[-1].sku}", json={"quantity": 1}, headers=headers
        )
        known = await http.put(f"{CART}/items/P-000", json={"quantity": 2}, headers=headers)

    assert refused.status_code == 409
    assert refused.json()["code"] == "cart_full"
    assert refused.json()["limit"] == MAX_LINES
    assert known.status_code == 200


async def test_the_cart_flags_a_price_change_without_changing_the_line(
    client: httpx.AsyncClient, customer: dict[str, str], stores: Stores
) -> None:
    await client.put(ITEM, json={"quantity": 1}, headers=customer)
    await stores.projection.apply_state(product(price="79.90", version=2))

    body = (await client.get(CART, headers=customer)).json()

    assert body["items"][0]["price"] == "89.99"
    assert body["items"][0]["flags"] == [
        {"type": "price_changed", "old_price": "89.99", "new_price": "79.90", "available": None}
    ]


async def test_the_cart_flags_a_retired_product_and_missing_stock(
    client: httpx.AsyncClient, customer: dict[str, str], stores: Stores
) -> None:
    await client.put(ITEM, json={"quantity": 3}, headers=customer)
    await stores.projection.apply_state(product(stock=0, version=2))
    stock_flags = (await client.get(CART, headers=customer)).json()["items"][0]["flags"]
    await stores.projection.apply_deletion("RS-001", 3)

    gone_flags = (await client.get(CART, headers=customer)).json()["items"][0]["flags"]

    assert [flag["type"] for flag in stock_flags] == ["insufficient_stock"]
    assert stock_flags[0]["available"] == 0
    assert [flag["type"] for flag in gone_flags] == ["unavailable"]


async def test_accepting_the_price_updates_the_line(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: FakeCatalog
) -> None:
    await client.put(ITEM, json={"quantity": 2}, headers=customer)
    catalog.add(product(price="79.90", version=2))

    response = await client.put(
        ITEM, json={"quantity": 2, "accepted_price": "79.90"}, headers=customer
    )

    line = response.json()["items"][0]
    assert (line["price"], line["flags"], response.json()["subtotal"]) == ("79.90", [], "159.80")


async def test_accepting_a_stale_price_is_a_409_with_the_current_price(
    client: httpx.AsyncClient, customer: dict[str, str], catalog: FakeCatalog
) -> None:
    await client.put(ITEM, json={"quantity": 1}, headers=customer)
    catalog.add(product(price="60.00", version=3))

    response = await client.put(
        ITEM, json={"quantity": 1, "accepted_price": "79.90"}, headers=customer
    )

    assert response.status_code == 409
    assert response.json()["code"] == "price_changed"
    assert Decimal(response.json()["current_price"]) == Decimal("60.00")
    assert response.headers["content-type"] == "application/problem+json"


async def test_deleting_an_item_returns_the_remaining_cart(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    await client.put(ITEM, json={"quantity": 1}, headers=customer)

    first = await client.delete(ITEM, headers=customer)
    second = await client.delete(ITEM, headers=customer)

    assert first.status_code == second.status_code == 200
    assert first.json() == {"items": [], "item_count": 0, "subtotal": "0.00"}


async def test_deleting_a_malformed_sku_is_a_404(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.delete("/api/v1/cart/items/--", headers=customer)

    assert response.status_code == 404


async def test_clearing_the_cart_is_a_204(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    await client.put(ITEM, json={"quantity": 1}, headers=customer)

    cleared = await client.delete(CART, headers=customer)

    assert cleared.status_code == 204
    assert cleared.content == b""
    assert (await client.get(CART, headers=customer)).json()["item_count"] == 0


async def test_health_and_the_documented_routes(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    schema = (await client.get("/openapi.json")).json()

    assert health.status_code == 200
    assert set(schema["paths"]) >= {"/api/v1/cart", "/api/v1/cart/items/{sku}", "/health", "/ready"}
