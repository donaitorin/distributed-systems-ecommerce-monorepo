import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from orders_testing.data import SteppingClock, order_body, order_request
from orders_testing.events import (
    outgoing,
    payment_refunded,
    payment_succeeded,
    reservation_failed,
    stock_reserved,
)
from orders_testing.support import bearer, http_client, orders_settings
from orders_testing.waiting import eventually
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ecommerce_auth.testing import StubTokenIssuer, build_stub_verifier
from ecommerce_contracts import ORDER_CANCELLED, ORDER_CONFIRMED, ORDER_CREATED
from ecommerce_messaging import InMemoryBroker
from orders.application.orders import OrderService
from orders.application.saga import OrderSaga, SagaTimeouts
from orders.infra.database import create_session_factory
from orders.infra.unit_of_work import SqlAlchemyUnitOfWork
from orders.main import create_orders_app
from orders.worker import SAGA_TOPICS, build_consumer

pytestmark = pytest.mark.integration

CONCURRENCY = 20
ORDERS = "/api/v1/orders"
LINES = [("RS-001", "Rust in Action", 2, "39.90"), ("XS-001", "Sticker Pack", 1, "12.50")]
TIMEOUT = timedelta(seconds=60)


class Stack:
    def __init__(self, engine: AsyncEngine, issuer: StubTokenIssuer, clock: SteppingClock) -> None:
        self.engine = engine
        self.clock = clock
        self.sessions: async_sessionmaker[Any] = create_session_factory(engine)
        self.issuer = issuer
        self.service = OrderService(self.unit_of_work, clock)
        self.saga = OrderSaga(self.unit_of_work, clock)
        self.timeouts = SagaTimeouts(self.unit_of_work, TIMEOUT, clock, batch_size=5)
        app = create_orders_app(orders_settings(), engine, clock=clock)
        app.state.token_verifier = build_stub_verifier(issuer)
        self.app = app

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessions)

    async def rows(self, query: str, **params: object) -> list[Any]:
        async with self.sessions() as session:
            return list((await session.execute(text(query), params)).all())

    async def count(self, query: str, **params: object) -> int:
        rows = await self.rows(query, **params)
        return int(rows[0][0])

    async def outbox_types(self, order_id: UUID) -> list[str]:
        rows = await self.rows(
            "SELECT payload FROM outbox WHERE key = :key ORDER BY id", key=str(order_id)
        )
        return [json.loads(raw)["event_type"] for (raw,) in rows]

    async def history(self, order_id: UUID) -> list[tuple[str | None, str, str | None]]:
        rows = await self.rows(
            "SELECT from_status, to_status, reason FROM order_status_history"
            " WHERE order_id = :id ORDER BY id",
            id=order_id,
        )
        return [(a, b, c) for a, b, c in rows]

    async def status(self, order_id: UUID) -> str:
        return str((await self.rows("SELECT status FROM orders WHERE id = :id", id=order_id))[0][0])

    async def place(
        self, customer: UUID, key: str, lines: list[tuple[str, int, str]] | None = None
    ) -> UUID:
        placed = await self.service.place(customer, key, order_request(lines), uuid4())
        return placed.order_id

    async def deliver(self, *envelopes: Any) -> None:
        broker = InMemoryBroker()
        source = broker.source(SAGA_TOPICS)
        consumer = build_consumer(self.saga, source, broker)
        for envelope in envelopes:
            await broker.publish(outgoing(envelope))
        while (message := await source.poll(0)) is not None:
            await consumer.handle(message)


