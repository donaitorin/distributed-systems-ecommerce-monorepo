from decimal import Decimal
from typing import Any

import httpx
import pytest
from catalog_testing.support import SteppingClock, valid_product


async def create(client: httpx.AsyncClient, admin: dict[str, str], **overrides: object) -> None:
    response = await client.post("/api/v1/products", json=valid_product(**overrides), headers=admin)
    assert response.status_code == 201


async def category_id(client: httpx.AsyncClient, slug: str) -> str:
    categories = (await client.get("/api/v1/categories")).json()
    return str(next(item["id"] for item in categories if item["slug"] == slug))


@pytest.fixture
async def stocked(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> list[dict[str, Any]]:
    books = await category_id(client, "books")
    rows = [
        ("A-1", "Running Shoes", "89.99", 5, books),
        ("A-2", "Trail Running Shoes", "129.00", 0, books),
        ("A-3", "Coffee Mug", "9.50", 40, None),
        ("A-4", "Desk Lamp", "24.00", 3, None),
        ("A-5", "Running Socks", "9.75", 12, books),
    ]
    for sku, name, price, stock, category in rows:
        await create(
            client,
            admin,
            sku=sku,
            name=name,
            description=None,
            price=price,
            stock=stock,
            category_id=category,
        )
        clock.advance()
    response = await client.get("/api/v1/products", params={"limit": 48})
    return list(response.json()["items"])


def skus(response: httpx.Response) -> list[str]:
    return [item["sku"] for item in response.json()["items"]]


async def test_the_default_order_is_newest_first(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products")

    assert skus(response) == ["A-5", "A-4", "A-3", "A-2", "A-1"]
    assert response.json()["total"] == 5


async def test_sorting_by_price(client: httpx.AsyncClient, stocked: list[dict[str, Any]]) -> None:
    ascending = await client.get("/api/v1/products", params={"sort": "price_asc"})
    descending = await client.get("/api/v1/products", params={"sort": "price_desc"})

    assert skus(ascending) == ["A-3", "A-5", "A-4", "A-1", "A-2"]
    assert skus(descending) == ["A-2", "A-1", "A-4", "A-5", "A-3"]


async def test_filtering_by_category_slug(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"category": "books"})

    assert skus(response) == ["A-5", "A-2", "A-1"]


async def test_an_unknown_category_returns_an_empty_page_not_an_error(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"category": "does-not-exist"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


async def test_price_range_is_inclusive(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get(
        "/api/v1/products", params={"min_price": "9.50", "max_price": "24.00", "sort": "price_asc"}
    )

    assert skus(response) == ["A-3", "A-5", "A-4"]


async def test_in_stock_true_hides_sold_out_products(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"in_stock": "true"})

    assert "A-2" not in skus(response)
    assert response.json()["total"] == 4


@pytest.mark.parametrize("value", ["false", "0", "no"])
async def test_in_stock_false_is_the_same_as_omitting_the_filter(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]], value: str
) -> None:
    everything = await client.get("/api/v1/products")
    response = await client.get("/api/v1/products", params={"in_stock": value})

    assert skus(response) == skus(everything)


async def test_a_text_query_defaults_to_relevance(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"q": "running shoes"})

    assert skus(response)[0] == "A-1"
    assert set(skus(response)) == {"A-1", "A-2"}


async def test_a_blank_query_is_ignored(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"q": "   "})

    assert response.json()["total"] == 5


