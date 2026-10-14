from typing import Any
from uuid import uuid4

import httpx
import pytest
from catalog_testing.support import valid_product

URL = "/api/v1/products"


async def post(
    client: httpx.AsyncClient, headers: dict[str, str], body: dict[str, Any] | None = None
) -> httpx.Response:
    return await client.post(URL, json=body or valid_product(), headers=headers)


def problem_locations(response: httpx.Response) -> set[str]:
    return {item["location"] for item in response.json()["errors"]}


async def test_creating_requires_a_token(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json=valid_product())

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_creating_rejects_an_invalid_token(client: httpx.AsyncClient) -> None:
    response = await client.post(
        URL, json=valid_product(), headers={"Authorization": "Bearer not-a-jwt"}
    )

    assert response.status_code == 401


async def test_creating_is_forbidden_for_customers(
    client: httpx.AsyncClient, customer: dict[str, str]
) -> None:
    response = await post(client, customer)

    assert response.status_code == 403
    assert response.json()["title"] == "Insufficient permissions"
    assert (await client.get(f"{URL}/RS-001")).status_code == 404


async def test_authentication_is_checked_before_the_body(client: httpx.AsyncClient) -> None:
    response = await client.post(URL, json={"garbage": True})

    assert response.status_code == 401


async def test_create_returns_201_with_location_and_etag(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await post(client, admin, valid_product(sku="rs-001", price=89.9))

    body = response.json()
    assert response.status_code == 201
    assert response.headers["Location"] == "/api/v1/products/RS-001"
    assert response.headers["ETag"] == '"1"'
    assert body["sku"] == "RS-001"
    assert body["price"] == "89.90"
    assert body["version"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"price": "0.00"},
        {"price": 0},
        {"stock": 0},
        {"weight_kg": 0},
        {"weight_kg": None},
        {"description": None},
        {"description": ""},
        {"name": "x" * 255},
        {"price": "9999999999.99"},
        {"stock": 2147483647},
    ],
)
async def test_boundary_values_are_accepted(
    client: httpx.AsyncClient, admin: dict[str, str], overrides: dict[str, Any]
) -> None:
    response = await post(client, admin, valid_product(**overrides))

    assert response.status_code == 201


async def test_optional_fields_can_be_left_out(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await post(
        client, admin, {"sku": "MIN-1", "name": "Minimal", "price": "1", "stock": 0}
    )

    body = response.json()
    assert response.status_code == 201
    assert body["description"] is None
    assert body["weight_kg"] is None
    assert body["category"] is None


@pytest.mark.parametrize(
    ("overrides", "location"),
    [
        ({"price": "-0.01"}, "body.price"),
        ({"price": "1.234"}, "body.price"),
        ({"price": "10000000000.00"}, "body.price"),
        ({"price": "free"}, "body.price"),
        ({"price": "NaN"}, "body.price"),
        ({"price": None}, "body.price"),
        ({"stock": -5}, "body.stock"),
        ({"stock": "10"}, "body.stock"),
        ({"stock": 1.5}, "body.stock"),
        ({"stock": True}, "body.stock"),
        ({"stock": 2147483648}, "body.stock"),
        ({"weight_kg": "-1"}, "body.weight_kg"),
        ({"weight_kg": "0.0001"}, "body.weight_kg"),
        ({"name": ""}, "body.name"),
        ({"name": "     "}, "body.name"),
        ({"name": "x" * 256}, "body.name"),
        ({"name": 42}, "body.name"),
        ({"description": "x" * 5001}, "body.description"),
        ({"sku": "has space"}, "body.sku"),
        ({"sku": ""}, "body.sku"),
        ({"sku": "x" * 65}, "body.sku"),
        ({"category_id": "not-a-uuid"}, "body.category_id"),
        ({"category_id": str(uuid4())}, "body.category_id"),
    ],
)
async def test_invalid_data_is_a_422_problem_naming_the_field(
    client: httpx.AsyncClient,
    admin: dict[str, str],
    overrides: dict[str, Any],
    location: str,
) -> None:
    response = await post(client, admin, valid_product(**overrides))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Request validation failed"
    assert problem_locations(response) == {location}
    assert (await client.get(f"{URL}/RS-001")).status_code == 404


async def test_all_problems_are_reported_in_one_response(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await post(
        client, admin, valid_product(name=" ", price="-1", stock=-1, weight_kg="-1", sku="bad sku")
    )

    assert problem_locations(response) == {
        "body.name",
        "body.price",
        "body.stock",
        "body.weight_kg",
        "body.sku",
    }


@pytest.mark.parametrize("missing", ["sku", "name", "price", "stock"])
async def test_required_fields_are_enforced(
    client: httpx.AsyncClient, admin: dict[str, str], missing: str
) -> None:
    body = valid_product()
    del body[missing]

    response = await post(client, admin, body)

    assert response.status_code == 422
    assert problem_locations(response) == {f"body.{missing}"}


@pytest.mark.parametrize("field", ["id", "version", "created_at", "image_key", "prize"])
async def test_unknown_or_read_only_fields_are_rejected(
    client: httpx.AsyncClient, admin: dict[str, str], field: str
) -> None:
    response = await post(client, admin, valid_product(**{field: "x"}))

    assert response.status_code == 422
    assert problem_locations(response) == {f"body.{field}"}


async def test_malformed_json_is_a_422_problem(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    response = await client.post(
        URL, content="{not json", headers=admin | {"Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize("sku", ["RS-001", "rs-001", " rs-001 "])
async def test_duplicate_sku_is_a_409_ignoring_case(
    client: httpx.AsyncClient, admin: dict[str, str], sku: str
) -> None:
    await post(client, admin)

    response = await post(client, admin, valid_product(sku=sku, name="Other"))

    assert response.status_code == 409
    assert response.json()["title"] == "SKU already exists"
    assert (await client.get(f"{URL}/RS-001")).json()["name"] == "Running Shoes"


async def test_a_deleted_sku_still_conflicts(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    await post(client, admin)
    await client.delete(f"{URL}/RS-001", headers=admin | {"If-Match": "*"})

    response = await post(client, admin)

    assert response.status_code == 409


async def test_a_known_category_can_be_assigned(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    category = (await client.get("/api/v1/categories")).json()[0]

    response = await post(client, admin, valid_product(category_id=category["id"]))

    assert response.json()["category"]["slug"] == category["slug"]


async def test_the_same_name_may_be_used_by_different_skus(
    client: httpx.AsyncClient, admin: dict[str, str]
) -> None:
    first = await post(client, admin, valid_product(sku="RS-001"))
    second = await post(client, admin, valid_product(sku="RS-050"))

    assert (first.status_code, second.status_code) == (201, 201)
