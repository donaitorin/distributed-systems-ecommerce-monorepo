from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
from orders_testing.waiting import eventually

from saga_harness import WAIT_SECONDS, Saga

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


@asynccontextmanager
async def payments_stopped(saga: Saga) -> AsyncIterator[None]:
    await saga.workers.stop("payments")
    try:
        yield
    finally:
        if not saga.workers.is_running("payments"):
            saga.workers.start("payments")


async def stock_is(saga: Saga, sku: str, expected: int) -> None:
    async def reached() -> bool:
        return await saga.stock(sku) == expected

    await eventually(reached, seconds=WAIT_SECONDS, interval=0.2)


async def place_and_confirm(saga: Saga, customer: UUID, sku: str) -> str:
    order_id = (await saga.place(customer, sku, "1111")).json()["id"]
    await saga.wait_for_status(customer, order_id, "CONFIRMED")
    return str(order_id)


async def test_with_payments_stopped_the_timeout_cancels_the_order_and_nothing_is_charged_twice(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    await saga.put_in_cart(customer, sku)

    async with payments_stopped(saga):
        placed = await saga.place(customer, sku, "1111")
        order_id = placed.json()["id"]
        waiting = await saga.wait_for_status(customer, order_id, "STOCK_RESERVED")
        assert placed.status_code == 202
        assert waiting["status"] == "STOCK_RESERVED"
        assert await saga.stock(sku) == 3
        assert await saga.payment_rows(order_id) == 0

        cancelled = await saga.wait_for_status(customer, order_id, "CANCELLED")
        await stock_is(saga, sku, 5)
        assert cancelled["cancel_reason"] == "saga_timeout"
        assert await saga.payment_rows(order_id) == 0
        assert await saga.cart_skus(customer) == [sku]

    refunded = await saga.wait_for_payment(customer, order_id, "REFUNDED")
    correlation = await saga.correlation_of(order_id)
    await saga.wait_for_events(correlation, {"payment.succeeded", "payment.refunded"})
    order = await saga.order(customer, order_id)

    assert refunded["refunded_at"] is not None
    assert await saga.payment_rows(order_id) == 1
    assert saga.count_events(correlation, "payment.succeeded") == 1
    assert saga.count_events(correlation, "payment.refunded") == 1
    assert order["status"] == "CANCELLED"
    assert await saga.history_rows(order_id, "CONFIRMED") == 0
    assert await saga.stock(sku) == 5


async def test_with_payments_back_new_orders_are_confirmed(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    async with payments_stopped(saga):
        stalled = (await saga.place(customer, sku, "1111")).json()["id"]
        await saga.wait_for_status(customer, stalled, "CANCELLED")

    fresh_customer, fresh_sku = uuid4(), await saga.add_product(stock=5)
    order_id = await place_and_confirm(saga, fresh_customer, fresh_sku)

    assert await saga.stock(fresh_sku) == 3
    assert await saga.payment_rows(order_id) == 1
    assert (await saga.payment(fresh_customer, order_id) or {})["status"] == "SUCCEEDED"
