from uuid import UUID

import pytest
from orders_testing.data import CUSTOMER, SteppingClock, order_request
from orders_testing.events import (
    outgoing,
    payment_failed,
    payment_refunded,
    payment_succeeded,
    reservation_failed,
    stock_reserved,
)

from ecommerce_contracts import (
    INVENTORY_TOPIC,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
)
from ecommerce_messaging import ClaimMode, EventConsumer, InMemoryBroker, InMemorySource
from orders.application.orders import OrderService
from orders.application.saga import OrderSaga
from orders.domain.status import OrderStatus
from orders.infra.memory import InMemoryStore, InMemoryUnitOfWork
from orders.worker import (
    CONSUMER_GROUP,
    SAGA_TOPICS,
    build_consumer,
    saga_handlers,
)

LINES = [("RS-001", "Rust in Action", 2, "39.90"), ("XS-001", "Sticker Pack", 1, "12.50")]


@pytest.fixture
def saga(store: InMemoryStore, clock: SteppingClock) -> OrderSaga:
    return OrderSaga(lambda: InMemoryUnitOfWork(store), clock)


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> OrderService:
    return OrderService(lambda: InMemoryUnitOfWork(store), clock)


def wire(saga: OrderSaga) -> tuple[InMemoryBroker, EventConsumer, InMemorySource]:
    broker = InMemoryBroker()
    source = broker.source(SAGA_TOPICS)
    return broker, build_consumer(saga, source, broker), source


async def drain(consumer: EventConsumer, source: InMemorySource) -> None:
    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)


async def place(service: OrderService) -> UUID:
    return (await service.place(CUSTOMER, "worker-key-001", order_request(), UUID(int=1))).order_id


def test_the_worker_listens_to_inventory_and_payments_in_one_group() -> None:
    assert SAGA_TOPICS == (INVENTORY_TOPIC, PAYMENTS_TOPIC)
    assert CONSUMER_GROUP == "orders-saga"


def test_every_saga_event_has_a_handler_that_relies_on_the_state_machine(saga: OrderSaga) -> None:
    handlers = saga_handlers(saga)

    assert {(item.event_type, item.version) for item in handlers} == {
        (STOCK_RESERVED, 1),
        (STOCK_RESERVATION_FAILED, 1),
        (PAYMENT_SUCCEEDED, 1),
        (PAYMENT_FAILED, 1),
        (PAYMENT_REFUNDED, 1),
    }
    assert {item.claim for item in handlers} == {ClaimMode.NONE}


async def test_events_drive_an_order_to_confirmed_and_replays_change_nothing(
    saga: OrderSaga, service: OrderService, store: InMemoryStore
) -> None:
    order_id = await place(service)
    broker, consumer, source = wire(saga)
    reserved = stock_reserved(order_id, LINES)
    paid = payment_succeeded(order_id)
    for envelope in (reserved, reserved, paid, paid, reserved):
        await broker.publish(outgoing(envelope))

    await drain(consumer, source)

    order = await service.get_any(order_id)
    assert order.status is OrderStatus.CONFIRMED
    assert len(order.history) == 4
    assert [line.name for line in order.lines] == ["Rust in Action", "Sticker Pack"]
    assert len(store.outbox) == 3


async def test_a_declined_payment_cancels_through_the_consumer(
    saga: OrderSaga, service: OrderService
) -> None:
    order_id = await place(service)
    broker, consumer, source = wire(saga)
    for envelope in (stock_reserved(order_id, LINES), payment_failed(order_id)):
        await broker.publish(outgoing(envelope))

    await drain(consumer, source)

    order = await service.get_any(order_id)
    assert (order.status, order.cancel_reason) == (OrderStatus.CANCELLED, "payment_failed")


async def test_a_failed_reservation_cancels_through_the_consumer(
    saga: OrderSaga, service: OrderService
) -> None:
    order_id = await place(service)
    broker, consumer, source = wire(saga)
    await broker.publish(outgoing(reservation_failed(order_id, "price_changed")))

    await drain(consumer, source)

    assert (await service.get_any(order_id)).cancel_reason == "price_changed"


async def test_a_refund_event_adds_one_history_row_even_when_delivered_twice(
    saga: OrderSaga, service: OrderService
) -> None:
    order_id = await place(service)
    broker, consumer, source = wire(saga)
    refund = payment_refunded(order_id)
    for envelope in (reservation_failed(order_id), refund, refund):
        await broker.publish(outgoing(envelope))

    await drain(consumer, source)

    order = await service.get_any(order_id)
    assert order.status is OrderStatus.CANCELLED
    assert [entry.reason for entry in order.history].count("payment refunded") == 1


async def test_an_event_for_an_unknown_order_does_not_dead_letter(saga: OrderSaga) -> None:
    broker, consumer, source = wire(saga)
    await broker.publish(outgoing(payment_succeeded(UUID(int=404))))

    await drain(consumer, source)

    assert broker.messages("payments.events.dlq") == []
