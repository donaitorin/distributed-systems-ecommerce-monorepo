from uuid import uuid4

import httpx
import pytest
from accounts_testing.data import ADDRESS
from accounts_testing.support import bearer

from ecommerce_auth.testing import StubTokenIssuer

ADDRESSES = "/api/v1/accounts/me/addresses"

MINIMAL = {
    "recipient_name": "Ada",
    "line1": "1 Main St",
    "city": "Madrid",
    "postal_code": "28001",
    "country": "es",
}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", ADDRESSES),
        ("POST", ADDRESSES),
        ("DELETE", f"{ADDRESSES}/{uuid4()}"),
    ],
)
async def test_every_address_endpoint_requires_a_token(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, path, json=ADDRESS if method == "POST" else None)

    assert response.status_code == 401


async def test_a_new_user_has_no_addresses(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(ADDRESSES, headers=bearer(issuer))

    assert response.status_code == 200
    assert response.json() == {"items": []}
    assert response.headers["cache-control"] == "no-store"


async def test_an_address_is_created_and_listed(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)

    created = await client.post(ADDRESSES, json=ADDRESS, headers=headers)
    listed = await client.get(ADDRESSES, headers=headers)

    assert created.status_code == 201
    body = created.json()
    assert {key: body[key] for key in ADDRESS} == ADDRESS
    assert listed.json()["items"] == [body]


async def test_optional_fields_default_to_null_and_the_country_is_uppercased(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.post(ADDRESSES, json=MINIMAL, headers=bearer(issuer))

    body = response.json()
    assert body["country"] == "ES"
    assert (body["line2"], body["region"], body["phone"]) == (None, None, None)


async def test_blank_optional_fields_become_null_and_text_is_trimmed(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    payload = MINIMAL | {"line2": "  ", "region": "", "phone": " ", "city": "  Madrid  "}

    body = (await client.post(ADDRESSES, json=payload, headers=bearer(issuer))).json()

    assert (body["line2"], body["region"], body["phone"], body["city"]) == (
        None,
        None,
        None,
        "Madrid",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("recipient_name", ""),
        ("recipient_name", "x" * 101),
        ("line1", "  "),
        ("line1", "x" * 201),
        ("line2", "x" * 201),
        ("city", ""),
        ("region", "x" * 101),
        ("postal_code", ""),
        ("postal_code", "x" * 21),
        ("country", "ESP"),
        ("country", "E"),
        ("country", "E1"),
        ("country", ""),
        ("phone", "12345"),
    ],
)
async def test_invalid_address_fields_are_rejected_with_their_location(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, field: str, value: str
) -> None:
    response = await client.post(ADDRESSES, json=MINIMAL | {field: value}, headers=bearer(issuer))

    assert response.status_code == 422
    assert f"body.{field}" in [problem["location"] for problem in response.json()["errors"]]


@pytest.mark.parametrize("field", ["recipient_name", "line1", "city", "postal_code", "country"])
async def test_required_address_fields_are_reported_when_missing(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, field: str
) -> None:
    payload = {key: value for key, value in MINIMAL.items() if key != field}

    response = await client.post(ADDRESSES, json=payload, headers=bearer(issuer))

    assert response.status_code == 422
    assert f"body.{field}" in [problem["location"] for problem in response.json()["errors"]]


async def test_all_problems_are_reported_at_once(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.post(ADDRESSES, json={}, headers=bearer(issuer))

    assert len(response.json()["errors"]) == 5


async def test_the_eleventh_address_is_a_conflict(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    for _ in range(10):
        assert (await client.post(ADDRESSES, json=MINIMAL, headers=headers)).status_code == 201

    response = await client.post(ADDRESSES, json=MINIMAL, headers=headers)

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    assert len((await client.get(ADDRESSES, headers=headers)).json()["items"]) == 10


async def test_deleting_an_address_removes_it_for_good(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    address_id = (await client.post(ADDRESSES, json=ADDRESS, headers=headers)).json()["id"]

    deleted = await client.delete(f"{ADDRESSES}/{address_id}", headers=headers)
    again = await client.delete(f"{ADDRESSES}/{address_id}", headers=headers)

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert again.status_code == 404
    assert (await client.get(ADDRESSES, headers=headers)).json() == {"items": []}


async def test_another_users_address_cannot_be_seen_or_deleted(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    owner, stranger = bearer(issuer, uuid4()), bearer(issuer, uuid4())
    address_id = (await client.post(ADDRESSES, json=ADDRESS, headers=owner)).json()["id"]

    assert (await client.get(ADDRESSES, headers=stranger)).json() == {"items": []}
    assert (await client.delete(f"{ADDRESSES}/{address_id}", headers=stranger)).status_code == 404
    assert len((await client.get(ADDRESSES, headers=owner)).json()["items"]) == 1


async def test_a_malformed_address_id_is_a_validation_error(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.delete(f"{ADDRESSES}/not-a-uuid", headers=bearer(issuer))

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "path.address_id"
