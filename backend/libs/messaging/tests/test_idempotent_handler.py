from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    ClaimMode,
    DeadLetter,
    EventConsumer,
    Handler,
    InMemoryBroker,
    InMemorySource,
    Outcome,
    OutgoingMessage,
    RetryPolicy,
    idempotent_handler,
    standalone_handler,
    transactional_handler,
)
from ecommerce_messaging.ports import IncomingMessage

TOPIC = "sample.events"
CORRELATION = UUID("0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44")


class Sample(BaseModel):
    number: int


def envelope(number: int = 1, event_type: str = "sample.created") -> Envelope[Sample]:
    return Envelope[Sample](
        event_id=uuid4(),
        event_type=event_type,
        event_version=1,
        correlation_id=CORRELATION,
        producer="test",
        payload=Sample(number=number),
    )


class Harness:
    def __init__(self) -> None:
        self.broker = InMemoryBroker()
        self.source: InMemorySource = self.broker.source([TOPIC])
        self.seen: list[int] = []
        self.failures: list[Exception] = []
        self.sleeps: list[float] = []
        self.dead: list[DeadLetter] = []

    async def remember(self, item: Envelope[Sample]) -> None:
        if self.failures:
            raise self.failures.pop(0)
        self.seen.append(item.payload.number)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    async def hook(self, letter: DeadLetter) -> None:
        self.dead.append(letter)

    async def send(self, item: Envelope[Sample]) -> IncomingMessage:
        await self.broker.publish(OutgoingMessage(TOPIC, "key", item.model_dump_json().encode()))
        message = await self.source.poll(0)
        assert message is not None
        return message

    def consumer(self, attempts: int = 3) -> EventConsumer:
        return EventConsumer(
            group="group-a",
            source=self.source,
            dead_letters=self.broker,
            handlers=[idempotent_handler("sample.created", 1, Sample, self.remember)],
            retry=RetryPolicy(max_attempts=attempts, base_delay_seconds=0.5, max_delay_seconds=2.0),
            on_dead_letter=self.hook,
            sleep=self.sleep,
        )


async def test_an_idempotent_handler_runs_without_any_claim_storage() -> None:
    harness = Harness()
    message = await harness.send(envelope(4))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.PROCESSED
    assert harness.seen == [4]
    assert harness.source.commits == [message]


async def test_the_same_event_delivered_twice_reaches_the_handler_twice() -> None:
    harness = Harness()
    message = await harness.send(envelope(4))
    consumer = harness.consumer()

    await consumer.handle(message)
    await consumer.handle(message)

    assert harness.seen == [4, 4]


async def test_a_failing_idempotent_handler_is_retried_with_backoff() -> None:
    harness = Harness()
    harness.failures = [RuntimeError("redis down"), RuntimeError("redis down")]
    message = await harness.send(envelope(2))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.PROCESSED
    assert harness.seen == [2]
    assert harness.sleeps == [0.5, 1.0]


async def test_a_handler_that_keeps_failing_goes_to_the_dead_letter_topic() -> None:
    harness = Harness()
    harness.failures = [ValueError("bad")] * 3
    message = await harness.send(envelope(2))

    outcome = await harness.consumer().handle(message)

    [dead] = harness.broker.messages(TOPIC + ".dlq")
    assert outcome is Outcome.DEAD_LETTERED
    assert dead.value == message.value
    assert dead.headers["x-attempts"] == b"3"
    assert len(harness.dead) == 1
    assert harness.source.commits == [message]


async def test_events_without_a_handler_are_ignored_and_committed() -> None:
    harness = Harness()
    message = await harness.send(envelope(1, "other.created"))

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.IGNORED
    assert harness.seen == []
    assert harness.source.commits == [message]


async def test_an_invalid_payload_is_dead_lettered_without_calling_the_handler() -> None:
    harness = Harness()
    await harness.broker.publish(
        OutgoingMessage(
            TOPIC,
            "key",
            envelope().model_dump_json().replace('"number":1', '"number":"x"').encode(),
        )
    )
    message = await harness.source.poll(0)
    assert message is not None

    outcome = await harness.consumer().handle(message)

    assert outcome is Outcome.DEAD_LETTERED
    assert harness.seen == []


def test_the_handler_declares_that_it_skips_the_claim() -> None:
    handler = idempotent_handler("sample.created", 1, Sample, Harness().remember)

    assert handler.claim is ClaimMode.NONE


async def noop(item: Envelope[Sample]) -> None:
    return None


async def noop_in_session(item: Envelope[Sample], session: AsyncSession) -> None:
    return None


@pytest.mark.parametrize(
    "handler",
    [
        standalone_handler("sample.created", 1, Sample, noop),
        transactional_handler("sample.created", 1, Sample, noop_in_session),
    ],
)
def test_handlers_that_claim_events_need_claim_storage(handler: Handler) -> None:
    harness = Harness()

    with pytest.raises(ValueError, match="session factory and a claim table"):
        EventConsumer(
            group="group-a",
            source=harness.source,
            dead_letters=harness.broker,
            handlers=[handler],
        )


def test_a_consumer_with_only_idempotent_handlers_needs_no_claim_storage() -> None:
    assert Harness().consumer() is not None
