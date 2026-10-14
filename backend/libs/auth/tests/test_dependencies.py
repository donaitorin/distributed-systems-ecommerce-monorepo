from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from ecommerce_auth import (
    AdminUser,
    AuthError,
    CurrentUser,
    CustomerUser,
    Role,
    TokenVerifier,
    require_role,
)
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier


def build_app(verifier: TokenVerifier | None) -> FastAPI:
    app = FastAPI()
    if verifier is not None:
        app.state.token_verifier = verifier

    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, error: AuthError) -> JSONResponse:
        return JSONResponse(
            {"detail": error.detail}, status_code=error.status, headers=error.headers
        )

    @app.get("/me")
    async def me(user: CurrentUser) -> dict[str, str]:
        return {"user_id": user.user_id, "role": user.role}

    @app.get("/customer")
    async def customer_area(user: CustomerUser) -> dict[str, str]:
        return {"user_id": user.user_id}

    @app.get("/admin")
    async def admin_area(user: AdminUser) -> dict[str, str]:
        return {"user_id": user.user_id}

    @app.get("/customer-only", dependencies=[Depends(require_role(Role.CUSTOMER))])
    async def customer_only() -> dict[str, str]:
        return {"ok": "yes"}

    return app


@pytest.fixture
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
async def client(issuer: StubTokenIssuer) -> AsyncIterator[httpx.AsyncClient]:
    app = build_app(build_stub_verifier(issuer))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_missing_token_is_unauthorized_with_a_challenge(client: httpx.AsyncClient) -> None:
    response = await client.get("/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_non_bearer_scheme_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401


async def test_invalid_token_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/me", headers=bearer("garbage"))

    assert response.status_code == 401


async def test_valid_token_returns_the_current_user(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    token = issuer.issue(subject="user-7", role=Role.CUSTOMER)

    response = await client.get("/me", headers=bearer(token))

    assert response.json() == {"user_id": "user-7", "role": "customer"}


@pytest.mark.parametrize("role", [Role.CUSTOMER, Role.ADMIN])
async def test_customer_area_accepts_customers_and_admins(
    client: httpx.AsyncClient, issuer: StubTokenIssuer, role: Role
) -> None:
    response = await client.get("/customer", headers=bearer(issuer.issue(role=role)))

    assert response.status_code == 200


async def test_admin_area_rejects_customers_with_forbidden(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get("/admin", headers=bearer(issuer.issue(role=Role.CUSTOMER)))

    assert response.status_code == 403
    assert "WWW-Authenticate" not in response.headers


async def test_admin_area_accepts_admins(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    response = await client.get("/admin", headers=bearer(issuer.issue(role=Role.ADMIN)))

    assert response.status_code == 200


async def test_role_dependency_can_be_used_in_a_decorator(
    client: httpx.AsyncClient, issuer: StubTokenIssuer
) -> None:
    allowed = await client.get("/customer-only", headers=bearer(issuer.issue(role=Role.CUSTOMER)))
    denied = await client.get("/customer-only", headers=bearer(issuer.issue(role=Role.ADMIN)))

    assert (allowed.status_code, denied.status_code) == (200, 403)


async def test_missing_verifier_configuration_is_a_programming_error() -> None:
    app = build_app(None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        with pytest.raises(RuntimeError, match="not configured"):
            await http_client.get("/me", headers={"Authorization": "Bearer x"})
