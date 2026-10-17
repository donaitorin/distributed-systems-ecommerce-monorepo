import asyncio
import contextlib
import dataclasses
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from payments_testing.data import order_cancelled, outgoing, payment_requested
from payments_testing.waiting import eventually
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ecommerce_contracts import (
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    Envelope,
)
from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutgoingMessage
from kafka_support import KafkaBroker
from payments.infra.database import create_engine
from payments.worker import WorkerSettings, run_worker

pytestmark = pytest.mark.integration

WAIT_SECONDS = 60
LATE_DELAY = 2.0


@dataclass(slots=True)
class Pipeline:
    kafka: KafkaBroker
    engine: AsyncEngine
    settings: WorkerSettings
    publisher: KafkaPublisher
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    def start_worker(self) -> None:
        self.task = asyncio.create_task(run_worker(self.settings, self.stop))

    async def stop_worker(self) -> None:
        self.stop.set()
        if self.task is not None:
            await asyncio.wait_for(self.task, timeout=30)

    async def send(self, envelope: Envelope[Any]) -> None:
        message = outgoing(envelope)
        await self.publisher.publish(dataclasses.replace(message, topic=self.settings.topic))

    async def status(self, order_id: UUID) -> str | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT status FROM payments WHERE order_id = :id"), {"id": order_id}
            )
            row = result.first()
        return None if row is None else str(row[0])

    async def wait_for_status(self, order_id: UUID, status: str) -> None:
        async def reached() -> bool:
            return await self.status(order_id) == status

        await eventually(reached, seconds=WAIT_SECONDS, interval=0.2)

    async def published_within(self, order_id: UUID, seconds: float) -> list[dict[str, Any]]:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(seconds):
                return await self.published(order_id, 1)
        return []

    async def published(self, order_id: UUID, count: int) -> list[dict[str, Any]]:
        reader = AIOKafkaConsumer(
            PAYMENTS_TOPIC,
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
                        found.extend(e for e in parsed if e["payload"]["order_id"] == str(order_id))
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
    kafka_settings = KafkaSettings(kafka.bootstrap, "payments-test", publish_timeout_seconds=10)
    settings = WorkerSettings(
        database_url=make_url(empty_database_url),
        kafka=kafka_settings,
        late_approval_delay_seconds=LATE_DELAY,
        settle_interval_seconds=0.1,
        topic=f"orders.events.{uuid4().hex}",
        group=f"payments-order-events-{uuid4().hex}",
    )
    engine = create_engine(empty_database_url)
    prepared = Pipeline(kafka, engine, settings, KafkaPublisher(kafka_settings))
    yield prepared
    await prepared.stop_worker()
    await prepared.publisher.close()
    await engine.dispose()


async def test_an_approved_card_publishes_payment_succeeded_with_the_orders_correlation_id(
    pipeline: Pipeline,
) -> None:
    request = payment_requested(card_last4="1111")
    await pipeline.send(request)

    pipeline.start_worker()
    [event] = await pipeline.published(request.payload.order_id, 1)

    assert event["event_type"] == PAYMENT_SUCCEEDED
    assert event["producer"] == "payments-service"
    assert event["correlation_id"] == str(request.correlation_id)
    assert event["payload"]["amount"] == "92.30"


async def test_a_declined_card_publishes_payment_failed(pipeline: Pipeline) -> None:
    request = payment_requested(card_last4="0000")
    await pipeline.send(request)

    pipeline.start_worker()
    [event] = await pipeline.published(request.payload.order_id, 1)

    assert event["event_type"] == PAYMENT_FAILED
    assert event["payload"]["reason"] == "card_declined"


async def test_a_card_that_never_answers_publishes_nothing_while_others_go_on(
    pipeline: Pipeline,
) -> None:
    silent, control = payment_requested(card_last4="9999"), payment_requested(card_last4="1111")
    await pipeline.send(silent)
    await pipeline.send(control)

    pipeline.start_worker()
    await pipeline.published(control.payload.order_id, 1)
    await asyncio.sleep(LATE_DELAY + 1)

    assert await pipeline.status(silent.payload.order_id) == "PENDING"
    assert await pipeline.published_within(silent.payload.order_id, seconds=3) == []


async def test_the_late_card_succeeds_after_the_delay(pipeline: Pipeline) -> None:
    request = payment_requested(card_last4="2222")
    await pipeline.send(request)

    pipeline.start_worker()
    await asyncio.sleep(0.5)
    assert await pipeline.status(request.payload.order_id) == "PENDING"
    [event] = await pipeline.published(request.payload.order_id, 1)

    assert event["event_type"] == PAYMENT_SUCCEEDED


async def test_a_late_success_for_a_cancelled_order_is_refunded_and_announced(
    pipeline: Pipeline,
) -> None:
    request = payment_requested(card_last4="2222")
    order_id = request.payload.order_id
    await pipeline.send(request)
    await pipeline.send(order_cancelled(order_id))

    pipeline.start_worker()
    events = await pipeline.published(order_id, 2)
    await pipeline.wait_for_status(order_id, "REFUNDED")

    assert [event["event_type"] for event in events] == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    assert events[1]["payload"]["reason"] == "order_cancelled"


async def test_redelivered_requests_and_cancellations_announce_each_thing_once(
    pipeline: Pipeline,
) -> None:
    request = payment_requested(card_last4="1111")
    order_id = request.payload.order_id
    cancelled = order_cancelled(order_id)
    for envelope in (request, request, cancelled, cancelled, request):
        await pipeline.send(envelope)

    pipeline.start_worker()
    await pipeline.wait_for_status(order_id, "REFUNDED")
    events = await pipeline.published(order_id, 2)
    await asyncio.sleep(1)
    again = await pipeline.published(order_id, 2)

    assert [event["event_type"] for event in events] == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    assert len(again) == 2


async def test_a_malformed_message_is_dead_lettered_and_the_next_one_is_processed(
    pipeline: Pipeline,
) -> None:
    request = payment_requested(card_last4="1111")
    await pipeline.publisher.publish(OutgoingMessage(pipeline.settings.topic, "bad", b"{nope"))
    await pipeline.send(request)

    pipeline.start_worker()
    await pipeline.wait_for_status(request.payload.order_id, "SUCCEEDED")


async def test_the_worker_stops_promptly_when_asked(pipeline: Pipeline) -> None:
    pipeline.start_worker()
    await asyncio.sleep(1)

    await pipeline.stop_worker()

    assert pipeline.task is not None
    assert pipeline.task.done()
