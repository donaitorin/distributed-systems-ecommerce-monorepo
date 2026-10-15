import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import Column, Integer, MetaData, Table, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    DeadLetter,
    EventConsumer,
    Handler,
    InMemoryBroker,
    InMemorySource,
    Outcome,
    OutgoingMessage,
    RetryPolicy,
    processed_events_table,
    standalone_handler,
    transactional_handler,
)
from ecommerce_messaging.errors import ConsumeError
from ecommerce_messaging.ports import IncomingMessage
from postgres_support import PostgresServer

pytestmark = pytest.mark.integration

TOPIC = "sample.events"
CORRELATION = UUID("0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44")


class Sample(BaseModel):
    number: int


class Database:
    def __init__(self, engine: AsyncEngine) -> None:
        self.metadata = MetaData()
        self.processed = processed_events_table(self.metadata)
        self.effects = Table("effects", self.metadata, Column("number", Integer))
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def effect_numbers(self) -> list[int]:
        async with self.sessions() as session:
            return list((await session.scalars(select(self.effects.c.number))).all())

    async def claims(self, group: str = "group-a") -> int:
        async with self.sessions() as session:
            statement = (
                select(func.count())
                .select_from(self.processed)
                .where(self.processed.c.consumer_group == group)
            )
            return int(await session.scalar(statement) or 0)


@pytest.fixture
async def database(postgres_server: PostgresServer) -> AsyncIterator[Database]:
    engine = create_async_engine(postgres_server.create_database())
    prepared = Database(engine)
    async with engine.begin() as connection:
        await connection.run_sync(prepared.metadata.create_all)
    yield prepared
    await engine.dispose()


def envelope(
    number: int = 1,
    event_type: str = "sample.created",
    version: int = 1,
    event_id: UUID | None = None,
) -> Envelope[Sample]:
    return Envelope[Sample](
        event_id=event_id or uuid4(),
        event_type=event_type,
        event_version=version,
        correlation_id=CORRELATION,
        producer="test",
        payload=Sample(number=number),
    )


class Harness:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.broker = InMemoryBroker()
        self.source: InMemorySource = self.broker.source([TOPIC])
        self.sleeps: list[float] = []
        self.seen: list[int] = []
        self.dead: list[DeadLetter] = []
        self.failures: list[Exception] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    async def send(self, item: Envelope[Sample], key: str = "key-1") -> IncomingMessage:
        await self.broker.publish(OutgoingMessage(TOPIC, key, item.model_dump_json().encode()))
        message = await self.source.poll(0)
        assert message is not None
        return message

    async def send_raw(self, value: bytes, key: str = "key-1") -> IncomingMessage:
        await self.broker.publish(OutgoingMessage(TOPIC, key, value, {"trace": b"abc"}))
        message = await self.source.poll(0)
        assert message is not None
        return message

    def consumer(
        self, handlers: list[Handler] | None = None, group: str = "group-a", attempts: int = 3
    ) -> EventConsumer:
        async def remember(item: Envelope[Sample]) -> None:
            if self.failures:
                raise self.failures.pop(0)
            self.seen.append(item.payload.number)

        async def hook(letter: DeadLetter) -> None:
            self.dead.append(letter)

        return EventConsumer(
            group=group,
            source=self.source,
            dead_letters=self.broker,
            session_factory=self.database.sessions,
            processed_events=self.database.processed,
            handlers=handlers or [standalone_handler("sample.created", 1, Sample, remember)],
            retry=RetryPolicy(max_attempts=attempts, base_delay_seconds=0.5, max_delay_seconds=2.0),
            on_dead_letter=hook,
            sleep=self.sleep,
        )

    def dead_letters(self) -> list[IncomingMessage]:
        return self.broker.messages(TOPIC + ".dlq")


@pytest.fixture
def harness(database: Database) -> Harness:
    return Harness(database)


async def test_a_message_is_handled_recorded_and_committed(harness: Harness) -> None:
    message = await harness.send(envelope(5))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.PROCESSED
    assert harness.seen == [5]
    assert await harness.database.claims() == 1
    assert harness.source.commits == [message]


