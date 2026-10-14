from typing import Any

import httpx
import pytest
from catalog_testing.support import SteppingClock, valid_product

URL = "/api/v1/products/RS-001"


def replacement(**overrides: Any) -> dict[str, Any]:
    body = valid_product(name="Trail Shoes", price="99.50", stock=3)
    del body["sku"]
    return body | overrides


@pytest.fixture
async def seeded(client: httpx.AsyncClient, admin: dict[str, str]) -> None:
    response = await client.post("/api/v1/products", json=valid_product(), headers=admin)
    assert response.headers["ETag"] == '"1"'


async def put(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    if_match: str | None = '"1"',
    body: dict[str, Any] | None = None,
) -> httpx.Response:
    request_headers = headers | ({"If-Match": if_match} if if_match is not None else {})
    return await client.put(URL, json=body or replacement(), headers=request_headers)


@pytest.mark.usefixtures("seeded")
class TestReplace:
    async def test_requires_a_token(self, client: httpx.AsyncClient) -> None:
        response = await client.put(URL, json=replacement(), headers={"If-Match": '"1"'})

        assert response.status_code == 401

    async def test_is_forbidden_for_customers(
        self, client: httpx.AsyncClient, customer: dict[str, str]
    ) -> None:
        assert (await put(client, customer)).status_code == 403

    async def test_without_if_match_is_428(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await put(client, admin, if_match=None)

        assert response.status_code == 428
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["title"] == "Precondition required"
        assert (await client.get(URL)).json()["name"] == "Running Shoes"

    async def test_with_the_current_etag_replaces_everything(
        self, client: httpx.AsyncClient, admin: dict[str, str], clock: SteppingClock
    ) -> None:
        before = (await client.get(URL)).json()
        clock.advance()

        response = await put(client, admin, body=replacement(description=None, weight_kg=None))

        body = response.json()
        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert body["version"] == 2
        assert body["name"] == "Trail Shoes"
        assert body["price"] == "99.50"
        assert body["stock"] == 3
        assert body["description"] is None
        assert body["weight_kg"] is None
        assert body["created_at"] == before["created_at"]
        assert body["updated_at"] > before["updated_at"]
        assert (await client.get(URL)).headers["ETag"] == '"2"'

    async def test_with_a_stale_etag_is_412_and_changes_nothing(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        await put(client, admin, '"1"')

        response = await put(client, admin, '"1"', replacement(name="Lost update"))

        assert response.status_code == 412
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.json()["title"] == "Precondition failed"
        current = (await client.get(URL)).json()
        assert current["name"] == "Trail Shoes"
        assert current["version"] == 2

    @pytest.mark.parametrize("header", ['"1"', 'W/"1"', '"7", "1"', "*"])
    async def test_accepted_if_match_forms(
        self, client: httpx.AsyncClient, admin: dict[str, str], header: str
    ) -> None:
        assert (await put(client, admin, header)).status_code == 200

    @pytest.mark.parametrize("header", ['"2"', "1", "garbage", '""', "", "v1"])
    async def test_rejected_if_match_forms(
        self, client: httpx.AsyncClient, admin: dict[str, str], header: str
    ) -> None:
        assert (await put(client, admin, header)).status_code == 412

    async def test_two_editors_the_second_one_loses(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        etag = (await client.get(URL)).headers["ETag"]

        first = await put(client, admin, etag, replacement(stock=10))
        second = await put(client, admin, etag, replacement(stock=99))

        assert (first.status_code, second.status_code) == (200, 412)
        assert (await client.get(URL)).json()["stock"] == 10

    async def test_validation_errors_are_422_and_do_not_bump_the_version(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await put(client, admin, body=replacement(price="-1"))

        assert response.status_code == 422
        assert (await client.get(URL)).json()["version"] == 1

    async def test_sku_in_the_body_is_rejected(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await put(client, admin, body=replacement(sku="OTHER-1"))

        assert response.status_code == 422

    async def test_unknown_category_is_a_422(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await put(
            client, admin, body=replacement(category_id="00000000-0000-4000-8000-0000000000ff")
        )

        assert response.status_code == 422
        assert response.json()["errors"][0]["location"] == "body.category_id"

    async def test_unknown_sku_is_404(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/v1/products/NOPE", json=replacement(), headers=admin | {"If-Match": "*"}
        )

        assert response.status_code == 404

    async def test_sku_is_case_insensitive_in_the_path(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await client.put(
            "/api/v1/products/rs-001", json=replacement(), headers=admin | {"If-Match": '"1"'}
        )

        assert response.status_code == 200


@pytest.mark.usefixtures("seeded")
class TestDelete:
    async def test_requires_a_token(self, client: httpx.AsyncClient) -> None:
        response = await client.delete(URL, headers={"If-Match": '"1"'})

        assert response.status_code == 401

    async def test_is_forbidden_for_customers(
        self, client: httpx.AsyncClient, customer: dict[str, str]
    ) -> None:
        response = await client.delete(URL, headers=customer | {"If-Match": '"1"'})

        assert response.status_code == 403
        assert (await client.get(URL)).status_code == 200

    async def test_without_if_match_is_428(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await client.delete(URL, headers=admin)

        assert response.status_code == 428
        assert (await client.get(URL)).status_code == 200

    async def test_with_the_current_etag_returns_204_and_hides_the_product(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await client.delete(URL, headers=admin | {"If-Match": '"1"'})

        assert response.status_code == 204
        assert response.content == b""
        assert (await client.get(URL)).status_code == 404
        assert (await client.get("/api/v1/products")).json()["items"] == []

    async def test_with_a_stale_etag_is_412_and_keeps_the_product(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        await put(client, admin, '"1"')

        response = await client.delete(URL, headers=admin | {"If-Match": '"1"'})

        assert response.status_code == 412
        assert (await client.get(URL)).status_code == 200

    async def test_wildcard_deletes_regardless_of_version(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        await put(client, admin, '"1"')

        response = await client.delete(URL, headers=admin | {"If-Match": "*"})

        assert response.status_code == 204

    async def test_deleting_twice_is_404_the_second_time(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        await client.delete(URL, headers=admin | {"If-Match": "*"})

        response = await client.delete(URL, headers=admin | {"If-Match": "*"})

        assert response.status_code == 404

    async def test_a_deleted_product_cannot_be_replaced(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        await client.delete(URL, headers=admin | {"If-Match": "*"})

        assert (await put(client, admin, "*")).status_code == 404

    async def test_unknown_sku_is_404(
        self, client: httpx.AsyncClient, admin: dict[str, str]
    ) -> None:
        response = await client.delete("/api/v1/products/NOPE", headers=admin | {"If-Match": "*"})

        assert response.status_code == 404
