import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import MetaData, func, select, text, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    InMemoryBroker,
    OutboxRelay,
    OutboxWriter,
    OutgoingMessage,
    PublishError,
    outbox_table,
)
from postgres_support import PostgresServer

pytestmark = pytest.mark.integration

CORRELATION = UUID("0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44")


class Sample(BaseModel):
    number: int


class Database:
    def __init__(self, engine: AsyncEngine) -> None:
        self.metadata = MetaData()
        self.table = outbox_table(self.metadata)
        self.engine = engine
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.writer = OutboxWriter(self.table, "test-service")

    async def add(self, number: int, key: str = "k1", topic: str = "t") -> Envelope[Sample]:
        async with self.sessions() as session, session.begin():
            return await self.writer.add(
                session,
                topic=topic,
                key=key,
                event_type="sample.created",
                payload=Sample(number=number),
                correlation_id=CORRELATION,
            )

    async def count(self, published: bool | None = None) -> int:
        statement = select(func.count()).select_from(self.table)
        if published is True:
            statement = statement.where(self.table.c.published_at.is_not(None))
        if published is False:
            statement = statement.where(self.table.c.published_at.is_(None))
        async with self.sessions() as session:
            return int(await session.scalar(statement) or 0)

    def relay(self, publisher: object, **options: object) -> OutboxRelay:
        return OutboxRelay(
            self.table,
            self.sessions,
            publisher,  # type: ignore[arg-type]
            poll_interval_seconds=0.05,
            **options,  # type: ignore[arg-type]
        )


@pytest.fixture
async def database(postgres_server: PostgresServer) -> AsyncIterator[Database]:
    engine = create_async_engine(postgres_server.create_database())
    prepared = Database(engine)
    async with engine.begin() as connection:
        await connection.run_sync(prepared.metadata.create_all)
    yield prepared
    await engine.dispose()


def numbers(broker: InMemoryBroker, topic: str = "t") -> list[int]:
    return [
        Envelope[Sample].model_validate_json(item.value).payload.number
        for item in broker.messages(topic)
    ]


async def test_the_writer_stores_a_complete_envelope(database: Database) -> None:
    envelope = await database.add(7, key="order-1", topic="orders.events")

    async with database.sessions() as session:
        row = (await session.execute(select(database.table))).one()
    stored = Envelope[Sample].model_validate_json(row.payload)
    assert (row.topic, row.key, row.event_id) == ("orders.events", "order-1", envelope.event_id)
    assert stored == envelope
    assert stored.producer == "test-service"
    assert stored.correlation_id == CORRELATION
    assert (stored.event_type, stored.event_version, stored.payload.number) == (
        "sample.created",
        1,
        7,
    )
    assert row.published_at is None


async def test_nothing_is_stored_when_the_surrounding_transaction_rolls_back(
    database: Database,
) -> None:
    async with database.sessions() as session:
        await database.writer.add(
            session,
            topic="t",
            key="k",
            event_type="sample.created",
            payload=Sample(number=1),
            correlation_id=CORRELATION,
        )
        await session.rollback()

    assert await database.count() == 0


async def test_the_relay_publishes_in_order_and_marks_rows_published(database: Database) -> None:
    for number in range(5):
        await database.add(number)
    broker = InMemoryBroker()

    delivered = await database.relay(broker).drain_once()

    assert delivered == 5
    assert numbers(broker) == [0, 1, 2, 3, 4]
    assert await database.count(published=False) == 0
    assert broker.published[0].key == "k1"


async def test_published_rows_are_not_sent_again(database: Database) -> None:
    await database.add(1)
    broker = InMemoryBroker()
    relay = database.relay(broker)
    await relay.drain_once()

    assert await relay.drain_once() == 0
    assert numbers(broker) == [1]


async def test_batches_are_limited_by_the_batch_size(database: Database) -> None:
    for number in range(5):
        await database.add(number)
    broker = InMemoryBroker()
    relay = database.relay(broker, batch_size=2)

    assert [await relay.drain_once(), await relay.drain_once(), await relay.drain_once()] == [
        2,
        2,
        1,
    ]
    assert numbers(broker) == [0, 1, 2, 3, 4]


