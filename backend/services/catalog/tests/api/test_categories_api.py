from typing import Any

import httpx
import pytest

URL = "/api/v1/categories"


async def test_listing_is_public_and_sorted_by_name_ignoring_case(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    await client.post(URL, json={"name": "aardvark supplies"}, headers=admin)

    response = await client.get(URL)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "aardvark supplies",
        "Books",
        "Electronics",
        "Home & Office",
    ]


async def test_each_category_exposes_id_name_and_slug(client: httpx.AsyncClient) -> None:
    item = (await client.get(URL)).json()[0]

    assert set(item) == {"id", "name", "slug"}


async def test_creating_requires_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.post(URL, json={"name": "Pets"})).status_code == 401


async def test_creating_is_forbidden_for_customers(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await client.post(URL, json={"name": "Pets"}, headers=customer)

    assert response.status_code == 403


async def test_admin_creates_a_category_with_a_derived_slug(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.post(URL, json={"name": "  Food &   Beverage "}, headers=admin)

    body = response.json()
    assert response.status_code == 201
    assert body["name"] == "Food & Beverage"
    assert body["slug"] == "food-beverage"
    assert body in (await client.get(URL)).json()


@pytest.mark.parametrize("name", ["electronics", "ELECTRONICS", "  Electronics ", "Home Office"])
async def test_duplicates_by_name_or_slug_are_409(
    client: httpx.AsyncClient, admin: dict[str, str], name: str
) -> None:
    response = await client.post(URL, json={"name": name}, headers=admin)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Category already exists"


@pytest.mark.parametrize(
    "body",
    [{"name": ""}, {"name": "   "}, {"name": "!!!"}, {"name": "x" * 101}, {}, {"name": 5}],
)
async def test_invalid_names_are_422(
    client: httpx.AsyncClient, admin: dict[str, str], body: dict[str, Any]
) -> None:
    response = await client.post(URL, json=body, headers=admin)

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "body.name"


async def test_unknown_fields_are_rejected(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.post(URL, json={"name": "Pets", "slug": "custom"}, headers=admin)

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "body.slug"
