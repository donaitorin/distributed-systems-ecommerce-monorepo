import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel
from sqlalchemy import MetaData, Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    KafkaPublisher,
    KafkaSettings,
    OutboxRelay,
    OutboxWriter,
    OutgoingMessage,
    PublishError,
    outbox_table,
)
from kafka_support import KafkaBroker
from postgres_support import PostgresServer

pytestmark = pytest.mark.integration


class Sample(BaseModel):
    number: int


async def read(bootstrap: str, topic: str, count: int) -> list[tuple[str | None, bytes]]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=f"reader-{uuid4().hex}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    found: list[tuple[str | None, bytes]] = []
    try:
        async with asyncio.timeout(30):
            while len(found) < count:
                batch = await consumer.getmany(timeout_ms=1000)
                for records in batch.values():
                    found.extend(
                        (record.key.decode() if record.key else None, record.value)
                        for record in records
                    )
    finally:
        await consumer.stop()
    return found


def settings(broker: KafkaBroker) -> KafkaSettings:
    return KafkaSettings(broker.bootstrap, "test", publish_timeout_seconds=5)


async def test_a_message_reaches_kafka_with_its_key_value_and_headers(kafka: KafkaBroker) -> None:
    topic = f"t-{uuid4().hex}"
    publisher = KafkaPublisher(settings(kafka))

    await publisher.publish(OutgoingMessage(topic, "order-1", b'{"a":1}', {"h": b"x"}))
    await publisher.close()

    assert await read(kafka.bootstrap, topic, 1) == [("order-1", b'{"a":1}')]


async def test_messages_with_the_same_key_keep_their_order(kafka: KafkaBroker) -> None:
    topic = f"t-{uuid4().hex}"
    publisher = KafkaPublisher(settings(kafka))

    for number in range(20):
        await publisher.publish(OutgoingMessage(topic, "same-key", str(number).encode()))
    await publisher.close()

    values = [value for _, value in await read(kafka.bootstrap, topic, 20)]
    assert values == [str(number).encode() for number in range(20)]


async def test_an_unreachable_broker_is_a_publish_error_not_a_hang() -> None:
    publisher = KafkaPublisher(KafkaSettings("127.0.0.1:1", "test", publish_timeout_seconds=2))

    with pytest.raises(PublishError):
        await publisher.publish(OutgoingMessage("t", "k", b"v"))

    await publisher.close()


async def test_closing_an_unused_publisher_is_harmless() -> None:
    await KafkaPublisher(KafkaSettings("127.0.0.1:1")).close()


@pytest.fixture
async def outbox(
    postgres_server: PostgresServer,
) -> AsyncIterator[tuple[Table, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(postgres_server.create_database())
    metadata = MetaData()
    table = outbox_table(metadata)
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    yield table, async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_events_written_while_kafka_is_down_leave_when_it_comes_back(
    stoppable_kafka: KafkaBroker, outbox: tuple[Table, async_sessionmaker[AsyncSession]]
) -> None:
    table, sessions = outbox
    writer = OutboxWriter(table, "test-service")
    topic = f"t-{uuid4().hex}"
    publisher = KafkaPublisher(settings(stoppable_kafka))
    relay = OutboxRelay(table, sessions, publisher, poll_interval_seconds=0.05)
    stoppable_kafka.stop()

    async with sessions() as session, session.begin():
        await writer.add(
            session,
            topic=topic,
            key="k",
            event_type="sample.created",
            payload=Sample(number=1),
            correlation_id=uuid4(),
        )
    with pytest.raises(PublishError):
        await relay.drain_once()

    stoppable_kafka.start()
    delivered = 0
    for _ in range(30):
        try:
            delivered = await relay.drain_once()
            break
        except PublishError:
            await asyncio.sleep(1)
    await publisher.close()

    assert delivered == 1
    [(key, value)] = await read(stoppable_kafka.bootstrap, topic, 1)
    assert key == "k"
    assert Envelope[Sample].model_validate_json(value).payload.number == 1
