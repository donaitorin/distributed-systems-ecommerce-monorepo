from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from accounts_testing.data import SteppingClock
from accounts_testing.support import bearer

from accounts.infra.memory import InMemoryStore
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer

DIRECTORY = "/api/v1/accounts"
ME = f"{DIRECTORY}/me"


async def seed(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock, count: int = 7
) -> None:
    for number in range(count):
        role = Role.ADMIN if number % 3 == 0 else Role.CUSTOMER
        await client.get(ME, headers=bearer(issuer, role=role, email=f"User{number}@example.com"))
        clock.advance(seconds=1)


def admin(issuer: StubTokenIssuer) -> dict[str, str]:
    return bearer(issuer, role=Role.ADMIN, email="boss@example.com")


async def test_the_directory_requires_a_token(client: httpx.AsyncClient) -> None:
    assert (await client.get(DIRECTORY)).status_code == 401


async def test_a_customer_cannot_list_profiles(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(DIRECTORY, headers=bearer(issuer))

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_an_admin_lists_profiles_newest_first(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock
) -> None:
    await seed(client, issuer, clock)

    response = await client.get(DIRECTORY, headers=admin(issuer))

    assert response.status_code == 200
    body = response.json()
    assert [item["email"] for item in body["items"]] == [
        f"user{n}@example.com" for n in range(6, -1, -1)
    ]
    assert body["next_cursor"] is None
    assert set(body["items"][0]) == {
        "user_id",
        "email",
        "role",
        "name",
        "phone",
        "created_at",
        "updated_at",
    }


async def test_the_admin_listing_does_not_create_the_admins_own_profile(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    await client.get(DIRECTORY, headers=admin(issuer))

    assert store.profiles == {}


async def test_the_email_filter_is_a_case_insensitive_prefix(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock
) -> None:
    await seed(client, issuer, clock)
    await client.get(ME, headers=bearer(issuer, email="grace@example.com"))

    response = await client.get(DIRECTORY, params={"email": "USER"}, headers=admin(issuer))
    nothing = await client.get(DIRECTORY, params={"email": "ser"}, headers=admin(issuer))

    assert len(response.json()["items"]) == 7
    assert nothing.json()["items"] == []


async def test_the_role_filter_returns_only_that_role(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock
) -> None:
    await seed(client, issuer, clock)

    response = await client.get(DIRECTORY, params={"role": "admin"}, headers=admin(issuer))

    assert {item["role"] for item in response.json()["items"]} == {"admin"}
    assert len(response.json()["items"]) == 3


async def test_an_unknown_role_filter_is_a_validation_error(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(DIRECTORY, params={"role": "root"}, headers=admin(issuer))

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "query.role"


@pytest.mark.parametrize("limit", ["0", "10", "26", "101", "abc"])
async def test_only_the_documented_page_sizes_are_accepted(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, limit: str
) -> None:
    response = await client.get(DIRECTORY, params={"limit": limit}, headers=admin(issuer))

    assert response.status_code == 422
    assert response.json()["errors"][0]["location"] == "query.limit"


@pytest.mark.parametrize("limit", ["25", "50", "100"])
async def test_the_documented_page_sizes_are_accepted(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, limit: str
) -> None:
    assert (
        await client.get(DIRECTORY, params={"limit": limit}, headers=admin(issuer))
    ).status_code == 200


async def test_the_cursor_walks_every_profile_once(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock
) -> None:
    await seed(client, issuer, clock, count=60)
    seen: list[str] = []
    cursor: str | None = None

    for _ in range(5):
        params = {"limit": "25"} | ({"cursor": cursor} if cursor else {})
        body = (await client.get(DIRECTORY, params=params, headers=admin(issuer))).json()
        seen.extend(item["user_id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == 60
    assert len(set(seen)) == 60


async def test_a_malformed_cursor_is_a_validation_error(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get(DIRECTORY, params={"cursor": "garbage"}, headers=admin(issuer))

    assert response.status_code == 422
    problem = response.json()["errors"][0]
    assert (problem["location"], problem["type"]) == ("query.cursor", "invalid_cursor")


async def test_a_cursor_reused_with_other_filters_is_a_mismatch(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, clock: SteppingClock
) -> None:
    await seed(client, issuer, clock, count=30)
    first = await client.get(DIRECTORY, headers=admin(issuer))
    cursor = first.json()["next_cursor"]

    response = await client.get(
        DIRECTORY, params={"cursor": cursor, "role": "admin"}, headers=admin(issuer)
    )

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "cursor_mismatch"


async def test_a_role_change_event_is_visible_in_the_listing(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, store: InMemoryStore
) -> None:
    user_id = uuid4()
    await client.get(ME, headers=bearer(issuer, user_id))
    store.profiles[user_id] = replace(store.profiles[user_id], role="admin")

    response = await client.get(DIRECTORY, params={"role": "admin"}, headers=admin(issuer))

    assert [item["user_id"] for item in response.json()["items"]] == [str(user_id)]
