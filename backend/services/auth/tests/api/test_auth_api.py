from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
import pytest
from auth_testing.support import (
    STRONG_PASSWORD,
    SteppingClock,
    login_user,
    refresh_with,
    register_user,
    verifier_for,
)

from auth.infra.keys import KeyStore
from ecommerce_auth import Role

PREFIX = "/api/v1/auth"


def field_locations(response: httpx.Response) -> set[str]:
    return {item["location"] for item in response.json()["errors"]}


def problem_without_request_data(response: httpx.Response) -> dict[str, Any]:
    body: dict[str, Any] = response.json()
    return {key: value for key, value in body.items() if key not in {"request_id", "instance"}}


async def test_register_creates_a_customer_and_returns_no_tokens_or_secrets(
    client: httpx.AsyncClient,
) -> None:
    response = await register_user(client, "  Ada@Example.com ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "role"}
    assert body["email"] == "ada@example.com"
    assert body["role"] == "customer"


async def test_register_ignores_a_role_sent_by_the_client(client: httpx.AsyncClient) -> None:
    response = await client.post(
        f"{PREFIX}/register",
        json={"email": "eve@example.com", "password": STRONG_PASSWORD, "role": "admin"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "customer"


async def test_registering_the_same_email_twice_is_a_conflict(client: httpx.AsyncClient) -> None:
    await register_user(client)

    response = await register_user(client, "ADA@example.com")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["title"] == "Email already registered"


async def test_register_reports_every_invalid_field(client: httpx.AsyncClient) -> None:
    response = await register_user(client, "not-an-email", "short")

    assert response.status_code == 422
    assert field_locations(response) == {"body.email", "body.password"}
    assert response.headers["content-type"] == "application/problem+json"


async def test_register_rejects_a_common_password(client: httpx.AsyncClient) -> None:
    response = await register_user(client, password="password123")

    assert response.status_code == 422
    assert response.json()["errors"][0]["type"] == "too_common"


async def test_register_rejects_missing_fields_and_oversized_input(
    client: httpx.AsyncClient,
) -> None:
    missing = await client.post(f"{PREFIX}/register", json={})
    oversized = await register_user(client, password="x" * 2000)

    assert missing.status_code == 422
    assert field_locations(missing) == {"body.email", "body.password"}
    assert oversized.status_code == 422
    assert field_locations(oversized) == {"body.password"}


async def test_login_returns_tokens_that_other_services_accept(
    client: httpx.AsyncClient, key_store: KeyStore, clock: SteppingClock
) -> None:
    clock.now = datetime.now(UTC)
    registered = (await register_user(client)).json()

    response = await login_user(client, "ADA@example.com")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    user = await verifier_for(key_store.jwks_document()).verify(body["access_token"])
    assert user.user_id == registered["id"]
    assert user.role is Role.CUSTOMER


async def test_unknown_email_and_wrong_password_are_indistinguishable(
    client: httpx.AsyncClient,
) -> None:
    await register_user(client)

    unknown = await login_user(client, "nobody@example.com")
    wrong = await login_user(client, "ada@example.com", "not the password")

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.headers["content-type"] == wrong.headers["content-type"]
    assert problem_without_request_data(unknown) == problem_without_request_data(wrong)


async def test_a_malformed_email_on_login_is_just_invalid_credentials(
    client: httpx.AsyncClient,
) -> None:
    response = await login_user(client, "not-an-email", "short")

    assert response.status_code == 401
    assert response.json()["title"] == "Invalid credentials"


async def test_refresh_rotates_the_pair(client: httpx.AsyncClient, clock: SteppingClock) -> None:
    await register_user(client)
    first = (await login_user(client)).json()
    clock.advance(seconds=60)

    response = await refresh_with(client, first["refresh_token"])

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]


async def test_refreshing_with_garbage_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await refresh_with(client, "garbage")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


async def test_reusing_a_rotated_token_inside_the_grace_window_is_unauthorized_but_harmless(
    client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    await register_user(client)
    first = (await login_user(client)).json()
    second = (await refresh_with(client, first["refresh_token"])).json()
    clock.advance(seconds=5)

    replay = await refresh_with(client, first["refresh_token"])
    still_valid = await refresh_with(client, second["refresh_token"])

    assert replay.status_code == 401
    assert still_valid.status_code == 200


async def test_reusing_a_rotated_token_after_the_grace_window_ends_the_session(
    client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    await register_user(client)
    first = (await login_user(client)).json()
    second = (await refresh_with(client, first["refresh_token"])).json()
    clock.advance(seconds=30)

    replay = await refresh_with(client, first["refresh_token"])
    descendant = await refresh_with(client, second["refresh_token"])

    assert replay.status_code == 401
    assert descendant.status_code == 401


async def test_every_refresh_failure_looks_the_same_to_the_client(
    client: httpx.AsyncClient, clock: SteppingClock
) -> None:
    await register_user(client)
    first = (await login_user(client)).json()
    await refresh_with(client, first["refresh_token"])
    within_grace = await refresh_with(client, first["refresh_token"])
    clock.advance(seconds=30)
    reuse = await refresh_with(client, first["refresh_token"])
    unknown = await refresh_with(client, "garbage")

    bodies = [problem_without_request_data(r) for r in (within_grace, reuse, unknown)]
    assert bodies[0] == bodies[1] == bodies[2]


async def test_logout_returns_no_content_and_kills_the_refresh_token(
    client: httpx.AsyncClient,
) -> None:
    await register_user(client)
    tokens = (await login_user(client)).json()

    logout = await client.post(f"{PREFIX}/logout", json={"refresh_token": tokens["refresh_token"]})
    refresh = await refresh_with(client, tokens["refresh_token"])

    assert logout.status_code == 204
    assert logout.content == b""
    assert refresh.status_code == 401


async def test_logout_with_an_unknown_token_is_still_no_content(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{PREFIX}/logout", json={"refresh_token": "never-issued"})

    assert response.status_code == 204


async def test_logout_requires_a_refresh_token_field(client: httpx.AsyncClient) -> None:
    response = await client.post(f"{PREFIX}/logout", json={})

    assert response.status_code == 422
    assert field_locations(response) == {"body.refresh_token"}


async def test_jwks_publishes_the_public_signing_keys(
    client: httpx.AsyncClient, key_store: KeyStore
) -> None:
    response = await client.get(f"{PREFIX}/.well-known/jwks.json")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.json() == key_store.jwks_document()
    (jwk,) = response.json()["keys"]
    assert jwk["kid"] == key_store.active.kid
    assert "d" not in jwk


async def test_the_token_header_names_a_key_published_in_the_jwks(
    client: httpx.AsyncClient,
) -> None:
    await register_user(client)
    token = (await login_user(client)).json()["access_token"]

    kid = jwt.get_unverified_header(token)["kid"]

    published = (await client.get(f"{PREFIX}/.well-known/jwks.json")).json()["keys"]
    assert kid in {jwk["kid"] for jwk in published}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/register"),
        ("GET", "/login"),
        ("GET", "/refresh"),
        ("POST", "/.well-known/jwks.json"),
    ],
)
async def test_wrong_methods_are_rejected_as_problem_json(
    client: httpx.AsyncClient, method: str, path: str
) -> None:
    response = await client.request(method, f"{PREFIX}{path}")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"


async def test_responses_carry_a_request_id(client: httpx.AsyncClient) -> None:
    response = await login_user(client, "nobody@example.com")

    assert response.headers["x-request-id"] == response.json()["request_id"]
