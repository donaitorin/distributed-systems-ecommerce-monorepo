import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from orders_testing.waiting import eventually

from saga_harness import WAIT_SECONDS, Infrastructure, Saga, running_saga

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]

OUTAGE_OBSERVATION_SECONDS = 3.0
ORDERS_DURING_OUTAGE = 3
SAGA_TIMEOUT_LONGER_THAN_THE_OUTAGE_SECONDS = 180.0


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def saga(infrastructure: Infrastructure) -> AsyncIterator[Saga]:
    async with running_saga(
        infrastructure, saga_timeout_seconds=SAGA_TIMEOUT_LONGER_THAN_THE_OUTAGE_SECONDS
    ) as running:
        yield running


@asynccontextmanager
async def kafka_down(saga: Saga) -> AsyncIterator[None]:
    broker = saga.infrastructure.kafka
    await asyncio.to_thread(broker.pause)
    try:
        yield
    finally:
        await asyncio.to_thread(broker.resume)


async def place_and_confirm(saga: Saga, customer: UUID, sku: str) -> str:
    order_id = (await saga.place(customer, sku, "1111")).json()["id"]
    await saga.wait_for_status(customer, order_id, "CONFIRMED")
    return str(order_id)


async def test_with_kafka_stopped_orders_are_accepted_and_complete_after_the_restart(
    saga: Saga,
) -> None:
    earlier_customer, earlier_sku = uuid4(), await saga.add_product(stock=5)
    earlier = await place_and_confirm(saga, earlier_customer, earlier_sku)
    customers = [uuid4() for _ in range(ORDERS_DURING_OUTAGE)]
    skus = [await saga.add_product(stock=5) for _ in customers]

    async with kafka_down(saga):
        placed = [
            await saga.place(customer, sku, "1111")
            for customer, sku in zip(customers, skus, strict=True)
        ]
        ids = [response.json()["id"] for response in placed]

        async def outbox_holds_them() -> bool:
            return await saga.unpublished_orders_events() >= ORDERS_DURING_OUTAGE

        await eventually(outbox_holds_them, seconds=WAIT_SECONDS, interval=0.2)
        await asyncio.sleep(OUTAGE_OBSERVATION_SECONDS)
        during = [
            await saga.order(customer, order_id)
            for customer, order_id in zip(customers, ids, strict=True)
        ]
        assert [response.status_code for response in placed] == [202] * ORDERS_DURING_OUTAGE
        assert {order["status"] for order in during} == {"PENDING"}
        assert [await saga.stock(sku) for sku in skus] == [5] * ORDERS_DURING_OUTAGE

    for customer, order_id in zip(customers, ids, strict=True):
        await saga.wait_for_status(customer, order_id, "CONFIRMED")

    async def outbox_is_drained() -> bool:
        return await saga.unpublished_orders_events() == 0

    await eventually(outbox_is_drained, seconds=WAIT_SECONDS, interval=0.2)
    for sku, order_id in zip(skus, ids, strict=True):
        assert await saga.stock(sku) == 3
        assert await saga.payment_rows(order_id) == 1
        assert await saga.history_rows(order_id, "CONFIRMED") == 1
        assert await saga.history_rows(order_id, "STOCK_RESERVED") == 1
    assert await saga.stock(earlier_sku) == 3
    assert await saga.payment_rows(earlier) == 1
    assert await saga.history_rows(earlier, "CONFIRMED") == 1


async def test_an_idempotency_key_used_during_a_kafka_outage_still_buys_once(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    key = f"e2e-{uuid4().hex}"

    async with kafka_down(saga):
        first = await saga.place(customer, sku, "1111", key=key)
        second = await saga.place(customer, sku, "1111", key=key)
        assert first.status_code == 202
        assert second.json() == first.json()
        assert second.headers["idempotent-replay"] == "true"

    order_id = first.json()["id"]
    await saga.wait_for_status(customer, order_id, "CONFIRMED")
    assert await saga.stock(sku) == 3
    assert await saga.payment_rows(order_id) == 1
