import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from payments_testing.data import RecordingProvider, SteppingClock, payment_requested
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from ecommerce_contracts import PAYMENT_REFUNDED, PAYMENT_SUCCEEDED
from payments.application.processor import PaymentProcessor
from payments.domain.payment import PaymentStatus
from payments.infra.database import create_session_factory
from payments.infra.simulated import SimulatedPaymentProvider
from payments.infra.unit_of_work import SqlAlchemyUnitOfWork

pytestmark = pytest.mark.integration

CONCURRENCY = 20
DELAY = timedelta(seconds=90)


class Stack:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.clock = SteppingClock()
        self.sessions: async_sessionmaker[Any] = create_session_factory(engine)
        self.provider = RecordingProvider(SimulatedPaymentProvider(DELAY, self.clock))
        self.processor = PaymentProcessor(self.unit_of_work, self.provider, self.clock)

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessions)

    async def rows(self, query: str, **params: object) -> list[Any]:
        async with self.sessions() as session:
            return list((await session.execute(text(query), params)).all())

    async def events(self, order_id: UUID) -> list[str]:
        rows = await self.rows(
            "SELECT payload FROM outbox WHERE key = :key ORDER BY id", key=str(order_id)
        )
        return [json.loads(raw)["event_type"] for (raw,) in rows]

    async def status(self, order_id: UUID) -> str:
        rows = await self.rows("SELECT status FROM payments WHERE order_id = :id", id=order_id)
        return str(rows[0][0])

    async def request(self, card: str) -> UUID:
        envelope = payment_requested(card_last4=card)
        await self.processor.charge_requested(envelope.payload, envelope.correlation_id)
        return envelope.payload.order_id


@pytest.fixture
async def stack(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> AsyncIterator[Stack]:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_async_engine(empty_database_url, pool_size=40, max_overflow=0)
    yield Stack(engine)
    await engine.dispose()


async def test_the_same_request_delivered_concurrently_creates_one_payment_and_one_event(
    stack: Stack,
) -> None:
    envelope = payment_requested(card_last4="1111")

    await asyncio.gather(
        *(
            stack.processor.charge_requested(envelope.payload, envelope.correlation_id)
            for _ in range(CONCURRENCY)
        )
    )

    order_id = envelope.payload.order_id
    assert len(await stack.rows("SELECT 1 FROM payments")) == 1
    assert await stack.events(order_id) == [PAYMENT_SUCCEEDED]
    assert {call.idempotency_key for call in stack.provider.charges} == {str(order_id)}


async def test_concurrent_cancellations_of_a_paid_order_refund_it_once(stack: Stack) -> None:
    order_id = await stack.request("1111")

    await asyncio.gather(*(stack.processor.order_cancelled(order_id) for _ in range(CONCURRENCY)))

    assert await stack.status(order_id) == PaymentStatus.REFUNDED
    assert await stack.events(order_id) == [PAYMENT_SUCCEEDED, PAYMENT_REFUNDED]
    assert {call.idempotency_key for call in stack.provider.refunds} == {f"refund-{order_id}"}


async def test_a_cancellation_racing_the_late_approval_always_ends_refunded_exactly_once(
    stack: Stack,
) -> None:
    order_ids = [await stack.request("2222") for _ in range(CONCURRENCY)]
    stack.clock.advance(seconds=91)

    await asyncio.gather(
        stack.processor.settle_due(),
        *(stack.processor.order_cancelled(order_id) for order_id in order_ids),
    )
    while await stack.processor.refund_due():
        pass

    for order_id in order_ids:
        assert await stack.status(order_id) == PaymentStatus.REFUNDED
        events = await stack.events(order_id)
        assert events.count(PAYMENT_SUCCEEDED) == 1
        assert events.count(PAYMENT_REFUNDED) == 1
        assert events.index(PAYMENT_SUCCEEDED) < events.index(PAYMENT_REFUNDED)


async def test_the_late_approval_without_a_cancellation_just_succeeds(stack: Stack) -> None:
    order_id = await stack.request("2222")
    stack.clock.advance(seconds=91)

    await asyncio.gather(*(stack.processor.settle_due() for _ in range(5)))

    assert await stack.status(order_id) == PaymentStatus.SUCCEEDED
    assert await stack.events(order_id) == [PAYMENT_SUCCEEDED]


async def test_a_payment_declined_or_never_answered_is_not_refunded_when_the_order_is_cancelled(
    stack: Stack,
) -> None:
    declined, silent = await stack.request("0000"), await stack.request("9999")

    await asyncio.gather(
        stack.processor.order_cancelled(declined), stack.processor.order_cancelled(silent)
    )

    assert await stack.status(declined) == PaymentStatus.FAILED
    assert await stack.status(silent) == PaymentStatus.PENDING
    assert stack.provider.refunds == []
