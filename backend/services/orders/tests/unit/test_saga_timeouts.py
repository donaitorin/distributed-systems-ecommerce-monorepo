import asyncio
from datetime import timedelta
from uuid import UUID

import pytest
from orders_testing.data import CUSTOMER, SteppingClock, order_request
from orders_testing.waiting import eventually

from ecommerce_contracts import ORDER_CANCELLED
from orders.application.orders import OrderService
from orders.application.saga import OrderSaga, SagaTimeouts
from orders.domain.status import SAGA_TIMEOUT, OrderStatus
from orders.infra.memory import InMemoryStore, InMemoryUnitOfWork

TIMEOUT = timedelta(seconds=60)


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> OrderService:
    return OrderService(lambda: InMemoryUnitOfWork(store), clock)


@pytest.fixture
def saga(store: InMemoryStore, clock: SteppingClock) -> OrderSaga:
    return OrderSaga(lambda: InMemoryUnitOfWork(store), clock)


@pytest.fixture
def timeouts(store: InMemoryStore, clock: SteppingClock) -> SagaTimeouts:
    return SagaTimeouts(lambda: InMemoryUnitOfWork(store), TIMEOUT, clock, batch_size=2)


async def place(service: OrderService, key: str) -> UUID:
    return (await service.place(CUSTOMER, key, order_request(), UUID(int=3))).order_id


async def test_an_order_stuck_in_pending_is_cancelled_after_the_timeout(
    service: OrderService, timeouts: SagaTimeouts, clock: SteppingClock, store: InMemoryStore
) -> None:
    order_id = await place(service, "key-pending-1")
    clock.advance(seconds=60)

    await timeouts.sweep()

    order = await service.get_any(order_id)
    assert (order.status, order.cancel_reason) == (OrderStatus.CANCELLED, SAGA_TIMEOUT)
    assert store.outbox[-1].event_type == ORDER_CANCELLED


async def test_an_order_stuck_waiting_for_payment_is_cancelled_too(
    service: OrderService,
    saga: OrderSaga,
    timeouts: SagaTimeouts,
    clock: SteppingClock,
) -> None:
    order_id = await place(service, "key-reserved-1")
    await saga.stock_reserved(order_id, {})
    clock.advance(seconds=61)

    await timeouts.sweep()

    assert (await service.get_any(order_id)).status is OrderStatus.CANCELLED


async def test_orders_inside_the_timeout_are_left_alone(
    service: OrderService, timeouts: SagaTimeouts, clock: SteppingClock
) -> None:
    order_id = await place(service, "key-fresh-1")
    clock.advance(seconds=59)

    assert await timeouts.sweep() == 0

    assert (await service.get_any(order_id)).status is OrderStatus.PENDING


async def test_confirmed_and_already_cancelled_orders_are_never_touched(
    service: OrderService,
    saga: OrderSaga,
    timeouts: SagaTimeouts,
    clock: SteppingClock,
    store: InMemoryStore,
) -> None:
    confirmed = await place(service, "key-confirmed-1")
    await saga.stock_reserved(confirmed, {})
    await saga.payment_succeeded(confirmed)
    cancelled = await place(service, "key-cancelled-1")
    await saga.reservation_failed(cancelled, "insufficient_stock")
    clock.advance(seconds=3600)
    events = len(store.outbox)

    assert await timeouts.sweep() == 0

    assert (await service.get_any(confirmed)).status is OrderStatus.CONFIRMED
    assert (await service.get_any(cancelled)).cancel_reason == "insufficient_stock"
    assert len(store.outbox) == events


async def test_sweeping_twice_cancels_each_order_once(
    service: OrderService, timeouts: SagaTimeouts, clock: SteppingClock, store: InMemoryStore
) -> None:
    await place(service, "key-twice-001")
    clock.advance(seconds=61)

    await timeouts.sweep()
    await timeouts.sweep()

    assert [entry.event_type for entry in store.outbox].count(ORDER_CANCELLED) == 1


async def test_the_run_loop_drains_more_than_one_batch_and_purges_old_keys(
    service: OrderService, timeouts: SagaTimeouts, clock: SteppingClock, store: InMemoryStore
) -> None:
    ids = [await place(service, f"key-batch-{index:03d}") for index in range(5)]
    clock.advance(days=2)
    stop = asyncio.Event()

    task = asyncio.create_task(timeouts.run(stop, 0.01))
    await eventually(
        lambda: (
            all(store.orders[item].status is OrderStatus.CANCELLED for item in ids)
            and not store.idempotency
        ),
        seconds=5,
        interval=0.01,
    )
    stop.set()
    await task

    assert not store.idempotency


async def test_a_failing_sweep_is_logged_and_does_not_stop_the_loop(
    timeouts: SagaTimeouts, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def broken() -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("database down")

    monkeypatch.setattr(timeouts, "sweep", broken)
    stop = asyncio.Event()

    task = asyncio.create_task(timeouts.run(stop, 0.01))
    await eventually(lambda: calls >= 3, seconds=5, interval=0.01)
    stop.set()
    await task

    assert calls >= 3
