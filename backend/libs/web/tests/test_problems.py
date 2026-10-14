import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ecommerce_auth import AdminUser, CurrentUser, ManagedTokenVerifier, Role
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_observability import REQUEST_ID_HEADER, configure_logging
from ecommerce_web import PROBLEM_MEDIA_TYPE, ServiceSettings, create_app

REQUEST_ID = "0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44"


class ItemIn(BaseModel):
    name: str
    quantity: int


@pytest.fixture
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def app(issuer: StubTokenIssuer) -> FastAPI:
    managed = ManagedTokenVerifier(build_stub_verifier(issuer), httpx.AsyncClient())
    app = create_app(ServiceSettings(name="svc"), token_verifier=managed)

    @app.post("/items")
    async def create_item(item: ItemIn) -> ItemIn:
        return item

    @app.get("/me")
    async def me(user: CurrentUser) -> dict[str, str]:
        return {"user_id": user.user_id}

    @app.get("/admin")
    async def admin(user: AdminUser) -> dict[str, str]:
        return {"user_id": user.user_id}

    @app.get("/teapot")
    async def teapot() -> None:
        raise HTTPException(418, "short and stout", headers={"X-Extra": "1"})

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def assert_problem(response: httpx.Response, status: int) -> dict[str, object]:
    body: dict[str, object] = response.json()
    assert response.status_code == status
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert body["status"] == status
    assert body["type"] == "about:blank"
    assert isinstance(body["title"], str)
    return body


async def test_unknown_route_is_a_problem(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope")

    body = assert_problem(response, 404)
    assert body["title"] == "Not Found"
    assert body["instance"] == "/nope"


async def test_wrong_method_is_a_problem_and_keeps_the_allow_header(
    client: httpx.AsyncClient,
) -> None:
    response = await client.delete("/me")

    assert_problem(response, 405)
    assert "allow" in response.headers


async def test_http_exception_keeps_status_detail_and_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/teapot")

    body = assert_problem(response, 418)
    assert body["detail"] == "short and stout"
    assert response.headers["X-Extra"] == "1"


async def test_validation_errors_list_each_invalid_field(client: httpx.AsyncClient) -> None:
    response = await client.post("/items", json={"quantity": "many"})

    body = assert_problem(response, 422)
    errors = body["errors"]
    assert isinstance(errors, list)
    assert {error["location"] for error in errors} == {"body.name", "body.quantity"}
    assert all({"message", "type"} <= error.keys() for error in errors)


async def test_missing_token_is_a_401_problem_with_a_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")

    body = assert_problem(response, 401)
    assert body["title"] == "Invalid or missing token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_valid_token_reaches_the_endpoint(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    token = issuer.issue(subject="user-1")

    response = await client.get("/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json() == {"user_id": "user-1"}


async def test_insufficient_role_is_a_403_problem(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    token = issuer.issue(role=Role.CUSTOMER)

    response = await client.get("/admin", headers={"Authorization": f"Bearer {token}"})

    body = assert_problem(response, 403)
    assert body["title"] == "Insufficient permissions"
    assert "WWW-Authenticate" not in response.headers


async def test_unexpected_errors_are_a_generic_500_without_internals(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/boom", headers={REQUEST_ID_HEADER: REQUEST_ID})

    body = assert_problem(response, 500)
    assert "secret internal detail" not in response.text
    assert body["request_id"] == REQUEST_ID
    assert response.headers[REQUEST_ID_HEADER] == REQUEST_ID


async def test_unexpected_errors_are_logged_with_the_request_id(
    capsys: pytest.CaptureFixture[str], client: httpx.AsyncClient
) -> None:
    configure_logging("svc")
    await client.get("/boom", headers={REQUEST_ID_HEADER: REQUEST_ID})

    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    entry = next(entry for entry in entries if entry["message"] == "unhandled error")
    assert entry["level"] == "ERROR"
    assert "secret internal detail" in entry["exception"]
    assert entry["request_id"] == REQUEST_ID


async def test_problem_bodies_carry_the_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/me", headers={REQUEST_ID_HEADER: REQUEST_ID})

    assert response.json()["request_id"] == REQUEST_ID
    assert response.headers[REQUEST_ID_HEADER] == REQUEST_ID
