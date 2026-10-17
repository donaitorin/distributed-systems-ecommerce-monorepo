import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from orders_testing.data import CUSTOMER, order_request
from orders_testing.events import (
    outgoing,
    payment_failed,
    payment_succeeded,
    reservation_failed,
    stock_reserved,
)
from orders_testing.waiting import eventually
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ecommerce_contracts import (
    INVENTORY_TOPIC,
    ORDER_CANCELLED,
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
)
from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutgoingMessage
from kafka_support import KafkaBroker
from orders.application.clock import utc_now
from orders.application.orders import OrderService
from orders.infra.database import create_engine, create_session_factory
from orders.infra.unit_of_work import SqlAlchemyUnitOfWork
from orders.worker import WorkerSettings, run_worker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 60


@dataclass(slots=True)
class Pipeline:
    kafka: KafkaBroker
    engine: AsyncEngine
    settings: WorkerSettings
    publisher: KafkaPublisher
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)

    @property
    def inventory_topic(self) -> str:
        return self.settings.topics[0]

    @property
    def payments_topic(self) -> str:
        return self.settings.topics[1]

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(create_session_factory(self.engine))

    def start_worker(self) -> None:
        self.tasks.append(asyncio.create_task(run_worker(self.settings, self.stop, utc_now)))

    async def stop_workers(self) -> None:
        self.stop.set()
        if self.tasks:
            await asyncio.wait_for(asyncio.gather(*self.tasks), timeout=30)

    async def place(self) -> UUID:
        service = OrderService(self.unit_of_work, utc_now)
        key = f"kafka-{uuid4().hex}"
        return (await service.place(CUSTOMER, key, order_request(), uuid4())).order_id

    async def send(self, envelope: Any) -> None:
        message = outgoing(envelope)
        topic = self.inventory_topic if message.topic == INVENTORY_TOPIC else self.payments_topic
        await self.publisher.publish(replace(message, topic=topic))

    async def status(self, order_id: UUID) -> str:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT status FROM orders WHERE id = :id"), {"id": order_id}
            )
            return str(result.scalar_one())

    async def wait_for_status(self, order_id: UUID, status: str) -> None:
        await eventually(lambda: self._is(order_id, status), seconds=WAIT_SECONDS, interval=0.2)

    async def _is(self, order_id: UUID, status: str) -> bool:
        return await self.status(order_id) == status

    async def events(self, order_ids: set[UUID], count: int) -> list[dict[str, Any]]:
        reader = AIOKafkaConsumer(
            ORDERS_TOPIC,
            bootstrap_servers=self.kafka.bootstrap,
            group_id=f"reader-{uuid4().hex}",
            auto_offset_reset="earliest",
        )
        await reader.start()
        found: list[dict[str, Any]] = []
        try:
            async with asyncio.timeout(WAIT_SECONDS):
                while len(found) < count:
                    for records in (await reader.getmany(timeout_ms=1000)).values():
                        parsed = (json.loads(record.value) for record in records)
                        found.extend(
                            event
                            for event in parsed
                            if event["payload"]["order_id"] in {str(item) for item in order_ids}
                        )
        finally:
            await reader.stop()
        return found

    async def dead_letters(self, topic: str, count: int) -> list[dict[str, bytes]]:
        reader = AIOKafkaConsumer(
            topic + ".dlq",
            bootstrap_servers=self.kafka.bootstrap,
            group_id=f"reader-{uuid4().hex}",
            auto_offset_reset="earliest",
        )
        await reader.start()
        found: list[dict[str, bytes]] = []
        try:
            async with asyncio.timeout(WAIT_SECONDS):
                while len(found) < count:
                    for records in (await reader.getmany(timeout_ms=1000)).values():
                        found.extend(dict(record.headers) for record in records)
        finally:
            await reader.stop()
        return found


type PipelineFactory = Callable[[float], Pipeline]


@pytest.fixture
async def pipeline(
    kafka: KafkaBroker,
    empty_database_url: str,
    alembic_runner: Callable[[str, str, str], None],
) -> AsyncIterator[Pipeline]:
    alembic_runner(empty_database_url, "upgrade", "head")
    kafka_settings = KafkaSettings(kafka.bootstrap, "orders-test", publish_timeout_seconds=10)
    settings = WorkerSettings(
        database_url=make_url(empty_database_url),
        kafka=kafka_settings,
        saga_timeout_seconds=3600,
        sweep_interval_seconds=0.2,
        topics=(f"inventory.events.{uuid4().hex}", f"payments.events.{uuid4().hex}"),
        group=f"orders-saga-{uuid4().hex}",
    )
    engine = create_engine(empty_database_url)
    prepared = Pipeline(kafka, engine, settings, KafkaPublisher(kafka_settings))
    yield prepared
    await prepared.stop_workers()
    await prepared.publisher.close()
    await engine.dispose()


