from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from kafka_support import run_kafka
from postgres_support import PostgresServer
from redis_support import RedisServer
from saga_harness import Infrastructure, Saga, migrate, running_saga


@pytest.fixture(scope="module")
def infrastructure(
    postgres_server: PostgresServer, redis_server: RedisServer
) -> Iterator[Infrastructure]:
    with run_kafka() as broker:
        urls = [postgres_server.create_database() for _ in range(3)]
        for service, url in zip(("catalog", "orders", "payments"), urls, strict=True):
            migrate(service, url)
        yield Infrastructure(broker, urls[0], urls[1], urls[2], redis_server)


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def saga(infrastructure: Infrastructure) -> AsyncIterator[Saga]:
    async with running_saga(infrastructure) as running:
        yield running
