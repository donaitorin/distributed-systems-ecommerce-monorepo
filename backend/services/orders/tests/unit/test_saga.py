from uuid import UUID

import pytest
from orders_testing.data import CUSTOMER, SteppingClock, order_request

from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_PAYMENT_REQUESTED,
    OrderCancelledV1,
    OrderConfirmedV1,
    OrderPaymentRequestedV1,
)
from orders.application.orders import OrderService
from orders.application.saga import OrderSaga
from orders.domain.order import Order
from orders.domain.status import OrderStatus
from orders.infra.memory import InMemoryStore, InMemoryUnitOfWork

NAMES = {"RS-001": "Rust in Action", "XS-001": "Sticker Pack"}


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> OrderService:
    return OrderService(lambda: InMemoryUnitOfWork(store), clock)


@pytest.fixture
def saga(store: InMemoryStore, clock: SteppingClock) -> OrderSaga:
    return OrderSaga(lambda: InMemoryUnitOfWork(store), clock)


async def place(service: OrderService, lines: list[tuple[str, int, str]] | None = None) -> UUID:
    placed = await service.place(
        CUSTOMER, f"key-{len(lines or [])}-{id(lines)}", order_request(lines), UUID(int=9)
    )
    return placed.order_id


def event_types(store: InMemoryStore) -> list[str]:
    return [entry.event_type for entry in store.outbox]


def statuses(order: Order) -> list[OrderStatus]:
    return [entry.to_status for entry in order.history]


async def test_a_paid_order_goes_pending_reserved_paid_confirmed(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)

    await saga.stock_reserved(order_id, NAMES)
    await saga.payment_succeeded(order_id)

    order = await service.get_any(order_id)
    assert order.status is OrderStatus.CONFIRMED
    assert statuses(order) == [
        OrderStatus.PENDING,
        OrderStatus.STOCK_RESERVED,
        OrderStatus.PAID,
        OrderStatus.CONFIRMED,
    ]
    assert [line.name for line in order.lines] == ["Rust in Action", "Sticker Pack"]
    assert event_types(store) == [ORDER_CREATED, ORDER_PAYMENT_REQUESTED, ORDER_CONFIRMED]


async def test_the_payment_request_carries_the_total_and_only_the_card_ending(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)

    await saga.stock_reserved(order_id, NAMES)

    request = store.outbox[1].payload
    assert isinstance(request, OrderPaymentRequestedV1)
    assert (str(request.amount), request.currency, request.card_last4) == ("92.30", "USD", "1111")
    assert store.outbox[1].correlation_id == UUID(int=9)


async def test_the_confirmation_lists_the_purchased_lines_for_the_cart(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)
    await saga.stock_reserved(order_id, NAMES)

    await saga.payment_succeeded(order_id)

    confirmed = store.outbox[-1].payload
    assert isinstance(confirmed, OrderConfirmedV1)
    assert confirmed.customer_id == CUSTOMER
    assert [(line.sku, line.quantity) for line in confirmed.lines] == [("RS-001", 2), ("XS-001", 1)]
    assert str(confirmed.total) == "92.30"


async def test_an_order_worth_nothing_is_confirmed_without_asking_for_payment(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service, [("GIFT-1", 1, "0.00")])

    await saga.stock_reserved(order_id, {"GIFT-1": "Gift"})

    order = await service.get_any(order_id)
    assert order.status is OrderStatus.CONFIRMED
    assert statuses(order) == [
        OrderStatus.PENDING,
        OrderStatus.STOCK_RESERVED,
        OrderStatus.CONFIRMED,
    ]
    assert event_types(store) == [ORDER_CREATED, ORDER_CONFIRMED]


@pytest.mark.parametrize("reason", ["insufficient_stock", "product_unavailable", "price_changed"])
async def test_a_failed_reservation_cancels_the_order_with_the_reason(
    service: OrderService, saga: OrderSaga, store: InMemoryStore, reason: str
) -> None:
    order_id = await place(service)

    await saga.reservation_failed(order_id, reason)

    order = await service.get_any(order_id)
    assert (order.status, order.cancel_reason) == (OrderStatus.CANCELLED, reason)
    assert order.history[-1].reason == reason
    cancelled = store.outbox[-1]
    assert cancelled.event_type == ORDER_CANCELLED
    assert isinstance(cancelled.payload, OrderCancelledV1)
    assert cancelled.payload.reason == reason


async def test_a_failed_payment_cancels_the_order(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)
    await saga.stock_reserved(order_id, NAMES)

    await saga.payment_failed(order_id)

    order = await service.get_any(order_id)
    assert (order.status, order.cancel_reason) == (OrderStatus.CANCELLED, "payment_failed")
    assert event_types(store)[-1] == ORDER_CANCELLED


async def test_redelivered_events_change_nothing(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)
    await saga.stock_reserved(order_id, NAMES)
    await saga.payment_succeeded(order_id)
    snapshot = (store.orders[order_id], list(store.outbox))

    await saga.stock_reserved(order_id, NAMES)
    await saga.payment_succeeded(order_id)
    await saga.payment_failed(order_id)
    await saga.reservation_failed(order_id, "insufficient_stock")

    assert (store.orders[order_id], store.outbox) == snapshot


async def test_late_events_cannot_resurrect_a_cancelled_order(
    service: OrderService, saga: OrderSaga, store: InMemoryStore
) -> None:
    order_id = await place(service)
    await saga.reservation_failed(order_id, "insufficient_stock")
    snapshot = (store.orders[order_id], list(store.outbox))

    await saga.stock_reserved(order_id, NAMES)
    await saga.payment_succeeded(order_id)

    assert (store.orders[order_id], store.outbox) == snapshot


async def test_events_for_an_unknown_order_are_ignored(
    saga: OrderSaga, store: InMemoryStore
) -> None:
    unknown = UUID(int=404)

    await saga.stock_reserved(unknown, NAMES)
    await saga.reservation_failed(unknown, "insufficient_stock")
    await saga.payment_succeeded(unknown)
    await saga.payment_failed(unknown)
    await saga.payment_refunded(unknown)

    assert not store.orders
    assert not store.outbox


async def test_a_refund_after_cancellation_is_recorded_once_and_the_order_stays_cancelled(
    service: OrderService, saga: OrderSaga, store: InMemoryStore, clock: SteppingClock
) -> None:
    order_id = await place(service)
    await saga.stock_reserved(order_id, NAMES)
    await saga.payment_failed(order_id)
    clock.advance(seconds=90)

    await saga.payment_refunded(order_id)
    await saga.payment_refunded(order_id)

    order = await service.get_any(order_id)
    assert order.status is OrderStatus.CANCELLED
    assert order.refunded_at == clock.now
    refund = order.history[-1]
    assert (refund.from_status, refund.to_status, refund.reason) == (
        OrderStatus.CANCELLED,
        OrderStatus.CANCELLED,
        "payment refunded",
    )
    assert [entry.reason for entry in order.history].count("payment refunded") == 1


async def test_a_refund_for_an_order_that_is_not_cancelled_is_ignored(
    service: OrderService, saga: OrderSaga
) -> None:
    order_id = await place(service)

    await saga.payment_refunded(order_id)

    order = await service.get_any(order_id)
    assert order.refunded_at is None
    assert order.status is OrderStatus.PENDING
