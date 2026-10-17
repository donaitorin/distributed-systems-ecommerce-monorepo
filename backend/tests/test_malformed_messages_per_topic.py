import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest

from accounts.worker import build_consumer as accounts_auth_consumer
from cart.worker import build_consumer as cart_catalog_consumer
from cart.worker import build_purchase_consumer as cart_orders_consumer
from catalog.worker import build_consumer as catalog_imports_consumer
from catalog.worker import build_orders_consumer as catalog_orders_consumer
from ecommerce_messaging import (
    EventConsumer,
    InMemoryBroker,
    InMemorySource,
    OutgoingMessage,
    RetryPolicy,
)
from ecommerce_messaging.ports import IncomingMessage, MessageSource, Publisher
from orders.worker import build_consumer as orders_saga_consumer
from payments.worker import build_consumer as payments_orders_consumer

ORDERS = "orders.events"
INVENTORY = "inventory.events"
PAYMENTS = "payments.events"
CATALOG = "catalog.events"
IMPORTS = "imports.jobs"
AUTH = "auth.events"
NO_RETRY = RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0)
SECRET = "grace.hopper@example.com"

type Build = Callable[[MessageSource, Publisher], EventConsumer]


def anything() -> Any:
    return object()


@dataclass(frozen=True, slots=True)
class Case:
    consumer: str
    topics: tuple[str, ...]
    build: Build


CASES = [
    Case(
        "orders saga",
        (INVENTORY, PAYMENTS),
        lambda source, dead: orders_saga_consumer(anything(), source, dead, retry=NO_RETRY),
    ),
    Case(
        "payments",
        (ORDERS,),
        lambda source, dead: payments_orders_consumer(anything(), source, dead, retry=NO_RETRY),
    ),
    Case(
        "catalog stock",
        (ORDERS,),
        lambda source, dead: catalog_orders_consumer(anything(), source, dead, retry=NO_RETRY),
    ),
    Case(
        "cart purchases",
        (ORDERS,),
        lambda source, dead: cart_orders_consumer(source, dead, anything(), retry=NO_RETRY),
    ),
    Case(
        "cart projection",
        (CATALOG,),
        lambda source, dead: cart_catalog_consumer(source, dead, anything(), retry=NO_RETRY),
    ),
    Case(
        "catalog imports",
        (IMPORTS,),
        lambda source, dead: catalog_imports_consumer(
            anything(),
            source,
            dead,
            anything(),
            retry=NO_RETRY,
        ),
    ),
    Case(
        "accounts",
        (AUTH,),
        lambda source, dead: accounts_auth_consumer(source, dead, anything(), retry=NO_RETRY),
    ),
]

SPECIFIC_TOPICS = sorted({topic for case in CASES for topic in case.topics})


def unrelated_event() -> bytes:
    return json.dumps(
        {
            "event_id": str(uuid4()),
            "event_type": "unrelated.thing_happened",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "correlation_id": str(uuid4()),
            "producer": "test",
            "payload": {},
        }
    ).encode()


def malformed_messages() -> list[bytes]:
    return [
        f'{{"email": "{SECRET}", "card": '.encode(),
        json.dumps({"event_type": "not an event", "payload": SECRET}).encode(),
    ]


class SignalingSource(InMemorySource):
    def __init__(self, broker: InMemoryBroker, topics: tuple[str, ...], expected: int) -> None:
        super().__init__(broker, topics)
        self.expected = expected
        self.reached = asyncio.Event()

    async def commit(self, message: IncomingMessage) -> None:
        await super().commit(message)
        if len(self.commits) >= self.expected:
            self.reached.set()


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.consumer)
async def test_malformed_messages_in_every_topic_land_in_its_dead_letter_topic_without_blocking(
    case: Case,
) -> None:
    broker = InMemoryBroker()
    sent = len(case.topics) * (len(malformed_messages()) + 1)
    source = SignalingSource(broker, case.topics, sent)
    consumer = case.build(source, broker)
    index = 0
    for topic in case.topics:
        for value in [*malformed_messages(), unrelated_event()]:
            await broker.publish(OutgoingMessage(topic, f"key-{index}", value))
            index += 1
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))

    try:
        await asyncio.wait_for(source.reached.wait(), timeout=10)
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=10)

    for topic in case.topics:
        dead = broker.messages(topic + ".dlq")
        assert [message.value for message in dead] == malformed_messages()
        for message in dead:
            assert message.headers["x-original-topic"] == topic.encode()
            assert message.headers["x-error-type"] == b"InvalidEventError"
            assert SECRET.encode() not in message.headers["x-error"]
        committed = {m.offset for m in source.commits if m.topic == topic}
        assert committed == {0, 1, 2}


def test_every_topic_with_a_consumer_is_covered() -> None:
    assert sorted({ORDERS, INVENTORY, PAYMENTS, CATALOG, IMPORTS, AUTH}) == SPECIFIC_TOPICS
