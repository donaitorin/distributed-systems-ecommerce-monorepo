import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import httpx
import pytest
from cart_testing.events import confirmed_event, deleted_event, updated_event
from cart_testing.support import FakeCatalog, bearer, cart_settings, http_client, product
from redis.asyncio import Redis

from cart.domain.cart import CartLine
from cart.infra.redis_client import create_redis
from cart.infra.redis_projection import RedisProductProjection, product_key
from cart.infra.redis_store import RedisCartStore
from cart.main import create_cart_app
from cart.settings import RedisSettings
from cart.worker import WorkerSettings, run_worker
from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_contracts import Envelope, ProductDeletedV1, ProductUpdatedV1
from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutgoingMessage
from kafka_support import KafkaBroker
from redis_support import PASSWORD, RedisServer

pytestmark = pytest.mark.integration

type Event = Envelope[ProductUpdatedV1] | Envelope[ProductDeletedV1]
TTL = 3600


@dataclass(slots=True)
class Pipeline:
    settings: WorkerSettings
    redis: Redis
    publisher: KafkaPublisher
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    @property
    def topic(self) -> str:
        return self.settings.topic

    def start_worker(self) -> None:
        self.task = asyncio.create_task(run_worker(self.settings, self.stop))

    async def stop_worker(self) -> None:
        self.stop.set()
        if self.task is not None:
            await asyncio.wait_for(self.task, timeout=30)

    async def send(self, event: Event, key: str = "ordered") -> None:
        await self.publisher.publish(
            OutgoingMessage(self.topic, key, event.model_dump_json().encode())
        )

    async def reserve(self, sku: str = "RS-001", version: int = 1) -> None:
        projection = RedisProductProjection(self.redis, TTL)
        await projection.reserve(sku)
        await projection.apply_state(product(sku=sku, version=version, price="89.99", stock=10))

    async def wait_for(self, check: Callable[[], Awaitable[bool]]) -> None:
        async with asyncio.timeout(60):
            while True:
                if await check():
                    return
                await asyncio.sleep(0.2)

    async def wait_for_version(self, version: int, sku: str = "RS-001") -> None:
        async def reached() -> bool:
            return await self.redis.hget(product_key(sku), "version") == str(version)

        await self.wait_for(reached)

    async def entry(self, sku: str = "RS-001") -> dict[str, str]:
        return cast(dict[str, str], await self.redis.hgetall(product_key(sku)))


@pytest.fixture
async def pipeline(
    kafka: KafkaBroker, redis_server: RedisServer, redis_client: Redis
) -> AsyncIterator[Pipeline]:
    kafka_settings = KafkaSettings(kafka.bootstrap, "cart-test", publish_timeout_seconds=10)
    settings = WorkerSettings(
        redis=RedisSettings(host="127.0.0.1", port=redis_server.port, password=PASSWORD),
        kafka=kafka_settings,
        ttl_seconds=TTL,
        topic=f"catalog.events.{uuid4().hex}",
        group=f"cart-catalog-events-{uuid4().hex}",
        orders_topic=f"orders.events.{uuid4().hex}",
        orders_group=f"cart-order-events-{uuid4().hex}",
    )
    prepared = Pipeline(settings, redis_client, KafkaPublisher(kafka_settings))
    yield prepared
    await prepared.stop_worker()
    await prepared.publisher.close()


async def test_events_published_before_the_worker_started_end_in_the_newest_state(
    pipeline: Pipeline,
) -> None:
    await pipeline.reserve()
    await pipeline.send(updated_event(version=2, price="70.00", stock=4))
    await pipeline.send(deleted_event(version=3))
    await pipeline.send(updated_event(version=4, price="75.00", stock=0, name="Trail Shoes"))

    pipeline.start_worker()
    await pipeline.wait_for_version(4)

    assert await pipeline.entry() == {
        "version": "4",
        "name": "Trail Shoes",
        "price": "75.00",
        "stock": "0",
        "image_key": "",
        "deleted": "0",
    }


async def test_a_deletion_is_remembered_until_a_newer_update_arrives(pipeline: Pipeline) -> None:
    await pipeline.reserve()
    pipeline.start_worker()

    await pipeline.send(deleted_event(version=2))
    await pipeline.wait_for_version(2)
    assert (await pipeline.entry())["deleted"] == "1"

    await pipeline.send(updated_event(version=3, price="10.00"))
    await pipeline.wait_for_version(3)
    assert (await pipeline.entry())["deleted"] == "0"


async def test_replaying_the_whole_history_changes_nothing(pipeline: Pipeline) -> None:
    await pipeline.reserve()
    history: list[Event] = [
        updated_event(version=2, price="70.00"),
        deleted_event(version=3),
        updated_event(version=4, price="75.00"),
    ]
    for event in history:
        await pipeline.send(event)
    pipeline.start_worker()
    await pipeline.wait_for_version(4)
    settled = await pipeline.entry()

    for event in history:
        await pipeline.send(event)
    await pipeline.reserve("SENTINEL-1")
    await pipeline.send(updated_event(sku="SENTINEL-1", version=2))
    await pipeline.wait_for_version(2, "SENTINEL-1")

    assert await pipeline.entry() == settled