async def test_relevance_without_a_query_falls_back_to_newest(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    response = await client.get("/api/v1/products", params={"sort": "relevance"})

    assert skus(response) == ["A-5", "A-4", "A-3", "A-2", "A-1"]


async def test_every_sort_can_be_walked_in_both_directions(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> None:
    for index in range(30):
        await create(
            client,
            admin,
            sku=f"W-{index:02d}",
            name="Walker",
            price=str(Decimal(10 + index % 4)),
        )
        clock.advance(index % 3)

    for sort in ("newest", "price_asc", "price_desc"):
        pages = [await fetch_page(client, sort)]
        while pages[-1]["next_cursor"] is not None:
            pages.append(await fetch_page(client, sort, pages[-1]["next_cursor"]))
        forward = [item["sku"] for page in pages for item in page["items"]]

        back = [pages[-1]]
        while back[-1]["prev_cursor"] is not None:
            back.append(await fetch_page(client, sort, back[-1]["prev_cursor"]))
        backward = [item["sku"] for page in reversed(back) for item in page["items"]]

        assert len(forward) == len(set(forward)) == 30
        assert backward == forward


async def fetch_page(
    client: httpx.AsyncClient, sort: str, cursor: str | None = None
) -> dict[str, Any]:
    params = {"sort": sort, "limit": "12"}
    if cursor is not None:
        params["cursor"] = cursor
    page: dict[str, Any] = (await client.get("/api/v1/products", params=params)).json()
    return page


async def test_cursor_mismatch_is_reported_on_the_cursor_parameter(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> None:
    for index in range(14):
        await create(client, admin, sku=f"M-{index:02d}", name=f"Mug {index}")
        clock.advance()
    cursor = (await client.get("/api/v1/products", params={"limit": 12})).json()["next_cursor"]

    for params in (
        {"category": "books"},
        {"q": "mug"},
        {"min_price": "1"},
        {"max_price": "500"},
        {"in_stock": "true"},
        {"sort": "price_asc"},
    ):
        response = await client.get("/api/v1/products", params={"cursor": cursor} | params)

        assert response.status_code == 422, params
        assert response.headers["content-type"].startswith("application/problem+json")
        error = response.json()["errors"][0]
        assert (error["location"], error["type"]) == ("query.cursor", "cursor_mismatch")

    same = await client.get("/api/v1/products", params={"cursor": cursor, "limit": 12})
    assert same.status_code == 200


async def test_the_page_size_can_change_between_pages(
    client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
) -> None:
    for index in range(30):
        await create(client, admin, sku=f"S-{index:02d}")
        clock.advance()
    first = (await client.get("/api/v1/products", params={"limit": 12})).json()

    second = await client.get(
        "/api/v1/products", params={"limit": 24, "cursor": first["next_cursor"]}
    )

    assert second.status_code == 200
    assert len(second.json()["items"]) == 18


@pytest.mark.parametrize(
    ("params", "location"),
    [
        ({"sort": "alphabetical"}, "query.sort"),
        ({"min_price": "abc"}, "query.min_price"),
        ({"max_price": "abc"}, "query.max_price"),
        ({"min_price": "-1"}, "query.min_price"),
        ({"max_price": "1.234"}, "query.max_price"),
        ({"min_price": "NaN"}, "query.min_price"),
        ({"min_price": "20", "max_price": "10"}, "query.min_price"),
        ({"in_stock": "maybe"}, "query.in_stock"),
        ({"q": "x" * 101}, "query.q"),
        ({"category": "x" * 121}, "query.category"),
        ({"limit": "10"}, "query.limit"),
        ({"cursor": "garbage"}, "query.cursor"),
        ({"cursor": "x" * 513}, "query.cursor"),
    ],
)
async def test_invalid_parameters_are_422_problems_with_the_offending_location(
    client: httpx.AsyncClient, params: dict[str, str], location: str
) -> None:
    response = await client.get("/api/v1/products", params=params)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert location in [error["location"] for error in response.json()["errors"]]


async def test_a_malformed_cursor_is_reported_as_invalid(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/products", params={"cursor": "garbage"})

    assert response.json()["errors"][0]["type"] == "invalid_cursor"


async def test_the_response_keeps_the_original_fields_and_adds_the_new_ones(
    client: httpx.AsyncClient, stocked: list[dict[str, Any]]
) -> None:
    body = (await client.get("/api/v1/products")).json()

    assert {"items", "next_cursor"} <= set(body)
    assert {"prev_cursor", "total", "total_exact"} == set(body) - {"items", "next_cursor"}
    assert body["total_exact"] is True


async def test_the_openapi_document_describes_the_search_parameters(
    client: httpx.AsyncClient,
) -> None:
    document = (await client.get("/openapi.json")).json()

    operation = document["paths"]["/api/v1/products"]["get"]
    names = {parameter["name"] for parameter in operation["parameters"]}
    assert {
        "q",
        "category",
        "min_price",
        "max_price",
        "in_stock",
        "sort",
        "limit",
        "cursor",
    } <= names
    assert "in_stock=false" in operation["description"]
    in_stock = next(item for item in operation["parameters"] if item["name"] == "in_stock")
    assert "false" in in_stock["description"]