async def test_the_handler_receives_a_typed_envelope(harness: Harness) -> None:
    received: list[Envelope[Any]] = []

    async def capture(item: Envelope[Sample]) -> None:
        received.append(item)

    original = envelope(9)
    message = await harness.send(original)

    await harness.consumer([standalone_handler("sample.created", 1, Sample, capture)]).handle(
        message
    )

    assert received[0].event_id == original.event_id
    assert isinstance(received[0].payload, Sample)
    assert received[0].payload.number == 9
    assert received[0].correlation_id == CORRELATION


async def test_a_redelivered_event_is_handled_only_once(harness: Harness) -> None:
    item = envelope(1)
    first, second = await harness.send(item), await harness.send(item)
    consumer = harness.consumer()

    outcomes = [await consumer.handle(first), await consumer.handle(second)]

    assert outcomes == [Outcome.PROCESSED, Outcome.DUPLICATE]
    assert harness.seen == [1]
    assert len(harness.source.commits) == 2


async def test_each_consumer_group_handles_the_same_event_once(harness: Harness) -> None:
    item = envelope(1)
    message = await harness.send(item)

    await harness.consumer(group="group-a").handle(message)
    await harness.consumer(group="group-b").handle(message)
    await harness.consumer(group="group-a").handle(message)

    assert harness.seen == [1, 1]


async def test_transactional_handlers_commit_their_work_together_with_the_claim(
    harness: Harness,
) -> None:
    async def write(item: Envelope[Sample], session: AsyncSession) -> None:
        await session.execute(harness.database.effects.insert().values(number=item.payload.number))

    consumer = harness.consumer([transactional_handler("sample.created", 1, Sample, write)])
    message = await harness.send(envelope(3))

    await consumer.handle(message)
    await consumer.handle(message)

    assert await harness.database.effect_numbers() == [3]
    assert await harness.database.claims() == 1


async def test_a_failing_transactional_handler_leaves_no_trace_and_succeeds_on_retry(
    harness: Harness,
) -> None:
    calls = {"count": 0}

    async def flaky(item: Envelope[Sample], session: AsyncSession) -> None:
        await session.execute(harness.database.effects.insert().values(number=item.payload.number))
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom after writing")

    consumer = harness.consumer([transactional_handler("sample.created", 1, Sample, flaky)])
    message = await harness.send(envelope(4))

    outcome = await consumer.handle(message)

    assert outcome is Outcome.PROCESSED
    assert calls["count"] == 2
    assert await harness.database.effect_numbers() == [4]
    assert await harness.database.claims() == 1
    assert harness.dead_letters() == []


async def test_failures_are_retried_with_exponential_backoff_and_then_succeed(
    harness: Harness,
) -> None:
    harness.failures = [RuntimeError("one"), RuntimeError("two")]
    message = await harness.send(envelope(1))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.PROCESSED
    assert harness.sleeps == [0.5, 1.0]
    assert harness.seen == [1]
    assert harness.dead_letters() == []


async def test_a_message_that_keeps_failing_goes_to_the_dead_letter_topic(
    harness: Harness,
) -> None:
    harness.failures = [RuntimeError("one"), RuntimeError("two"), ValueError("bad data")]
    message = await harness.send(envelope(1), key="order-7")

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    [dead] = harness.dead_letters()
    assert dead.key == "order-7"
    assert dead.value == message.value
    assert dead.headers["x-error"] == b"bad data"
    assert dead.headers["x-error-type"] == b"ValueError"
    assert dead.headers["x-attempts"] == b"3"
    assert dead.headers["x-original-topic"] == TOPIC.encode()
    assert dead.headers["x-original-partition"] == b"0"
    assert dead.headers["x-original-offset"] == b"0"
    assert dead.headers["x-consumer-group"] == b"group-a"
    assert harness.source.commits == [message]
    assert harness.seen == []
    assert await harness.database.claims() == 0
    assert harness.sleeps == [0.5, 1.0]


