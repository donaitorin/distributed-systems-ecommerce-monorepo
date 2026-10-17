from collections.abc import AsyncIterator

import httpx
import pytest
from cart_testing.support import FakeCatalog, Stores, bearer, build_test_app, http_client, product
from fastapi import FastAPI
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from cart.main import build, create_cart_app
from cart.settings import CartSettings
from ecommerce_auth.testing import StubTokenIssuer

UNREACHABLE = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)


class BrokenStore:
    async def lines(self, user_id: str) -> list[object]:
        raise RedisConnectionError("redis is down")


@pytest.fixture
async def client(issuer: StubTokenIssuer) -> AsyncIterator[httpx.AsyncClient]:
    app = build_test_app(issuer, Stores(), FakeCatalog(product()), redis=UNREACHABLE)
    async with http_client(app) as http:
        yield http


async def test_readiness_depends_on_redis_only(client: httpx.AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 503
    checks = response.json()["checks"]
    assert list(checks) == ["redis"]
    assert checks["redis"] in {"failed", "timeout"}
    assert response.headers["content-type"] == "application/problem+json"


async def test_liveness_does_not_touch_redis(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health")).status_code == 200


async def test_a_redis_outage_is_a_503_problem_with_retry_after(issuer: StubTokenIssuer) -> None:
    app: FastAPI = build_test_app(issuer, Stores(), FakeCatalog(), redis=UNREACHABLE)
    app.state.cart_service._store = BrokenStore()
    async with http_client(app) as http:
        response = await http.get("/api/v1/cart", headers=bearer(issuer))

    assert response.status_code == 503
    assert response.headers["retry-after"] == "2"
    assert response.json()["title"] == "Cart unavailable"


def test_the_real_catalog_gateway_is_built_from_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "REDIS_CART_HOST": "127.0.0.1",
        "REDIS_CART_PASSWORD": "secret",
        "JWT_JWKS_URL": "http://auth.invalid/jwks.json",
        "JWT_ISSUER": "ecommerce-auth",
        "JWT_AUDIENCE": "ecommerce-api",
        "ROOT_PATH": "/cart-service",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    app = build()

    assert app.root_path == "/cart-service"
    assert create_cart_app(CartSettings.from_env(environment)).title == "cart"
