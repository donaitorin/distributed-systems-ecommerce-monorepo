from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
import pytest
from auth_testing.support import (
    AUDIENCE,
    ISSUER,
    STRONG_PASSWORD,
    SteppingClock,
    login_user,
    new_signing_key,
    patch_role,
    register_user,
)
from fastapi import FastAPI

from auth.application.registration import RegistrationService
from auth.domain.user import Role
from auth.infra.keys import KeyStore
from auth.infra.memory import InMemoryStore
from auth.infra.signer import JwtAccessTokenIssuer
from ecommerce_contracts import USER_ROLE_CHANGED, UserRoleChangedV1

ADMIN_EMAIL = "admin@example.com"


@pytest.fixture(autouse=True)
def real_time(clock: SteppingClock) -> None:
    clock.now = datetime.now(UTC)


async def admin_token(app: FastAPI, client: httpx.AsyncClient) -> str:
    registration: RegistrationService = app.state.registration_service
    await registration.register(ADMIN_EMAIL, STRONG_PASSWORD, uuid4(), Role.ADMIN)
    return str((await login_user(client, ADMIN_EMAIL)).json()["access_token"])


async def customer_token(client: httpx.AsyncClient, email: str = "ada@example.com") -> str:
    await register_user(client, email)
    return str((await login_user(client, email)).json()["access_token"])


async def test_an_admin_changes_a_customer_to_admin(
    app: FastAPI, client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    token = await admin_token(app, client)
    user_id = (await register_user(client)).json()["id"]

    response = await patch_role(client, user_id, "admin", token)

    assert response.status_code == 200
    assert response.json() == {"id": user_id, "email": "ada@example.com", "role": "admin"}
    event = store.outbox[-1]
    assert event.event_type == USER_ROLE_CHANGED
    assert isinstance(event.payload, UserRoleChangedV1)
    assert str(event.payload.user_id) == user_id


async def test_the_next_login_carries_the_new_role(app: FastAPI, client: httpx.AsyncClient) -> None:
    token = await admin_token(app, client)
    user_id = (await register_user(client)).json()["id"]
    await patch_role(client, user_id, "admin", token)

    access = (await login_user(client)).json()["access_token"]

    assert jwt.decode(access, options={"verify_signature": False})["role"] == "admin"


async def test_a_customer_cannot_change_roles(client: httpx.AsyncClient) -> None:
    token = await customer_token(client)
    target = (await register_user(client, "bob@example.com")).json()["id"]

    response = await patch_role(client, target, "admin", token)

    assert response.status_code == 403
    assert response.headers["content-type"] == "application/problem+json"


async def test_a_request_without_a_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    target = (await register_user(client)).json()["id"]

    response = await patch_role(client, target, "admin")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_a_token_signed_by_someone_else_is_unauthorized(
    client: httpx.AsyncClient,
) -> None:
    stranger = new_signing_key()
    issuer = JwtAccessTokenIssuer(
        KeyStore([stranger], stranger.kid), ISSUER, AUDIENCE, timedelta(minutes=5)
    )
    forged = issuer.issue(uuid4(), Role.ADMIN, datetime.now(UTC))

    response = await patch_role(client, uuid4(), "admin", forged.value)

    assert response.status_code == 401


async def test_an_admin_cannot_change_their_own_role(
    app: FastAPI, client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    token = await admin_token(app, client)
    admin_id = jwt.decode(token, options={"verify_signature": False})["sub"]

    response = await patch_role(client, admin_id, "customer", token)

    assert response.status_code == 409
    assert response.json()["title"] == "Cannot change your own role"


async def test_an_unknown_user_is_not_found(app: FastAPI, client: httpx.AsyncClient) -> None:
    token = await admin_token(app, client)

    response = await patch_role(client, uuid4(), "admin", token)

    assert response.status_code == 404
    assert response.json()["title"] == "User not found"


async def test_an_unknown_role_is_a_validation_error(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    token = await admin_token(app, client)
    target = (await register_user(client)).json()["id"]

    response = await patch_role(client, target, "superuser", token)

    assert response.status_code == 422
    assert {item["location"] for item in response.json()["errors"]} == {"body.role"}


async def test_a_malformed_user_id_is_a_validation_error(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    token = await admin_token(app, client)

    response = await patch_role(client, "not-a-uuid", "admin", token)

    assert response.status_code == 422
    assert {item["location"] for item in response.json()["errors"]} == {"path.user_id"}


async def test_repeating_the_same_role_is_a_no_op(
    app: FastAPI, client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    token = await admin_token(app, client)
    target = (await register_user(client)).json()["id"]
    events_before = len(store.outbox)

    response = await patch_role(client, target, "customer", token)

    assert response.status_code == 200
    assert len(store.outbox) == events_before


async def test_registering_through_the_api_publishes_user_registered(
    client: httpx.AsyncClient, store: InMemoryStore
) -> None:
    response = await register_user(client)

    (event,) = store.outbox
    assert event.event_type == "user.registered"
    assert event.key == response.json()["id"]
    assert event.correlation_id.version == 4
