import asyncio
from uuid import uuid4

import pytest
from orders_testing.waiting import eventually

from saga_harness import WAIT_SECONDS, Saga, history_of

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


async def test_an_approved_card_confirms_the_order_takes_the_stock_and_empties_the_cart_line(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    other = await saga.add_product()
    await saga.put_in_cart(customer, sku)
    await saga.put_in_cart(customer, other)

    placed = await saga.place(customer, sku, "1111")
    order_id = placed.json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CONFIRMED")
    payment = await saga.payment(customer, order_id)

    assert placed.status_code == 202
    assert [(a, b) for a, b, _ in history_of(order)] == [
        (None, "PENDING"),
        ("PENDING", "STOCK_RESERVED"),
        ("STOCK_RESERVED", "PAID"),
        ("PAID", "CONFIRMED"),
    ]
    assert order["lines"][0]["name"] == "Saga Widget"
    assert await saga.stock(sku) == 3
    assert payment is not None
    assert (payment["status"], payment["card_last4"], payment["amount"]) == (
        "SUCCEEDED",
        "1111",
        "20.00",
    )

    async def purchased_line_is_gone() -> bool:
        return await saga.cart_skus(customer) == [other]

    await eventually(purchased_line_is_gone, seconds=WAIT_SECONDS, interval=0.2)


async def test_one_order_can_be_followed_across_the_topics_by_its_correlation_id(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product()
    order_id = (await saga.place(customer, sku, "1111")).json()["id"]
    await saga.wait_for_status(customer, order_id, "CONFIRMED")
    correlation = await saga.correlation_of(order_id)

    await saga.wait_for_events(
        correlation,
        {
            "order.created",
            "stock.reserved",
            "order.payment_requested",
            "payment.succeeded",
            "order.confirmed",
            "product.updated",
        },
    )

    events = saga.events_of(correlation)
    by_topic = {(event["topic"], event["event_type"]) for event in events}
    assert ("orders.events", "order.created") in by_topic
    assert ("inventory.events", "stock.reserved") in by_topic
    assert ("payments.events", "payment.succeeded") in by_topic
    assert ("catalog.events", "product.updated") in by_topic
    assert {event["payload"].get("order_id", order_id) for event in events} == {order_id}


async def test_a_declined_card_cancels_the_order_and_gives_the_stock_back(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    await saga.put_in_cart(customer, sku)

    order_id = (await saga.place(customer, sku, "0000")).json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    async def stock_is_back() -> bool:
        return await saga.stock(sku) == 5

    await eventually(stock_is_back, seconds=WAIT_SECONDS, interval=0.2)
    payment = await saga.payment(customer, order_id)
    events = await saga.wait_for_events(
        await saga.correlation_of(order_id), {"stock.released", "payment.failed", "order.cancelled"}
    )

    assert order["cancel_reason"] == "payment_failed"
    assert ("STOCK_RESERVED", "CANCELLED", "payment_failed") in history_of(order)
    assert payment is not None
    assert (payment["status"], payment["failure_reason"]) == ("FAILED", "card_declined")
    assert "payment.refunded" not in events
    assert await saga.cart_skus(customer) == [sku]


async def test_a_card_that_never_answers_is_cancelled_by_the_timeout_and_the_stock_returns(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    await saga.put_in_cart(customer, sku)
    order_id = (await saga.place(customer, sku, "9999")).json()["id"]

    stalled = await saga.wait_for_status(customer, order_id, "STOCK_RESERVED")
    assert await saga.stock(sku) == 3
    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    async def stock_is_back() -> bool:
        return await saga.stock(sku) == 5

    await eventually(stock_is_back, seconds=WAIT_SECONDS, interval=0.2)
    payment = await saga.payment(customer, order_id)
    assert stalled["status"] == "STOCK_RESERVED"
    assert order["cancel_reason"] == "saga_timeout"
    assert payment is not None
    assert payment["status"] == "PENDING"
    assert await saga.cart_skus(customer) == [sku]


async def test_a_late_approval_after_the_timeout_is_refunded_and_the_order_stays_cancelled(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    order_id = (await saga.place(customer, sku, "2222")).json()["id"]

    cancelled = await saga.wait_for_status(customer, order_id, "CANCELLED")
    still_pending = await saga.payment(customer, order_id)
    refunded = await saga.wait_for_payment(customer, order_id, "REFUNDED")

    async def refund_is_in_the_order() -> bool:
        return (await saga.order(customer, order_id))["refunded_at"] is not None

    await eventually(refund_is_in_the_order, seconds=WAIT_SECONDS, interval=0.2)
    order = await saga.order(customer, order_id)
    events = await saga.wait_for_events(
        await saga.correlation_of(order_id), {"payment.succeeded", "payment.refunded"}
    )

    assert cancelled["cancel_reason"] == "saga_timeout"
    assert still_pending is not None
    assert still_pending["status"] == "PENDING"
    assert refunded["refunded_at"] is not None
    assert order["status"] == "CANCELLED"
    assert history_of(order)[-2:] == [
        ("STOCK_RESERVED", "CANCELLED", "saga_timeout"),
        ("CANCELLED", "CANCELLED", "payment refunded"),
    ]
    assert events.index("payment.succeeded") < events.index("payment.refunded")
    assert await saga.stock(sku) == 5


async def test_an_order_worth_nothing_is_confirmed_without_a_payment(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(price="0.00", stock=5)
    await saga.put_in_cart(customer, sku)

    order_id = (await saga.place(customer, sku, "1111", price="0.00")).json()["id"]
    order = await saga.wait_for_status(customer, order_id, "CONFIRMED")

    async def cart_is_empty() -> bool:
        return await saga.cart_skus(customer) == []

    await eventually(cart_is_empty, seconds=WAIT_SECONDS, interval=0.2)
    assert [(a, b) for a, b, _ in history_of(order)] == [
        (None, "PENDING"),
        ("PENDING", "STOCK_RESERVED"),
        ("STOCK_RESERVED", "CONFIRMED"),
    ]
    assert order["total"] == "0.00"
    assert await saga.stock(sku) == 3
    assert await saga.payment(customer, order_id) is None


async def test_an_order_for_more_than_the_stock_is_cancelled_and_nothing_moves(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=1)
    order_id = (await saga.place(customer, sku, "1111", quantity=2)).json()["id"]

    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    assert order["cancel_reason"] == "insufficient_stock"
    assert await saga.stock(sku) == 1
    assert await saga.payment(customer, order_id) is None


async def test_a_price_that_changed_since_the_customer_saw_it_cancels_the_order(
    saga: Saga,
) -> None:
    customer, sku = uuid4(), await saga.add_product(price="10.00", stock=5)
    order_id = (await saga.place(customer, sku, "1111", price="9.99")).json()["id"]

    order = await saga.wait_for_status(customer, order_id, "CANCELLED")

    assert order["cancel_reason"] == "price_changed"
    assert await saga.stock(sku) == 5


async def test_the_same_idempotency_key_buys_once(saga: Saga) -> None:
    customer, sku = uuid4(), await saga.add_product(stock=5)
    key = f"e2e-{uuid4().hex}"

    first = await saga.place(customer, sku, "1111", key=key)
    second = await saga.place(customer, sku, "1111", key=key)
    await saga.wait_for_status(customer, first.json()["id"], "CONFIRMED")

    assert second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    assert await saga.stock(sku) == 3


async def test_twenty_customers_fighting_for_the_last_unit_produce_one_confirmed_order(
    saga: Saga,
) -> None:
    sku = await saga.add_product(stock=1)
    customers = [uuid4() for _ in range(20)]

    placed = await asyncio.gather(
        *(saga.place(customer, sku, "1111", quantity=1) for customer in customers)
    )
    ids = [response.json()["id"] for response in placed]

    async def all_decided() -> bool:
        orders = [
            await saga.order(customer, order_id)
            for customer, order_id in zip(customers, ids, strict=True)
        ]
        return all(order["status"] in {"CONFIRMED", "CANCELLED"} for order in orders)

    await eventually(all_decided, seconds=WAIT_SECONDS, interval=0.3)
    orders = [
        await saga.order(customer, order_id)
        for customer, order_id in zip(customers, ids, strict=True)
    ]
    assert [order["status"] for order in orders].count("CONFIRMED") == 1
    assert {o["cancel_reason"] for o in orders if o["status"] == "CANCELLED"} == {
        "insufficient_stock"
    }
    assert await saga.stock(sku) == 0
