import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from payments_testing.data import (
    RecordingProvider,
    SteppingClock,
    order_cancelled,
    outgoing,
    payment_requested,
)
from payments_testing.waiting import eventually

from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
)
from ecommerce_messaging import ClaimMode, InMemoryBroker
from payments.application.processor import PaymentProcessor
from payments.domain.payment import PaymentStatus
from payments.infra.memory import InMemoryStore, InMemoryUnitOfWork
from payments.infra.simulated import SimulatedPaymentProvider
from payments.worker import CONSUMER_GROUP, build_consumer, order_handlers, run_settlement

DELAY = timedelta(seconds=90)


@pytest.fixture
def provider(clock: SteppingClock) -> RecordingProvider:
    return RecordingProvider(SimulatedPaymentProvider(DELAY, clock))


@pytest.fixture
def processor(
    store: InMemoryStore, provider: RecordingProvider, clock: SteppingClock
) -> PaymentProcessor:
    return PaymentProcessor(lambda: InMemoryUnitOfWork(store), provider, clock)


def test_the_worker_listens_to_order_events_in_its_own_group(processor: PaymentProcessor) -> None:
    handlers = order_handlers(processor)

    assert CONSUMER_GROUP == "payments-order-events"
    assert {(item.event_type, item.version) for item in handlers} == {
        (ORDER_PAYMENT_REQUESTED, 1),
        (ORDER_CANCELLED, 1),
    }
    assert {item.claim for item in handlers} == {ClaimMode.NONE}


async def test_a_payment_request_and_a_cancellation_flow_through_the_consumer(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    broker = InMemoryBroker()
    source = broker.source([ORDERS_TOPIC])
    consumer = build_consumer(processor, source, broker)
    request = payment_requested(card_last4="1111")
    order_id = request.payload.order_id
    for envelope in (request, request, order_cancelled(order_id), order_cancelled(order_id)):
        await broker.publish(outgoing(envelope))

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert store.payments[order_id].status is PaymentStatus.REFUNDED
    assert [entry.event_type for entry in store.outbox] == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    assert broker.messages("orders.events.dlq") == []


async def test_unrelated_order_events_are_skipped(
    processor: PaymentProcessor, store: InMemoryStore
) -> None:
    broker = InMemoryBroker()
    source = broker.source([ORDERS_TOPIC])
    consumer = build_consumer(processor, source, broker)
    confirmed = order_cancelled(uuid4()).model_copy(update={"event_type": "order.confirmed"})
    await broker.publish(outgoing(confirmed))

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert not store.payments
    assert broker.messages("orders.events.dlq") == []


async def test_the_settlement_loop_finishes_late_payments_and_survives_failures(
    processor: PaymentProcessor,
    store: InMemoryStore,
    clock: SteppingClock,
    provider: RecordingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = payment_requested(card_last4="2222")
    await processor.charge_requested(request.payload, request.correlation_id)
    clock.advance(seconds=91)
    real = processor.settle_due
    failures = 0

    async def flaky() -> int:
        nonlocal failures
        if failures < 2:
            failures += 1
            raise RuntimeError("database down")
        return await real()

    monkeypatch.setattr(processor, "settle_due", flaky)
    stop = asyncio.Event()

    task = asyncio.create_task(run_settlement(processor, stop, 0.01))
    await eventually(
        lambda: store.payments[request.payload.order_id].status is PaymentStatus.SUCCEEDED,
        seconds=5,
        interval=0.01,
    )
    stop.set()
    await task

    assert failures == 2
    assert len(provider.checks) == 1