@pytest.fixture
async def stack(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> AsyncIterator[Stack]:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_async_engine(empty_database_url, pool_size=30, max_overflow=0)
    yield Stack(engine, StubTokenIssuer(), SteppingClock())
    await engine.dispose()


def post(client: httpx.AsyncClient, headers: dict[str, str], body: dict[str, Any], key: str) -> Any:
    return client.post(ORDERS, json=body, headers=headers | {"Idempotency-Key": key})


async def test_concurrent_posts_with_the_same_key_and_body_create_one_order(stack: Stack) -> None:
    headers = bearer(stack.issuer, uuid4())
    async with http_client(stack.app) as client:
        responses = await asyncio.gather(
            *(post(client, headers, order_body(), "checkout-same-0001") for _ in range(CONCURRENCY))
        )

    assert {response.status_code for response in responses} == {202}
    assert len({response.json()["id"] for response in responses}) == 1
    replays = [r for r in responses if r.headers.get("idempotent-replay") == "true"]
    assert len(replays) == CONCURRENCY - 1
    assert await stack.count("SELECT count(*) FROM orders") == 1
    assert await stack.count("SELECT count(*) FROM outbox") == 1
    assert await stack.count("SELECT count(*) FROM order_status_history") == 1
    assert await stack.count("SELECT count(*) FROM idempotency_keys") == 1


async def test_concurrent_posts_with_the_same_key_and_different_bodies_create_one_order(
    stack: Stack,
) -> None:
    headers = bearer(stack.issuer, uuid4())
    bodies = [
        order_body(),
        order_body(lines=[{"sku": "RS-001", "quantity": 5, "unit_price": "39.90"}]),
    ]
    async with http_client(stack.app) as client:
        responses = await asyncio.gather(
            *(
                post(client, headers, bodies[index % 2], "checkout-race-0001")
                for index in range(CONCURRENCY)
            )
        )

    winners = [r for r in responses if r.status_code == 202]
    losers = [r for r in responses if r.status_code == 422]
    assert len(winners) + len(losers) == CONCURRENCY
    assert len({r.json()["id"] for r in winners}) == 1
    assert {r.json()["code"] for r in losers} == {"idempotency_key_reused"}
    assert await stack.count("SELECT count(*) FROM orders") == 1


async def test_concurrent_posts_with_different_keys_create_one_order_each(stack: Stack) -> None:
    headers = bearer(stack.issuer, uuid4())
    async with http_client(stack.app) as client:
        responses = await asyncio.gather(
            *(
                post(client, headers, order_body(), f"checkout-many-{index:04d}")
                for index in range(CONCURRENCY)
            )
        )

    assert len({response.json()["id"] for response in responses}) == CONCURRENCY
    assert await stack.count("SELECT count(*) FROM orders") == CONCURRENCY


async def test_a_key_is_usable_again_after_twenty_four_hours(stack: Stack) -> None:
    customer = uuid4()
    first = await stack.service.place(customer, "checkout-ttl-0001", order_request(), uuid4())
    stack.clock.advance(seconds=24 * 3600)

    later = await stack.service.place(
        customer, "checkout-ttl-0001", order_request([("RS-001", 9, "39.90")]), uuid4()
    )

    assert later.order_id != first.order_id
    assert await stack.count("SELECT count(*) FROM orders") == 2
    assert await stack.count("SELECT count(*) FROM idempotency_keys") == 1


async def test_the_card_number_never_reaches_the_database_the_outbox_or_the_logs(
    stack: Stack, caplog: pytest.LogCaptureFixture
) -> None:
    number = "4929 1234 5678 1111"
    digits = "4929123456781111"
    headers = bearer(stack.issuer, uuid4())
    caplog.set_level(logging.DEBUG)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.DEBUG)
    body = order_body(payment={"card_number": number})
    try:
        async with http_client(stack.app) as client:
            accepted = await post(client, headers, body, "checkout-pan-0001")
            replay = await post(client, headers, body, "checkout-pan-0001")
            rejected = await post(
                client,
                headers,
                order_body(payment={"card_number": number}, lines=[]),
                "checkout-pan-0002",
            )
            await client.get(f"{ORDERS}/{accepted.json()['id']}", headers=headers)
        order_id = UUID(accepted.json()["id"])
        await stack.saga.stock_reserved(order_id, {"RS-001": "Rust in Action"})
        await stack.timeouts.sweep()
    finally:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.NOTSET)

    dumped = ""
    for table in ("orders", "order_lines", "order_status_history", "idempotency_keys", "outbox"):
        for (row,) in await stack.rows(f"SELECT t::text FROM {table} t"):
            dumped += row
    responses = accepted.text + replay.text + rejected.text
    assert accepted.status_code == replay.status_code == 202
    assert rejected.status_code == 422
    assert dumped
    assert "INSERT INTO orders" in caplog.text
    for needle in (number, digits, "4929", "1234 5678", "12345678"):
        assert needle not in dumped
        assert needle not in responses
        assert needle not in caplog.text
    assert (await stack.rows("SELECT card_last4 FROM orders"))[0][0] == "1111"
    payment_requests = [
        json.loads(raw)
        for (raw,) in await stack.rows(
            "SELECT payload FROM outbox WHERE payload LIKE '%order.payment_requested%'"
        )
    ]
    assert [item["payload"]["card_last4"] for item in payment_requests] == ["1111"]


async def test_the_saga_runs_end_to_end_on_postgres_and_replays_change_nothing(
    stack: Stack,
) -> None:
    order_id = await stack.place(uuid4(), "checkout-saga-0001")
    reserved, paid = stock_reserved(order_id, LINES), payment_succeeded(order_id)

    await stack.deliver(reserved, reserved, paid, paid, reserved, paid)

    assert await stack.status(order_id) == "CONFIRMED"
    assert [(a, b) for a, b, _ in await stack.history(order_id)] == [
        (None, "PENDING"),
        ("PENDING", "STOCK_RESERVED"),
        ("STOCK_RESERVED", "PAID"),
        ("PAID", "CONFIRMED"),
    ]
    assert await stack.outbox_types(order_id) == [
        ORDER_CREATED,
        "order.payment_requested",
        ORDER_CONFIRMED,
    ]
    names = await stack.rows(
        "SELECT name FROM order_lines WHERE order_id = :id ORDER BY position", id=order_id
    )
    assert [name for (name,) in names] == ["Rust in Action", "Sticker Pack"]


