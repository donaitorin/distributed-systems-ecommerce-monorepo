from collections.abc import AsyncIterator

import pytest
from cart_testing.support import FakeCatalog, SteppingClock, Stores, product
from redis.asyncio import Redis

from ecommerce_auth.testing import StubTokenIssuer
from redis_support import PASSWORD, RedisServer


@pytest.fixture(scope="session")
def issuer() -> StubTokenIssuer:
    return StubTokenIssuer()


@pytest.fixture
def clock() -> SteppingClock:
    return SteppingClock()


@pytest.fixture
def stores() -> Stores:
    return Stores()


@pytest.fixture
def catalog() -> FakeCatalog:
    return FakeCatalog(product())


@pytest.fixture
async def redis_client(redis_server: RedisServer) -> AsyncIterator[Redis]:
    client = Redis(
        port=redis_server.port, password=PASSWORD, decode_responses=True, socket_timeout=5
    )
    await client.flushall()
    yield client
    await client.aclose()