async def test_the_dead_letter_hook_receives_the_failure(harness: Harness) -> None:
    harness.failures = [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")]
    item = envelope(1)
    message = await harness.send(item)

    await harness.consumer().handle(message)

    [letter] = harness.dead
    assert letter.envelope is not None
    assert letter.envelope.event_id == item.event_id
    assert (letter.error, letter.error_type, letter.attempts, letter.group) == (
        "c",
        "RuntimeError",
        3,
        "group-a",
    )


async def test_a_failing_dead_letter_hook_does_not_stop_the_consumer(harness: Harness) -> None:
    harness.failures = [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")]

    async def broken_hook(letter: DeadLetter) -> None:
        raise RuntimeError("hook failed")

    consumer = EventConsumer(
        group="group-a",
        source=harness.source,
        dead_letters=harness.broker,
        session_factory=harness.database.sessions,
        processed_events=harness.database.processed,
        handlers=[
            standalone_handler(
                "sample.created", 1, Sample, lambda item: _raise(harness.failures.pop(0))
            )
        ],
        retry=RetryPolicy(max_attempts=3),
        on_dead_letter=broken_hook,
        sleep=harness.sleep,
    )
    message = await harness.send(envelope(1))

    assert await consumer.handle(message) is Outcome.DEAD_LETTERED


async def _raise(error: Exception) -> None:
    raise error


@pytest.mark.parametrize(
    "value",
    [b"not json at all", b"[]", b"{}", b'{"event_type": "sample.created"}', b""],
    ids=["text", "array", "empty-object", "partial", "empty"],
)
async def test_a_malformed_message_goes_straight_to_the_dead_letter_topic(
    harness: Harness, value: bytes
) -> None:
    message = await harness.send_raw(value)

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    assert harness.sleeps == []
    [dead] = harness.dead_letters()
    assert dead.value == value
    assert dead.headers["trace"] == b"abc"
    assert dead.headers["x-attempts"] == b"0"
    assert dead.headers["x-error-type"] == b"InvalidEventError"
    assert harness.seen == []


async def test_a_payload_that_does_not_match_its_contract_is_dead_lettered_without_retries(
    harness: Harness,
) -> None:
    raw = envelope(1).model_dump(mode="json")
    raw["payload"] = {"number": "not a number"}
    message = await harness.send_raw(__import__("json").dumps(raw).encode())

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    assert harness.sleeps == []
    assert len(harness.dead_letters()) == 1
    assert harness.dead[0].error_type == "ValidationError"


async def test_event_types_nobody_handles_are_skipped_and_committed(harness: Harness) -> None:
    message = await harness.send(envelope(1, event_type="sample.deleted"))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.IGNORED
    assert harness.source.commits == [message]
    assert harness.dead_letters() == []
    assert harness.seen == []


async def test_an_unsupported_version_of_a_known_event_is_dead_lettered(harness: Harness) -> None:
    message = await harness.send(envelope(1, version=2))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    assert "unsupported version 2" in harness.dead[0].error


async def test_standalone_handlers_claim_only_after_they_succeed(harness: Harness) -> None:
    order: list[str] = []

    async def record(item: Envelope[Sample]) -> None:
        order.append(f"handled claims={await harness.database.claims()}")

    consumer = harness.consumer([standalone_handler("sample.created", 1, Sample, record)])
    message = await harness.send(envelope(1))

    await consumer.handle(message)
    await consumer.handle(message)

    assert order == ["handled claims=0"]
    assert await harness.database.claims() == 1


async def test_a_standalone_handler_that_succeeded_but_whose_claim_was_lost_runs_again(
    harness: Harness,
) -> None:
    item = envelope(1)
    message = await harness.send(item)
    consumer = harness.consumer()
    async with harness.database.sessions() as session:
        assert (
            await session.scalar(select(func.count()).select_from(harness.database.processed)) == 0
        )

    await consumer.handle(message)
    async with harness.database.sessions() as session, session.begin():
        await session.execute(harness.database.processed.delete())
    await consumer.handle(message)

    assert harness.seen == [1, 1]


async def test_if_the_dead_letter_topic_is_down_the_offset_is_not_committed(
    harness: Harness,
) -> None:
    harness.failures = [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")]
    message = await harness.send(envelope(1))
    stop = asyncio.Event()
    stop.set()
    harness.broker.available = False

    with pytest.raises(Exception, match="unavailable"):
        await harness.consumer().handle(message, stop)

    assert harness.source.commits == []
    harness.broker.available = True
    harness.failures = [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")]
    assert await harness.consumer().handle(message) is Outcome.DEAD_LETTERED
    assert len(harness.dead_letters()) == 1


async def test_the_dead_letter_write_is_retried_until_the_topic_comes_back(
    harness: Harness,
) -> None:
    harness.failures = [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")]
    message = await harness.send(envelope(1))
    harness.broker.available = False
    attempts = {"sleeps": 0}
    original_sleep = harness.sleep

    async def sleep_then_recover(seconds: float) -> None:
        await original_sleep(seconds)
        attempts["sleeps"] += 1
        if attempts["sleeps"] >= 4:
            harness.broker.available = True

    consumer = harness.consumer()
    consumer._sleep = sleep_then_recover

    outcome = await consumer.handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    assert len(harness.dead_letters()) == 1


async def test_the_run_loop_processes_messages_until_stopped(harness: Harness) -> None:
    for number in range(3):
        await harness.broker.publish(
            OutgoingMessage(TOPIC, "k", envelope(number).model_dump_json().encode())
        )
    stop = asyncio.Event()
    consumer = harness.consumer()
    task = asyncio.create_task(consumer.run(stop))

    for _ in range(100):
        if len(harness.seen) == 3:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert harness.seen == [0, 1, 2]
    assert len(harness.source.commits) == 3


class FlakySource:
    def __init__(self, inner: InMemorySource) -> None:
        self.inner = inner
        self.poll_failures = 2
        self.commit_failures = 1

    async def poll(self, timeout_seconds: float) -> IncomingMessage | None:
        if self.poll_failures:
            self.poll_failures -= 1
            raise ConsumeError("kafka is down")
        return await self.inner.poll(timeout_seconds)

    async def commit(self, message: IncomingMessage) -> None:
        if self.commit_failures:
            self.commit_failures -= 1
            raise ConsumeError("commit failed")
        await self.inner.commit(message)

    async def close(self) -> None:
        return None


async def test_the_run_loop_survives_source_errors_and_a_redelivery_is_a_duplicate(
    harness: Harness,
) -> None:
    await harness.broker.publish(
        OutgoingMessage(TOPIC, "k", envelope(1).model_dump_json().encode())
    )
    flaky = FlakySource(harness.source)
    consumer = harness.consumer()
    consumer._source = flaky
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))

    for _ in range(100):
        if flaky.inner.commits:
            break
        await asyncio.sleep(0.02)
        if flaky.poll_failures == 0 and flaky.commit_failures == 0 and not flaky.inner.commits:
            flaky.inner.restart()
    stop.set()
    await asyncio.wait_for(task, timeout=5)

    assert harness.seen == [1]
    assert await harness.database.claims() == 1
    assert harness.sleeps[:2] == [0.5, 1.0]


def test_two_handlers_for_the_same_event_and_version_are_rejected(database: Database) -> None:
    async def noop(item: Envelope[Sample]) -> None:
        return None

    harness = Harness(database)

    with pytest.raises(ValueError, match="registered twice"):
        harness.consumer(
            [
                standalone_handler("sample.created", 1, Sample, noop),
                standalone_handler("sample.created", 1, Sample, noop),
            ]
        )


@pytest.mark.parametrize(
    ("attempt", "delay"), [(1, 0.5), (2, 1.0), (3, 2.0), (4, 4.0), (5, 8.0), (9, 8.0)]
)
def test_the_retry_delay_doubles_up_to_the_maximum(attempt: int, delay: float) -> None:
    assert RetryPolicy(base_delay_seconds=0.5, max_delay_seconds=8.0).delay(attempt) == delay