async def test_a_reservation_failure_cancels_once_even_when_delivered_repeatedly(
    stack: Stack,
) -> None:
    order_id = await stack.place(uuid4(), "checkout-fail-0001")
    failure = reservation_failed(order_id, "insufficient_stock")

    await asyncio.gather(*(stack.deliver(failure) for _ in range(10)))

    assert await stack.status(order_id) == "CANCELLED"
    assert await stack.outbox_types(order_id) == [ORDER_CREATED, ORDER_CANCELLED]
    assert len(await stack.history(order_id)) == 2


async def test_a_late_payment_changes_nothing_and_the_refund_is_recorded_once(
    stack: Stack,
) -> None:
    order_id = await stack.place(uuid4(), "checkout-late-0001")
    await stack.deliver(stock_reserved(order_id, LINES))
    stack.clock.advance(seconds=61)
    await stack.timeouts.sweep()

    await stack.deliver(payment_succeeded(order_id))
    refund = payment_refunded(order_id)
    await stack.deliver(refund, refund)

    assert await stack.status(order_id) == "CANCELLED"
    history = await stack.history(order_id)
    assert history[-2:] == [
        ("STOCK_RESERVED", "CANCELLED", "saga_timeout"),
        ("CANCELLED", "CANCELLED", "payment refunded"),
    ]
    assert await stack.outbox_types(order_id) == [
        ORDER_CREATED,
        "order.payment_requested",
        ORDER_CANCELLED,
    ]


async def test_sweepers_running_together_cancel_every_stuck_order_exactly_once(
    stack: Stack,
) -> None:
    customer = uuid4()
    order_ids = [await stack.place(customer, f"checkout-sweep-{i:04d}") for i in range(40)]
    stack.clock.advance(seconds=3600)
    first = SagaTimeouts(stack.unit_of_work, TIMEOUT, stack.clock, batch_size=5)
    second = SagaTimeouts(stack.unit_of_work, TIMEOUT, stack.clock, batch_size=5)
    stop = asyncio.Event()

    runners = [
        asyncio.create_task(first.run(stop, 0.01)),
        asyncio.create_task(second.run(stop, 0.01)),
    ]
    await eventually(
        lambda: _all_cancelled(stack, order_ids),
    )
    stop.set()
    await asyncio.gather(*runners)

    assert await stack.count("SELECT count(*) FROM orders WHERE status = 'CANCELLED'") == 40
    assert (
        await stack.count("SELECT count(*) FROM outbox WHERE payload LIKE '%order.cancelled%'")
        == 40
    )
    assert (
        await stack.count("SELECT count(*) FROM order_status_history WHERE to_status = 'CANCELLED'")
        == 40
    )


async def _all_cancelled(stack: Stack, order_ids: list[UUID]) -> bool:
    return await stack.count("SELECT count(*) FROM orders WHERE status = 'CANCELLED'") == len(
        order_ids
    )


async def test_a_sweeper_skips_rows_another_sweeper_is_holding(stack: Stack) -> None:
    customer = uuid4()
    order_ids = [await stack.place(customer, f"checkout-skip-{i:04d}") for i in range(6)]
    stack.clock.advance(seconds=3600)
    cutoff = stack.clock.now - TIMEOUT

    async with stack.unit_of_work() as holder:
        held = await holder.orders.lock_expired(cutoff, 3)
        other = SagaTimeouts(stack.unit_of_work, TIMEOUT, stack.clock, batch_size=10)
        async with asyncio.timeout(10):
            swept = await other.sweep()

    assert len(held) == 3
    assert swept == 3
    cancelled = {
        row[0] for row in await stack.rows("SELECT id FROM orders WHERE status = 'CANCELLED'")
    }
    assert cancelled == set(order_ids) - set(held)


async def test_a_payment_racing_the_timeout_leaves_one_consistent_outcome(stack: Stack) -> None:
    customer = uuid4()
    order_ids = []
    for index in range(CONCURRENCY):
        order_id = await stack.place(customer, f"checkout-race-{index:04d}")
        await stack.deliver(stock_reserved(order_id, LINES))
        order_ids.append(order_id)
    stack.clock.advance(seconds=3600)

    await asyncio.gather(
        _drain(stack),
        *(stack.deliver(payment_succeeded(order_id)) for order_id in order_ids),
    )

    for order_id in order_ids:
        status = await stack.status(order_id)
        events = await stack.outbox_types(order_id)
        assert status in {"CONFIRMED", "CANCELLED"}
        terminal = [name for name in events if name in {ORDER_CONFIRMED, ORDER_CANCELLED}]
        assert terminal == [ORDER_CONFIRMED if status == "CONFIRMED" else ORDER_CANCELLED]


async def _drain(stack: Stack) -> None:
    while await stack.timeouts.sweep():
        pass