async def test_reordered_events_cannot_move_the_projection_back(pipeline: Pipeline) -> None:
    await pipeline.reserve()
    pipeline.start_worker()

    for version in (9, 7, 8, 6):
        await pipeline.send(updated_event(version=version, price=f"{version}.00"))
    await pipeline.reserve("SENTINEL-1")
    await pipeline.send(updated_event(sku="SENTINEL-1", version=2))
    await pipeline.wait_for_version(2, "SENTINEL-1")

    entry = await pipeline.entry()
    assert (entry["version"], entry["price"]) == ("9", "9.00")


async def test_a_large_batch_of_events_for_products_in_no_cart_stores_nothing(
    pipeline: Pipeline,
) -> None:
    await pipeline.reserve()
    keys_before = await pipeline.redis.dbsize()
    pipeline.start_worker()

    for number in range(1500):
        await pipeline.send(updated_event(sku=f"IMPORTED-{number:05d}", version=1 + number % 4))
    await pipeline.send(deleted_event(sku="IMPORTED-00001", version=9))
    await pipeline.send(updated_event(version=2, price="70.00"))
    await pipeline.wait_for_version(2)

    assert await pipeline.redis.dbsize() == keys_before == 1
    assert [key async for key in pipeline.redis.scan_iter("product:IMPORTED-*")] == []


async def test_a_malformed_message_does_not_block_the_events_after_it(
    pipeline: Pipeline,
) -> None:
    await pipeline.reserve()
    await pipeline.publisher.publish(OutgoingMessage(pipeline.topic, "ordered", b"{not json"))
    await pipeline.send(updated_event(version=2, price="70.00"))

    pipeline.start_worker()
    await pipeline.wait_for_version(2)

    assert (await pipeline.entry())["price"] == "70.00"


@pytest.fixture
async def shop(
    pipeline: Pipeline, redis_server: RedisServer, issuer: StubTokenIssuer
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    settings = cart_settings(
        redis=RedisSettings(host="127.0.0.1", port=redis_server.port, password=PASSWORD)
    )
    redis = create_redis(settings.redis)
    app = create_cart_app(settings, redis=redis, catalog=FakeCatalog(product()))
    app.state.token_verifier = build_stub_verifier(issuer)
    async with http_client(app) as client:
        yield client, bearer(issuer, uuid4())
    await redis.aclose()


async def test_a_product_change_published_in_kafka_shows_up_as_a_flag_in_the_cart(
    pipeline: Pipeline, shop: tuple[httpx.AsyncClient, dict[str, str]]
) -> None:
    client, headers = shop
    pipeline.start_worker()
    await client.put("/api/v1/cart/items/RS-001", json={"quantity": 2}, headers=headers)

    await pipeline.send(updated_event(version=2, price="79.90", stock=1))
    await pipeline.wait_for_version(2)
    changed = (await client.get("/api/v1/cart", headers=headers)).json()["items"][0]

    await pipeline.send(deleted_event(version=3))
    await pipeline.wait_for_version(3)
    gone = (await client.get("/api/v1/cart", headers=headers)).json()["items"][0]

    assert changed["price"] == "89.99"
    assert [
        (flag["type"], flag["old_price"], flag["new_price"], flag["available"])
        for flag in changed["flags"]
    ] == [
        ("price_changed", "89.99", "79.90", None),
        ("insufficient_stock", None, None, 1),
    ]
    assert [flag["type"] for flag in gone["flags"]] == ["unavailable"]


async def test_a_confirmed_order_removes_its_lines_from_the_customers_cart_once(
    pipeline: Pipeline,
) -> None:
    customer = uuid4()
    store = RedisCartStore(pipeline.redis, TTL)
    older = datetime(2026, 10, 1, tzinfo=UTC)
    for sku in ("A-1", "B-2"):
        await store.put_line(str(customer), CartLine.started(product(sku=sku), 2, older), 100)
    event = confirmed_event(customer, ["A-1"])
    body = event.model_dump_json().encode()
    topic = pipeline.settings.orders_topic

    pipeline.start_worker()
    await pipeline.publisher.publish(OutgoingMessage(topic, "k", body))
    await pipeline.publisher.publish(OutgoingMessage(topic, "k", body))

    async def only_b_left() -> bool:
        return [line.sku for line in await store.lines(str(customer))] == ["B-2"]

    await pipeline.wait_for(only_b_left)
    later = datetime.now(UTC)
    await store.put_line(str(customer), CartLine.started(product(sku="A-1"), 1, later), 100)
    await pipeline.publisher.publish(OutgoingMessage(topic, "k", body))
    marker = confirmed_event(customer, ["B-2"], occurred_at=later)
    await pipeline.publisher.publish(OutgoingMessage(topic, "k", marker.model_dump_json().encode()))

    async def b_gone() -> bool:
        return [line.sku for line in await store.lines(str(customer))] == ["A-1"]

    await pipeline.wait_for(b_gone)
    assert [line.sku for line in await store.lines(str(customer))] == ["A-1"]
