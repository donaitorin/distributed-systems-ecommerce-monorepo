import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from accounts_testing.data import START
from accounts_testing.events import outgoing, registered_event, role_changed_event
from aiokafka import AIOKafkaConsumer
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine

from accounts.infra.database import create_engine
from accounts.worker import WorkerSettings, run_worker
from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutgoingMessage
from kafka_support import KafkaBroker

pytestmark = pytest.mark.integration

T1 = START + timedelta(minutes=1)
T2 = START + timedelta(minutes=2)


@dataclass(slots=True)
class Pipeline:
    kafka: KafkaBroker
    engine: AsyncEngine
    settings: WorkerSettings
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

    async def send(self, message: OutgoingMessage) -> None:
        await self.publisher.publish(message)

    async def row(self, user_id: UUID) -> tuple[str | None, str, object] | None:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT email, role, role_updated_at FROM profiles WHERE user_id = :id"),
                {"id": user_id},
            )
            found = result.first()
        return None if found is None else (found[0], found[1], found[2])

    async def wait_for_profile(self, user_id: UUID, role: str | None = None) -> None:
        async with asyncio.timeout(60):
            while True:
                found = await self.row(user_id)
                if found is not None and (role is None or found[1] == role):
                    return
                await asyncio.sleep(0.2)

    async def processed(self) -> int:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT count(*) FROM processed_events WHERE consumer_group = :group"),
                {"group": self.settings.group},
            )
            return int(result.scalar_one())

    async def dead_letters(self, count: int) -> list[dict[str, bytes]]:
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
async def pipeline(kafka: KafkaBroker, migrated_database_url: str) -> AsyncIterator[Pipeline]:
    kafka_settings = KafkaSettings(kafka.bootstrap, "accounts-test", publish_timeout_seconds=10)
    settings = WorkerSettings(
        database_url=make_url(migrated_database_url),
        kafka=kafka_settings,
        topic=f"auth.events.{uuid4().hex}",
        group=f"accounts-auth-events-{uuid4().hex}",
    )
    engine = create_engine(migrated_database_url)
    prepared = Pipeline(kafka, engine, settings, KafkaPublisher(kafka_settings))
    yield prepared
    await prepared.stop_worker()
    await prepared.publisher.close()
    await engine.dispose()


async def test_events_published_before_the_worker_started_build_the_profile_with_the_last_role(
    pipeline: Pipeline,
) -> None:
    user_id = uuid4()
    await pipeline.send(outgoing(registered_event(user_id, START), pipeline.topic))
    await pipeline.send(outgoing(role_changed_event(user_id, T1, new_role="admin"), pipeline.topic))
    await pipeline.send(
        outgoing(
            role_changed_event(user_id, T2, new_role="manager", old_role="admin"), pipeline.topic
        )
    )

    pipeline.start_worker()
    await pipeline.wait_for_profile(user_id, role="manager")

    email, role, stamped = await pipeline.row(user_id) or (None, "", None)
    assert (email, role, stamped) == ("ada@example.com", "manager", T2)
    assert await pipeline.processed() == 3


async def test_a_republished_event_leaves_the_processed_count_unchanged(
    pipeline: Pipeline,
) -> None:
    first, second = uuid4(), uuid4()
    event = registered_event(first, START)
    await pipeline.send(outgoing(event, pipeline.topic))
    pipeline.start_worker()
    await pipeline.wait_for_profile(first)
    assert await pipeline.processed() == 1

    await pipeline.send(outgoing(event, pipeline.topic))
    await pipeline.send(outgoing(registered_event(second, START), pipeline.topic))
    await pipeline.wait_for_profile(second)

    assert await pipeline.processed() == 2


async def test_a_malformed_message_is_dead_lettered_and_the_next_one_is_processed(
    pipeline: Pipeline,
) -> None:
    user_id = uuid4()
    await pipeline.send(OutgoingMessage(pipeline.topic, "bad", b"{this is not json"))
    await pipeline.send(outgoing(registered_event(user_id, START), pipeline.topic))

    pipeline.start_worker()
    await pipeline.wait_for_profile(user_id)

    [headers] = await pipeline.dead_letters(1)
    assert headers["x-original-topic"] == pipeline.topic.encode()
    assert headers["x-consumer-group"] == pipeline.settings.group.encode()
    assert headers["x-error"].startswith(b"not a valid event envelope")
    assert headers["x-attempts"] == b"0"
    assert await pipeline.processed() == 1


async def test_the_worker_stops_promptly_when_asked(pipeline: Pipeline) -> None:
    pipeline.start_worker()
    await asyncio.sleep(1)

    await pipeline.stop_worker()

    assert pipeline.task is not None
    assert pipeline.task.done()
