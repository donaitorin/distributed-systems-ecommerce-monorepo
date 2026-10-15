import asyncio
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from aiokafka import AIOKafkaConsumer
from pydantic import BaseModel
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    EventConsumer,
    KafkaPublisher,
    KafkaSettings,
    KafkaSource,
    OutgoingMessage,
    RetryPolicy,
    processed_events_table,
    standalone_handler,
)
from kafka_support import KafkaBroker
from postgres_support import PostgresServer

pytestmark = pytest.mark.integration

POISON = 13


class Sample(BaseModel):
    number: int


class Cluster:
    def __init__(self, kafka: KafkaBroker, engine: AsyncEngine) -> None:
        self.kafka = kafka
        self.settings = KafkaSettings(kafka.bootstrap, "test", publish_timeout_seconds=10)
        self.metadata = MetaData()
        self.processed = processed_events_table(self.metadata)
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.topic = f"sample-{uuid4().hex}"
        self.group = f"group-{uuid4().hex}"
        self.seen: list[int] = []
        self.changed = asyncio.Event()
        self.publisher = KafkaPublisher(self.settings)

    def consumer(self) -> tuple[EventConsumer, KafkaSource]:
        async def handle(item: Envelope[Sample]) -> None:
            if item.payload.number == POISON:
                raise ValueError("poison pill")
            self.seen.append(item.payload.number)
            self.changed.set()

        source = KafkaSource(self.settings, [self.topic], self.group)
        consumer = EventConsumer(
            group=self.group,
            source=source,
            dead_letters=self.publisher,
            session_factory=self.sessions,
            processed_events=self.processed,
            handlers=[standalone_handler("sample.created", 1, Sample, handle)],
            retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.05),
            poll_timeout_seconds=0.5,
        )
        return consumer, source

    async def send(self, number: int, event_id: UUID | None = None) -> None:
        item = Envelope[Sample](
            event_id=event_id or uuid4(),
            event_type="sample.created",
            event_version=1,
            correlation_id=uuid4(),
            producer="test",
            payload=Sample(number=number),
        )
        await self.publisher.publish(
            OutgoingMessage(self.topic, "key", item.model_dump_json().encode())
        )

    async def wait_for(self, count: int) -> None:
        async with asyncio.timeout(60):
            while len(self.seen) < count:
                self.changed.clear()
                await self.changed.wait()

    async def read_dead_letters(self, count: int) -> list[dict[str, bytes]]:
        reader = AIOKafkaConsumer(
            self.topic + ".dlq",
            bootstrap_servers=self.kafka.bootstrap,
            group_id=f"reader-{uuid4().hex}",
            auto_offset_reset="earliest",
        )
        await reader.start()
        found: list[dict[str, bytes]] = []
        try:
            async with asyncio.timeout(30):
                while len(found) < count:
                    for records in (await reader.getmany(timeout_ms=1000)).values():
                        found.extend(dict(record.headers) for record in records)
        finally:
            await reader.stop()
        return found


@pytest.fixture
async def cluster(kafka: KafkaBroker, postgres_server: PostgresServer) -> AsyncIterator[Cluster]:
    engine = create_async_engine(postgres_server.create_database())
    prepared = Cluster(kafka, engine)
    async with engine.begin() as connection:
        await connection.run_sync(prepared.metadata.create_all)
    yield prepared
    await prepared.publisher.close()
    await engine.dispose()


async def run_until(cluster: Cluster, count: int) -> None:
    consumer, source = cluster.consumer()
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))
    try:
        await cluster.wait_for(count)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=20)
        await source.close()


async def test_events_flow_through_kafka_and_a_poison_event_lands_in_the_dead_letter_topic(
    cluster: Cluster,
) -> None:
    for number in (1, 2, POISON, 3):
        await cluster.send(number)

    await run_until(cluster, 3)

    assert cluster.seen == [1, 2, 3]
    [headers] = await cluster.read_dead_letters(1)
    assert headers["x-error"] == b"poison pill"
    assert headers["x-original-topic"] == cluster.topic.encode()
    assert headers["x-attempts"] == b"2"
    assert headers["x-consumer-group"] == cluster.group.encode()


async def test_the_same_event_delivered_twice_has_one_effect(cluster: Cluster) -> None:
    repeated = uuid4()
    await cluster.send(1, repeated)
    await cluster.send(1, repeated)
    await cluster.send(2)

    await run_until(cluster, 2)

    assert cluster.seen == [1, 2]


async def test_a_restarted_consumer_continues_after_the_last_committed_message(
    cluster: Cluster,
) -> None:
    await cluster.send(1)
    await cluster.send(2)
    await run_until(cluster, 2)

    await cluster.send(3)
    await run_until(cluster, 3)

    assert cluster.seen == [1, 2, 3]