def with_timeout(pipeline: Pipeline, seconds: float) -> None:
    pipeline.settings = replace(pipeline.settings, saga_timeout_seconds=seconds)


async def test_an_order_travels_from_the_outbox_through_the_saga_events_to_confirmed(
    pipeline: Pipeline,
) -> None:
    order_id = await pipeline.place()
    pipeline.start_worker()
    created = await pipeline.events({order_id}, 1)
    assert [event["event_type"] for event in created] == [ORDER_CREATED]

    lines = [("RS-001", "Rust in Action", 2, "39.90"), ("XS-001", "Sticker Pack", 1, "12.50")]
    await pipeline.send(stock_reserved(order_id, lines))
    await pipeline.wait_for_status(order_id, "STOCK_RESERVED")
    await pipeline.send(payment_succeeded(order_id))
    await pipeline.wait_for_status(order_id, "CONFIRMED")
    events = await pipeline.events({order_id}, 3)

    assert [event["event_type"] for event in events] == [
        ORDER_CREATED,
        ORDER_PAYMENT_REQUESTED,
        ORDER_CONFIRMED,
    ]
    assert {event["correlation_id"] for event in events} != set()
    assert len({event["correlation_id"] for event in events}) == 1
    assert all(event["producer"] == "orders-service" for event in events)
    requested = events[1]["payload"]
    assert (requested["amount"], requested["card_last4"]) == ("92.30", "1111")


async def test_a_declined_payment_and_a_failed_reservation_cancel_their_orders(
    pipeline: Pipeline,
) -> None:
    declined, unavailable = await pipeline.place(), await pipeline.place()
    pipeline.start_worker()
    await pipeline.send(stock_reserved(declined, [("RS-001", "Rust in Action", 2, "39.90")]))
    await pipeline.wait_for_status(declined, "STOCK_RESERVED")
    failure = payment_failed(declined)
    await pipeline.send(failure)
    await pipeline.send(failure)
    await pipeline.send(reservation_failed(unavailable, "product_unavailable"))

    await pipeline.wait_for_status(declined, "CANCELLED")
    await pipeline.wait_for_status(unavailable, "CANCELLED")
    cancelled = [
        event
        for event in await pipeline.events({declined, unavailable}, 5)
        if event["event_type"] == ORDER_CANCELLED
    ]

    reasons = {event["payload"]["order_id"]: event["payload"]["reason"] for event in cancelled}
    assert reasons == {str(declined): "payment_failed", str(unavailable): "product_unavailable"}


async def test_an_order_nobody_answers_is_cancelled_by_the_timeout(pipeline: Pipeline) -> None:
    with_timeout(pipeline, 1)
    order_id = await pipeline.place()

    pipeline.start_worker()
    await pipeline.wait_for_status(order_id, "CANCELLED")
    events = await pipeline.events({order_id}, 2)

    assert [event["event_type"] for event in events] == [ORDER_CREATED, ORDER_CANCELLED]
    assert events[1]["payload"]["reason"] == "saga_timeout"


async def test_two_workers_cancel_each_stuck_order_once(pipeline: Pipeline) -> None:
    with_timeout(pipeline, 1)
    order_ids = {await pipeline.place() for _ in range(12)}

    pipeline.start_worker()
    pipeline.start_worker()
    events = await pipeline.events(order_ids, 24)
    await asyncio.sleep(1)
    again = await pipeline.events(order_ids, 24)

    cancelled = [event for event in again if event["event_type"] == ORDER_CANCELLED]
    assert len(events) == 24
    assert len(cancelled) == 12
    assert {event["payload"]["order_id"] for event in cancelled} == {str(i) for i in order_ids}
    async with pipeline.engine.connect() as connection:
        result = await connection.execute(
            text("SELECT count(*) FROM order_status_history WHERE to_status = 'CANCELLED'")
        )
        assert result.scalar_one() == 12


async def test_a_malformed_message_is_dead_lettered_and_the_next_one_is_processed(
    pipeline: Pipeline,
) -> None:
    order_id = await pipeline.place()
    await pipeline.publisher.publish(OutgoingMessage(pipeline.inventory_topic, "bad", b"{nope"))
    await pipeline.send(reservation_failed(order_id))

    pipeline.start_worker()
    await pipeline.wait_for_status(order_id, "CANCELLED")
    [headers] = await pipeline.dead_letters(pipeline.inventory_topic, 1)

    assert headers["x-original-topic"] == pipeline.inventory_topic.encode()
    assert headers["x-consumer-group"] == pipeline.settings.group.encode()


async def test_the_workers_stop_promptly_when_asked(pipeline: Pipeline) -> None:
    pipeline.start_worker()
    await asyncio.sleep(1)

    await pipeline.stop_workers()

    assert all(task.done() for task in pipeline.tasks)
