import asyncio
import time
from uuid import UUID, uuid4

import httpx
import pytest
from accounts_testing.support import bearer

from accounts.infra.memory import InMemoryStore
from ecommerce_auth import DEFAULT_AUDIENCE, Role
from ecommerce_auth.testing import STUB_ISSUER, StubTokenIssuer

ME = "/api/v1/accounts/me"


async def test_me_requires_a_token(client: httpx.AsyncClient) -> None:
    response = await client.get(ME)

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_me_rejects_a_token_whose_subject_is_not_a_uuid(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = {"Authorization": f"Bearer {issuer.issue(subject='user-1')}"}

    response = await client.get(ME, headers=headers)

    assert response.status_code == 401


async def test_the_first_me_request_creates_the_profile_from_the_token(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    user_id = uuid4()

    response = await client.get(ME, headers=bearer(issuer, user_id, email="Ada@example.com"))

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["email"] == "ada@example.com"
    assert body["role"] == "customer"
    assert (body["name"], body["phone"]) == (None, None)
    assert response.headers["cache-control"] == "no-store"
    assert len(store.profiles) == 1


async def test_a_token_without_an_email_creates_a_profile_with_no_email(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(ME, headers=bearer(issuer, email=None))

    assert response.status_code == 200
    assert response.json()["email"] is None


async def test_an_admin_without_a_registration_event_works_through_the_lazy_path(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(ME, headers=bearer(issuer, role=Role.ADMIN))

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_the_lazy_path_stamps_the_role_with_the_token_issue_time(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    user_id = uuid4()

    await client.get(ME, headers=bearer(issuer, user_id, iat=1_700_000_000))

    role_time = store.profiles[user_id].role_updated_at
    assert role_time is not None
    assert int(role_time.timestamp()) == 1_700_000_000


async def test_a_token_without_an_issue_time_stores_no_role_time(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    user_id = uuid4()
    token = issuer.issue_with_claims(
        {
            "sub": str(user_id),
            "role": "customer",
            "aud": DEFAULT_AUDIENCE,
            "iss": STUB_ISSUER,
            "exp": int(time.time()) + 300,
        }
    )

    response = await client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert store.profiles[user_id].role_updated_at is None


async def test_a_later_token_never_overwrites_the_stored_profile(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    user_id = uuid4()
    await client.get(ME, headers=bearer(issuer, user_id, email="ada@example.com"))

    response = await client.get(
        ME, headers=bearer(issuer, user_id, role=Role.ADMIN, email="other@example.com")
    )

    assert response.json()["email"] == "ada@example.com"
    assert response.json()["role"] == "customer"


async def test_concurrent_first_requests_leave_one_profile(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    headers = bearer(issuer, uuid4())

    responses = await asyncio.gather(*(client.get(ME, headers=headers) for _ in range(20)))

    assert {response.status_code for response in responses} == {200}
    assert len(store.profiles) == 1


async def test_patch_sets_the_name_and_phone(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)

    response = await client.patch(
        ME, json={"name": "  Ada Lovelace ", "phone": "+34 600-111-222"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Ada Lovelace"
    assert response.json()["phone"] == "+34600111222"
    assert (await client.get(ME, headers=headers)).json()["name"] == "Ada Lovelace"


async def test_patch_creates_the_profile_when_it_is_the_first_request(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    response = await client.patch(ME, json={"name": "Ada"}, headers=bearer(issuer))

    assert response.status_code == 200
    assert len(store.profiles) == 1


async def test_patch_with_null_clears_the_phone_and_keeps_the_name(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    await client.patch(ME, json={"name": "Ada", "phone": "+34600111222"}, headers=headers)

    response = await client.patch(ME, json={"phone": None}, headers=headers)

    assert (response.json()["name"], response.json()["phone"]) == ("Ada", None)


async def test_patch_leaves_omitted_fields_alone(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    await client.patch(ME, json={"name": "Ada", "phone": "+34600111222"}, headers=headers)

    response = await client.patch(ME, json={"name": "Grace"}, headers=headers)

    assert (response.json()["name"], response.json()["phone"]) == ("Grace", "+34600111222")


async def test_an_empty_patch_is_accepted_and_changes_nothing(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer)
    before = (await client.get(ME, headers=headers)).json()

    response = await client.patch(ME, json={}, headers=headers)

    assert response.status_code == 200
    assert response.json() == before


async def test_a_blank_phone_clears_it(client: httpx.AsyncClient, issuer: StubTokenIssuer) -> None:
    headers = bearer(issuer)
    await client.patch(ME, json={"phone": "+34600111222"}, headers=headers)

    response = await client.patch(ME, json={"phone": "   "}, headers=headers)

    assert response.json()["phone"] is None


@pytest.mark.parametrize(
    ("body", "location"),
    [
        ({"name": ""}, "body.name"),
        ({"name": "   "}, "body.name"),
        ({"name": "x" * 101}, "body.name"),
        ({"name": None}, "body.name"),
        ({"name": 5}, "body.name"),
        ({"phone": "600111222"}, "body.phone"),
        ({"phone": "+1234567"}, "body.phone"),
        ({"phone": "+1234567890123456"}, "body.phone"),
        ({"phone": "+12ab5678901"}, "body.phone"),
    ],
)
async def test_patch_rejects_invalid_values_with_field_locations(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, body: dict[str, object], location: str
) -> None:
    response = await client.patch(ME, json=body, headers=bearer(issuer))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert location in [problem["location"] for problem in response.json()["errors"]]


@pytest.mark.parametrize("name", ["A", "x" * 100])
async def test_name_boundaries_are_accepted(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, name: str
) -> None:
    response = await client.patch(ME, json={"name": name}, headers=bearer(issuer))

    assert response.status_code == 200


@pytest.mark.parametrize("phone", ["+12345678", "+123456789012345"])
async def test_phone_boundaries_are_accepted(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, phone: str
) -> None:
    response = await client.patch(ME, json={"phone": phone}, headers=bearer(issuer))

    assert response.status_code == 200


async def test_profiles_are_isolated_between_users(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    ada, grace = bearer(issuer, uuid4()), bearer(issuer, uuid4(), email="grace@example.com")
    await client.patch(ME, json={"name": "Ada"}, headers=ada)

    assert (await client.get(ME, headers=grace)).json()["name"] is None


def user_id_of(response: httpx.Response) -> UUID:
    return UUID(response.json()["user_id"])
