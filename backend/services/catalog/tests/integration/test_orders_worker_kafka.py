import asyncio
import dataclasses
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from catalog_testing.reservations import (
    add_product,
    cancelled_event,
    created_event,
    line,
    outgoing,
    stock_and_version,
)
from catalog_testing.test_environment import WORKER_ENVIRON
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine

from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.settings import CatalogSettings
from catalog.worker import WorkerSettings, run_worker
from ecommerce_contracts import (
    CATALOG_TOPIC,
    INVENTORY_TOPIC,
    PRODUCT_UPDATED,
    STOCK_RELEASED,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    Envelope,
)
from ecommerce_messaging import KafkaPublisher, KafkaSettings
from kafka_support import KafkaBroker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 60


@dataclass(slots=True)
class Pipeline:
    kafka: KafkaBroker
    engine: AsyncEngine
    settings: WorkerSettings
    publisher: KafkaPublisher
    topic: str
    group: str
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    def factory(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(create_session_factory(self.engine))

    def start_worker(self) -> None:
        self.task = asyncio.create_task(
            run_worker(self.settings, self.stop, self.topic, self.group)
        )

    async def stop_worker(self) -> None:
        self.stop.set()
        if self.task is not None:
            await asyncio.wait_for(self.task, timeout=30)

    async def send(self, envelope: Envelope[Any], key: UUID | None = None) -> None:
        message = outgoing(envelope)
        await self.publisher.publish(
            dataclasses.replace(message, topic=self.topic, key=str(key or message.key))
        )

    async def wait_for_stock(self, sku: str, stock: int) -> None:
        async with asyncio.timeout(WAIT_SECONDS):
            while True:
                if (await stock_and_version(self.factory, sku))[0] == stock:
                    return
                await asyncio.sleep(0.2)

    async def wait_until_published(self, order_id: UUID, count: int) -> None:
        async with asyncio.timeout(WAIT_SECONDS):
            while True:
                async with self.engine.connect() as connection:
                    result = await connection.execute(
                        text(
                            "SELECT count(*) FROM outbox WHERE key = :key"
                            " AND published_at IS NOT NULL"
                        ),
                        {"key": str(order_id)},
                    )
                    if result.scalar_one() >= count:
                        return
                await asyncio.sleep(0.2)

    async def read(
        self, topic: str, wanted: Callable[[dict[str, object]], bool], count: int
    ) -> list[dict[str, object]]:
        reader = AIOKafkaConsumer(
            topic,
            bootstrap_servers=self.kafka.bootstrap,
            group_id=f"reader-{uuid4().hex}",
            auto_offset_reset="earliest",
        )
        await reader.start()
        found: list[dict[str, object]] = []
        try:
            async with asyncio.timeout(WAIT_SECONDS):
                while len(found) < count:
                    for records in (await reader.getmany(timeout_ms=1000)).values():
                        events = [json.loads(record.value) for record in records]
                        found.extend(event for event in events if wanted(event))
        finally:
            await reader.stop()
        return found


@pytest.fixture
async def pipeline(
    kafka: KafkaBroker,
    empty_database_url: str,
    alembic_runner: Callable[[str, str, str], None],
) -> AsyncIterator[Pipeline]:
    alembic_runner(empty_database_url, "upgrade", "head")
    kafka_settings = KafkaSettings(kafka.bootstrap, "catalog-test", publish_timeout_seconds=10)
    catalog = dataclasses.replace(
        CatalogSettings.from_env(WORKER_ENVIRON), database_url=make_url(empty_database_url)
    )
    engine = create_engine(empty_database_url)
    prepared = Pipeline(
        kafka,
        engine,
        WorkerSettings(catalog, kafka_settings),
        KafkaPublisher(kafka_settings),
        topic=f"orders.events.{uuid4().hex}",
        group=f"catalog-orders-{uuid4().hex}",
    )
    yield prepared
    await prepared.stop_worker()
    await prepared.publisher.close()
    await engine.dispose()


def about(order_id: UUID, event_type: str) -> Callable[[dict[str, object]], bool]:
    def matches(event: dict[str, object]) -> bool:
        payload = event["payload"]
        assert isinstance(payload, dict)
        return event["event_type"] == event_type and payload.get("order_id") == str(order_id)

    return matches


async def test_an_order_created_event_reserves_stock_and_replies_through_the_outbox_and_kafka(
    pipeline: Pipeline,
) -> None:
    sku = await add_product(pipeline.factory, price="12.50", stock=5)
    order_id = uuid4()
    await pipeline.send(created_event(order_id, line(sku, 2, "12.50")))

    pipeline.start_worker()
    await pipeline.wait_for_stock(sku, 3)
    [reply] = await pipeline.read(INVENTORY_TOPIC, about(order_id, STOCK_RESERVED), 1)

    assert reply["producer"] == "catalog-service"
    payload = reply["payload"]
    assert isinstance(payload, dict)
    assert payload["lines"] == [
        {"sku": sku, "name": "Widget", "quantity": 2, "unit_price": "12.50"}
    ]
    [product_event] = await pipeline.read(
        CATALOG_TOPIC,
        lambda event: event["event_type"] == PRODUCT_UPDATED and event["payload"]["sku"] == sku,  # type: ignore[index]
        1,
    )
    assert product_event["payload"]["stock"] == 3  # type: ignore[index]


async def test_redelivering_the_order_and_cancelling_it_twice_moves_the_stock_once_each_way(
    pipeline: Pipeline,
) -> None:
    sku = await add_product(pipeline.factory, stock=5)
    order_id = uuid4()
    created = created_event(order_id, line(sku, 2))
    cancelled = cancelled_event(order_id)
    for envelope in (created, created, cancelled, cancelled):
        await pipeline.send(envelope)

    pipeline.start_worker()
    await pipeline.wait_until_published(order_id, 2)
    released = await pipeline.read(INVENTORY_TOPIC, about(order_id, STOCK_RELEASED), 1)

    assert len(released) == 1
    assert await stock_and_version(pipeline.factory, sku) == (5, 3)
    await asyncio.sleep(1)
    async with pipeline.engine.connect() as connection:
        total = await connection.execute(
            text("SELECT count(*) FROM outbox WHERE key = :key"), {"key": str(order_id)}
        )
    assert total.scalar_one() == 2


async def test_a_cancellation_that_overtakes_its_order_leaves_the_stock_untouched(
    pipeline: Pipeline,
) -> None:
    sku = await add_product(pipeline.factory, stock=5)
    blocked, probe = uuid4(), uuid4()
    await pipeline.send(cancelled_event(blocked))
    await pipeline.send(created_event(blocked, line(sku, 2)))
    await pipeline.send(created_event(probe, line(sku, 1)), key=blocked)

    pipeline.start_worker()
    await pipeline.wait_for_stock(sku, 4)

    assert await stock_and_version(pipeline.factory, sku) == (4, 2)
    async with pipeline.engine.connect() as connection:
        rows = await connection.execute(
            text("SELECT count(*) FROM outbox WHERE key = :key"), {"key": str(blocked)}
        )
    assert rows.scalar_one() == 0


async def test_an_order_that_cannot_be_reserved_is_answered_with_the_reason(
    pipeline: Pipeline,
) -> None:
    sku = await add_product(pipeline.factory, stock=1)
    order_id = uuid4()
    await pipeline.send(created_event(order_id, line(sku, 2)))

    pipeline.start_worker()
    [reply] = await pipeline.read(INVENTORY_TOPIC, about(order_id, STOCK_RESERVATION_FAILED), 1)

    payload = reply["payload"]
    assert isinstance(payload, dict)
    assert (payload["reason"], payload["sku"], payload["available"]) == (
        "insufficient_stock",
        sku,
        1,
    )
    assert await stock_and_version(pipeline.factory, sku) == (1, 1)
