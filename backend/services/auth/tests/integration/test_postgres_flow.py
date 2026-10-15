import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from auth_testing.support import (
    FAST_HASHING,
    STRONG_PASSWORD,
    SteppingClock,
    auth_settings,
    http_client,
    login_user,
    refresh_with,
    register_user,
    verifier_for,
)
from fastapi import FastAPI
from sqlalchemy import make_url, text

from auth.domain.user import Role
from auth.infra.database import create_engine
from auth.infra.hashing import Argon2idHasher, HashingSettings
from auth.infra.keys import KeyStore
from auth.main import create_auth_app
from auth.tools.seed import run
from ecommerce_auth import Role as LibRole

pytestmark = pytest.mark.integration


@pytest.fixture
async def flow_app(
    migrated_database_url: str, key_store: KeyStore, clock: SteppingClock
) -> AsyncIterator[FastAPI]:
    engine = create_engine(migrated_database_url)
    app = create_auth_app(
        auth_settings(),
        engine,
        clock=clock,
        keys=key_store,
        hasher=Argon2idHasher(FAST_HASHING),
    )
    yield app
    await engine.dispose()


@pytest.fixture
async def flow_client(flow_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with http_client(flow_app) as client:
        yield client


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}@example.com"


async def test_the_whole_session_lifecycle_works_against_postgres(
    flow_client: httpx.AsyncClient, key_store: KeyStore, clock: SteppingClock
) -> None:
    clock.now = datetime.now(UTC)
    email = unique_email("lifecycle")
    registered = await register_user(flow_client, email)
    assert registered.status_code == 201
    assert (await register_user(flow_client, email.upper())).status_code == 409

    tokens = (await login_user(flow_client, email)).json()
    user = await verifier_for(key_store.jwks_document()).verify(tokens["access_token"])
    assert user.user_id == registered.json()["id"]
    assert user.role is LibRole.CUSTOMER

    rotated = await refresh_with(flow_client, tokens["refresh_token"])
    assert rotated.status_code == 200

    logout = await flow_client.post(
        "/api/v1/auth/logout", json={"refresh_token": rotated.json()["refresh_token"]}
    )
    assert logout.status_code == 204
    assert (await refresh_with(flow_client, rotated.json()["refresh_token"])).status_code == 401


async def test_wrong_credentials_are_rejected_against_postgres(
    flow_client: httpx.AsyncClient,
) -> None:
    email = unique_email("wrong")
    await register_user(flow_client, email)

    wrong = await login_user(flow_client, email, "not the password")
    unknown = await login_user(flow_client, unique_email("ghost"))

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_two_simultaneous_refreshes_of_one_token_yield_one_winner_and_no_revocation(
    flow_client: httpx.AsyncClient,
) -> None:
    email = unique_email("race")
    await register_user(flow_client, email)
    first = (await login_user(flow_client, email)).json()

    responses = await asyncio.gather(
        *(refresh_with(flow_client, first["refresh_token"]) for _ in range(4))
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200, 401, 401, 401]
    winner = next(response for response in responses if response.status_code == 200)
    follow_up = await refresh_with(flow_client, winner.json()["refresh_token"])
    assert follow_up.status_code == 200


async def test_reuse_after_the_grace_window_revokes_the_family_in_postgres(
    flow_client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    email = unique_email("reuse")
    await register_user(flow_client, email)
    first = (await login_user(flow_client, email)).json()
    second = (await refresh_with(flow_client, first["refresh_token"])).json()
    clock.advance(seconds=11)

    replay = await refresh_with(flow_client, first["refresh_token"])
    descendant = await refresh_with(flow_client, second["refresh_token"])

    assert replay.status_code == 401
    assert descendant.status_code == 401


async def test_the_grace_window_in_postgres_does_not_revoke(
    flow_client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    email = unique_email("grace")
    await register_user(flow_client, email)
    first = (await login_user(flow_client, email)).json()
    second = (await refresh_with(flow_client, first["refresh_token"])).json()
    clock.advance(seconds=9)

    replay = await refresh_with(flow_client, first["refresh_token"])
    descendant = await refresh_with(flow_client, second["refresh_token"])

    assert replay.status_code == 401
    assert descendant.status_code == 200


async def test_an_expired_session_family_is_rejected_in_postgres(
    flow_client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    email = unique_email("expired")
    await register_user(flow_client, email)
    tokens = (await login_user(flow_client, email)).json()
    clock.advance(days=8)

    assert (await refresh_with(flow_client, tokens["refresh_token"])).status_code == 401


async def test_login_upgrades_a_weaker_password_hash_in_postgres(
    migrated_database_url: str, key_store: KeyStore, clock: SteppingClock
) -> None:
    engine = create_engine(migrated_database_url)
    weak = create_auth_app(
        auth_settings(), engine, clock=clock, keys=key_store, hasher=Argon2idHasher(FAST_HASHING)
    )
    email = unique_email("rehash")
    try:
        async with http_client(weak) as client:
            await register_user(client, email)
        stronger = Argon2idHasher(HashingSettings(memory_cost_kib=16, time_cost=2))
        upgraded = create_auth_app(
            auth_settings(), engine, clock=clock, keys=key_store, hasher=stronger
        )
        async with http_client(upgraded) as client:
            assert (await login_user(client, email)).status_code == 200
        async with engine.connect() as connection:
            stored = await connection.scalar(
                text("SELECT password_hash FROM users WHERE email = :email"), {"email": email}
            )
    finally:
        await engine.dispose()

    assert stored is not None
    assert "m=16,t=2" in stored


async def test_the_seed_creates_the_admin_once_and_never_overwrites_it(
    migrated_database_url: str,
) -> None:
    url = make_url(migrated_database_url)
    environ = {
        "AUTH_DB_HOST": url.host or "",
        "AUTH_DB_PORT": str(url.port),
        "AUTH_DB_NAME": url.database or "",
        "AUTH_DB_USER": url.username or "",
        "AUTH_DB_PASSWORD": url.password or "",
        "AUTH_ADMIN_EMAIL": "seed-admin@example.com",
        "AUTH_ADMIN_PASSWORD": STRONG_PASSWORD,
        "AUTH_ARGON2_MEMORY_KIB": "8",
        "AUTH_ARGON2_TIME_COST": "1",
    }

    first = await run(environ)
    second = await run(environ | {"AUTH_ADMIN_PASSWORD": "a different long passphrase"})

    assert (first, second) == (True, False)
    engine = create_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text("SELECT role, password_hash FROM users WHERE email = :email"),
                    {"email": "seed-admin@example.com"},
                )
            ).one()
    finally:
        await engine.dispose()
    assert row.role == Role.ADMIN.value
    assert row.password_hash.startswith("$argon2id$")
    assert await Argon2idHasher(FAST_HASHING).verify(row.password_hash, STRONG_PASSWORD)
