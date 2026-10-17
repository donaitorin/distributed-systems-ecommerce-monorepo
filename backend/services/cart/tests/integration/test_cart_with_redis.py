from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
from cart_testing.support import (
    FakeCatalog,
    bearer,
    cart_settings,
    http_client,
    product,
)
from redis.asyncio import Redis

from cart.infra.redis_client import create_redis
from cart.infra.redis_projection import product_key
from cart.infra.redis_store import cart_key
from cart.main import create_cart_app
from cart.settings import CART_TTL_SECONDS, RedisSettings
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from redis_support import PASSWORD, RedisServer

pytestmark = pytest.mark.integration

CART = "/api/v1/cart"


class Stack:
    def __init__(
        self, client: httpx.AsyncClient, redis: Redis, headers: dict[str, str], user_id: str
    ) -> None:
        self.client = client
        self.redis = redis
        self.headers = headers
        self.user_id = user_id

    async def put(self, sku: str, quantity: int = 1) -> httpx.Response:
        return await self.client.put(
            f"{CART}/items/{sku}", json={"quantity": quantity}, headers=self.headers
        )

    async def cart(self) -> dict[str, object]:
        body: dict[str, object] = (await self.client.get(CART, headers=self.headers)).json()
        return body


@pytest.fixture
async def stack(
    redis_server: RedisServer, issuer: StubTokenIssuer
) -> AsyncIterator[tuple[Stack, FakeCatalog]]:
    settings = cart_settings(
        redis=RedisSettings(host="127.0.0.1", port=redis_server.port, password=PASSWORD)
    )
    redis = create_redis(settings.redis)
    await redis.flushall()
    catalog = FakeCatalog(product(), product(sku="TR-002", price="45.50", name="Trail Shoes"))
    app = create_cart_app(settings, redis=redis, catalog=catalog)
    app.state.token_verifier = build_stub_verifier(issuer)
    user = uuid4()
    async with http_client(app) as client:
        yield Stack(client, redis, bearer(issuer, user), str(user)), catalog
    await redis.aclose()


async def test_redis_runs_with_the_persistence_and_memory_settings_of_the_compose_file(
    redis_server: RedisServer,
) -> None:
    assert redis_server.config("appendonly") == "yes"
    assert redis_server.config("appendfsync") == "everysec"
    assert redis_server.config("maxmemory-policy") == "noeviction"


async def test_the_app_is_ready_against_a_real_redis(
    stack: tuple[Stack, FakeCatalog],
) -> None:
    app_stack, _ = stack

    response = await app_stack.client.get("/ready")

    assert response.status_code == 200
    assert response.json()["checks"] == {"redis": "ok"}


async def test_the_cart_and_its_projection_live_in_redis_with_the_thirty_day_ttl(
    stack: tuple[Stack, FakeCatalog],
) -> None:
    app_stack, _ = stack

    await app_stack.put("RS-001", 2)
    user_keys = [key async for key in app_stack.redis.scan_iter("cart:*")]

    assert user_keys == [cart_key(app_stack.user_id)]
    ttl = await app_stack.redis.ttl(user_keys[0])
    assert CART_TTL_SECONDS - 60 < ttl <= CART_TTL_SECONDS
    assert await app_stack.redis.ttl(product_key("RS-001")) > 29 * 24 * 3600
    assert await app_stack.redis.hget(product_key("RS-001"), "version") == "1"


async def test_every_change_renews_the_cart_ttl(stack: tuple[Stack, FakeCatalog]) -> None:
    app_stack, _ = stack
    await app_stack.put("RS-001")
    key = cart_key(app_stack.user_id)

    await app_stack.redis.expire(key, 100)
    await app_stack.put("TR-002")
    after_put = await app_stack.redis.ttl(key)
    await app_stack.redis.expire(key, 100)
    await app_stack.client.delete(f"{CART}/items/TR-002", headers=app_stack.headers)
    after_delete = await app_stack.redis.ttl(key)

    assert after_put > CART_TTL_SECONDS - 60
    assert after_delete > CART_TTL_SECONDS - 60


async def test_the_cart_survives_a_restart_of_redis(
    stack: tuple[Stack, FakeCatalog], redis_server: RedisServer
) -> None:
    app_stack, _ = stack
    await app_stack.put("RS-001", 2)
    await app_stack.put("TR-002", 1)
    before = await app_stack.cart()

    redis_server.restart()
    after = await app_stack.cart()

    assert before["item_count"] == 3
    assert after == before


async def test_the_projection_and_the_ttls_survive_a_restart_of_redis(
    stack: tuple[Stack, FakeCatalog], redis_server: RedisServer
) -> None:
    app_stack, _ = stack
    await app_stack.put("RS-001")
    key = cart_key(app_stack.user_id)

    redis_server.restart()

    assert await app_stack.redis.hget(product_key("RS-001"), "price") == "89.99"
    assert await app_stack.redis.ttl(key) > CART_TTL_SECONDS - 120


async def test_the_api_answers_503_while_redis_is_down_and_recovers_after(
    stack: tuple[Stack, FakeCatalog], redis_server: RedisServer
) -> None:
    app_stack, _ = stack
    await app_stack.put("RS-001")
    redis_server.stop()
    try:
        down = await app_stack.client.get(CART, headers=app_stack.headers)
    finally:
        redis_server.start()

    assert down.status_code == 503
    assert down.headers["retry-after"] == "2"
