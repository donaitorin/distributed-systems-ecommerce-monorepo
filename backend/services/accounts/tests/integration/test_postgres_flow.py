import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from accounts_testing.data import ADDRESS
from accounts_testing.support import accounts_settings, bearer, http_client
from sqlalchemy import text

from accounts.infra.database import create_engine
from accounts.main import create_accounts_app
from ecommerce_auth import Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier

pytestmark = pytest.mark.integration

ME = "/api/v1/accounts/me"


@pytest.fixture(scope="module")
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
async def live_client(
    migrated_database_url: str, issuer: StubTokenIssuer
) -> AsyncIterator[httpx.AsyncClient]:
    engine = create_engine(migrated_database_url)
    app = create_accounts_app(accounts_settings(), engine)
    app.state.token_verifier = build_stub_verifier(issuer)
    async with http_client(app) as client:
        yield client
    await engine.dispose()


async def count_profiles(url: str, user_id: object) -> int:
    engine = create_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT count(*) FROM profiles WHERE user_id = :id"), {"id": user_id}
            )
            return int(result.scalar_one())
    finally:
        await engine.dispose()


async def test_concurrent_first_requests_create_exactly_one_profile(
    live_client: httpx.AsyncClient, issuer: StubTokenIssuer, migrated_database_url: str
) -> None:
    user_id = uuid4()
    headers = bearer(issuer, user_id)

    responses = await asyncio.gather(*(live_client.get(ME, headers=headers) for _ in range(25)))

    assert {response.status_code for response in responses} == {200}
    assert len({response.json()["created_at"] for response in responses}) == 1
    assert await count_profiles(migrated_database_url, user_id) == 1


async def test_concurrent_address_creation_never_exceeds_the_limit(
    live_client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer, uuid4())

    responses = await asyncio.gather(
        *(live_client.post(f"{ME}/addresses", json=ADDRESS, headers=headers) for _ in range(15))
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [201] * 10 + [409] * 5
    assert len((await live_client.get(f"{ME}/addresses", headers=headers)).json()["items"]) == 10


async def test_profile_and_address_round_trip_on_postgres(
    live_client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    headers = bearer(issuer, uuid4(), email="roundtrip@example.com")

    patched = await live_client.patch(
        ME, json={"name": "Ada Lovelace", "phone": "+34600111222"}, headers=headers
    )
    created = await live_client.post(f"{ME}/addresses", json=ADDRESS, headers=headers)
    deleted = await live_client.delete(f"{ME}/addresses/{created.json()['id']}", headers=headers)

    assert patched.json()["name"] == "Ada Lovelace"
    assert created.status_code == 201
    assert deleted.status_code == 204


async def test_the_admin_directory_filters_and_pages_on_postgres(
    live_client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    tag = uuid4().hex[:10]
    for number in range(30):
        role = Role.ADMIN if number % 10 == 0 else Role.CUSTOMER
        await live_client.get(
            ME, headers=bearer(issuer, role=role, email=f"{tag.upper()}-{number}@example.com")
        )
    admin = bearer(issuer, role=Role.ADMIN)

    first = await live_client.get("/api/v1/accounts", params={"email": tag}, headers=admin)
    second = await live_client.get(
        "/api/v1/accounts",
        params={"email": tag, "cursor": first.json()["next_cursor"]},
        headers=admin,
    )
    admins = await live_client.get(
        "/api/v1/accounts", params={"email": tag, "role": "admin"}, headers=admin
    )

    assert len(first.json()["items"]) == 25
    assert len(second.json()["items"]) == 5
    assert second.json()["next_cursor"] is None
    assert len(admins.json()["items"]) == 3


async def test_ready_endpoint_is_green_with_a_reachable_database(
    migrated_database_url: str,
) -> None:
    engine = create_engine(migrated_database_url)
    app = create_accounts_app(accounts_settings(), engine)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/ready")
    finally:
        await engine.dispose()

    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok"}