class FailsAfter:
    def __init__(self, successes: int) -> None:
        self.broker = InMemoryBroker()
        self.remaining = successes

    async def publish(self, message: OutgoingMessage) -> None:
        if self.remaining <= 0:
            raise PublishError("kafka is down")
        self.remaining -= 1
        await self.broker.publish(message)

    async def close(self) -> None:
        return None


async def test_a_failure_keeps_the_unsent_rows_and_the_order(database: Database) -> None:
    for number in range(4):
        await database.add(number)
    flaky = FailsAfter(2)
    relay = database.relay(flaky)

    with pytest.raises(PublishError):
        await relay.drain_once()

    assert numbers(flaky.broker) == [0, 1]
    assert await database.count(published=False) == 2
    flaky.remaining = 10
    assert await relay.drain_once() == 2
    assert numbers(flaky.broker) == [0, 1, 2, 3]


class CrashesAfterPublishing:
    def __init__(self, broker: InMemoryBroker) -> None:
        self.broker = broker
        self.armed = True

    async def publish(self, message: OutgoingMessage) -> None:
        await self.broker.publish(message)
        if self.armed:
            raise RuntimeError("process died before the row was marked")

    async def close(self) -> None:
        return None


async def test_a_crash_between_publishing_and_marking_delivers_again_with_the_same_event_id(
    database: Database,
) -> None:
    envelope = await database.add(1)
    broker = InMemoryBroker()
    crashing = CrashesAfterPublishing(broker)
    relay = database.relay(crashing)

    with pytest.raises(RuntimeError):
        await relay.drain_once()
    crashing.armed = False
    await relay.drain_once()

    delivered = [Envelope[Sample].model_validate_json(item.value) for item in broker.published]
    assert [item.event_id for item in delivered] == [envelope.event_id, envelope.event_id]
    assert await database.count(published=False) == 0


async def test_only_one_relay_publishes_at_a_time(database: Database) -> None:
    await database.add(1)
    broker = InMemoryBroker()
    relay = database.relay(broker)
    async with database.sessions() as holder, holder.begin():
        await holder.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": relay._lock_id}
        )

        assert await relay.drain_once() == 0

    assert await relay.drain_once() == 1


async def test_two_relays_running_together_publish_every_row_once(database: Database) -> None:
    for number in range(20):
        await database.add(number)
    broker = InMemoryBroker()

    results = await asyncio.gather(
        database.relay(broker, batch_size=5).drain_once(),
        database.relay(broker, batch_size=5).drain_once(),
        database.relay(broker, batch_size=5).drain_once(),
    )
    while await database.relay(broker, batch_size=5).drain_once():
        pass

    assert sum(results) <= 15
    assert sorted(numbers(broker)) == list(range(20))


async def test_the_run_loop_delivers_new_rows_and_stops_on_request(database: Database) -> None:
    broker = InMemoryBroker()
    stop = asyncio.Event()
    task = asyncio.create_task(database.relay(broker).run(stop))

    await database.add(1)
    await database.add(2)
    for _ in range(100):
        if len(broker.published) == 2:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert numbers(broker) == [1, 2]


async def test_the_run_loop_survives_an_outage_and_delivers_when_the_broker_returns(
    database: Database,
) -> None:
    await database.add(1)
    broker = InMemoryBroker()
    broker.available = False
    stop = asyncio.Event()
    task = asyncio.create_task(database.relay(broker).run(stop))

    await asyncio.sleep(0.3)
    assert broker.published == []
    assert not task.done()
    broker.available = True
    for _ in range(200):
        if broker.published:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert numbers(broker) == [1]


async def test_old_published_rows_are_purged_and_recent_ones_kept(database: Database) -> None:
    for number in range(3):
        await database.add(number)
    broker = InMemoryBroker()
    relay = database.relay(broker, retention=timedelta(hours=1))
    await relay.drain_once()
    async with database.sessions() as session, session.begin():
        await session.execute(
            update(database.table)
            .where(database.table.c.id == select(func.min(database.table.c.id)).scalar_subquery())
            .values(published_at=datetime.now(UTC) - timedelta(hours=2))
        )
    unpublished = await database.add(99)

    purged = await relay.purge_published()

    assert purged == 1
    assert await database.count() == 3
    assert unpublished.event_id != uuid4()
    assert await database.count(published=False) == 1
