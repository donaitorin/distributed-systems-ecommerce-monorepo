import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from catalog_testing.reservations import (
    NOW,
    add_product,
    cancelled_event,
    created_event,
    line,
    outgoing,
    stock_and_version,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from catalog.application.reservations import StockReservations
from catalog.infra.database import create_session_factory
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.worker import build_orders_consumer
from ecommerce_contracts import (
    INSUFFICIENT_STOCK,
    ORDERS_TOPIC,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
)
from ecommerce_messaging import InMemoryBroker

pytestmark = pytest.mark.integration

CONCURRENT_ORDERS = 20


class Database:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions = create_session_factory(engine)
        self.reservations = StockReservations(self.factory, lambda: NOW)

    def factory(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessions)

    async def inventory_events(self) -> list[tuple[str, dict[str, Any]]]:
        async with self.sessions() as session:
            rows = await session.execute(
                text("SELECT payload FROM outbox WHERE topic = 'inventory.events' ORDER BY id")
            )
        parsed = [json.loads(raw) for (raw,) in rows.all()]
        return [(event["event_type"], event["payload"]) for event in parsed]

    async def count(self, query: str, **params: object) -> int:
        async with self.sessions() as session:
            return int(await session.scalar(text(query), params) or 0)


@pytest.fixture
async def database(
    empty_database_url: str, alembic_runner: Callable[[str, str, str], None]
) -> AsyncIterator[Database]:
    alembic_runner(empty_database_url, "upgrade", "head")
    engine = create_async_engine(empty_database_url, pool_size=CONCURRENT_ORDERS, max_overflow=0)
    yield Database(engine)
    await engine.dispose()


def events_of(
    events: list[tuple[str, dict[str, Any]]], order_id: UUID
) -> list[tuple[str, dict[str, Any]]]:
    return [item for item in events if item[1]["order_id"] == str(order_id)]


async def test_twenty_concurrent_orders_for_the_last_unit_sell_exactly_one(
    database: Database,
) -> None:
    sku = await add_product(database.factory, stock=1)
    order_ids = [uuid4() for _ in range(CONCURRENT_ORDERS)]

    await asyncio.gather(
        *(database.reservations.reserve(order_id, [line(sku)], uuid4()) for order_id in order_ids)
    )

    events = await database.inventory_events()
    assert [name for name, _ in events].count(STOCK_RESERVED) == 1
    failures = [payload for name, payload in events if name == STOCK_RESERVATION_FAILED]
    assert len(failures) == CONCURRENT_ORDERS - 1
    assert {item["reason"] for item in failures} == {INSUFFICIENT_STOCK}
    assert await stock_and_version(database.factory, sku) == (0, 2)
    assert await database.count("SELECT count(*) FROM stock_reservations") == CONCURRENT_ORDERS
    assert await database.count("SELECT count(*) FROM stock_reservation_lines") == 1


async def test_concurrent_orders_never_take_more_than_the_stock_and_the_rest_are_refused(
    database: Database,
) -> None:
    sku = await add_product(database.factory, stock=7)

    await asyncio.gather(
        *(
            database.reservations.reserve(uuid4(), [line(sku, 2)], uuid4())
            for _ in range(CONCURRENT_ORDERS)
        )
    )

    events = [name for name, _ in await database.inventory_events()]
    assert events.count(STOCK_RESERVED) == 3
    assert (await stock_and_version(database.factory, sku))[0] == 1


async def test_orders_listing_the_same_products_in_opposite_order_never_deadlock(
    database: Database,
) -> None:
    first = await add_product(database.factory, stock=100, sku="AAA-" + uuid4().hex[:8].upper())
    second = await add_product(database.factory, stock=100, sku="ZZZ-" + uuid4().hex[:8].upper())

    async with asyncio.timeout(30):
        await asyncio.gather(
            *(
                database.reservations.reserve(
                    uuid4(),
                    [line(first), line(second)] if index % 2 else [line(second), line(first)],
                    uuid4(),
                )
                for index in range(CONCURRENT_ORDERS)
            )
        )

    assert (await stock_and_version(database.factory, first))[0] == 100 - CONCURRENT_ORDERS
    assert (await stock_and_version(database.factory, second))[0] == 100 - CONCURRENT_ORDERS


async def test_concurrent_multi_product_orders_are_all_or_nothing(database: Database) -> None:
    plenty = await add_product(database.factory, stock=100)
    scarce = await add_product(database.factory, stock=3)

    await asyncio.gather(
        *(
            database.reservations.reserve(uuid4(), [line(plenty), line(scarce)], uuid4())
            for _ in range(CONCURRENT_ORDERS)
        )
    )

    sold = [name for name, _ in await database.inventory_events()].count(STOCK_RESERVED)
    assert sold == 3
    assert (await stock_and_version(database.factory, scarce))[0] == 0
    assert (await stock_and_version(database.factory, plenty))[0] == 100 - sold


async def test_the_same_order_delivered_concurrently_reserves_once(database: Database) -> None:
    sku = await add_product(database.factory, stock=10)
    order_id = uuid4()

    await asyncio.gather(
        *(
            database.reservations.reserve(order_id, [line(sku, 2)], uuid4())
            for _ in range(CONCURRENT_ORDERS)
        )
    )

    assert (await stock_and_version(database.factory, sku))[0] == 8
    assert [name for name, _ in await database.inventory_events()] == [STOCK_RESERVED]


async def test_a_release_racing_its_reservation_ends_with_the_stock_back(
    database: Database,
) -> None:
    sku = await add_product(database.factory, stock=5)
    order_ids = [uuid4() for _ in range(CONCURRENT_ORDERS)]

    await asyncio.gather(
        *(
            task
            for order_id in order_ids
            for task in (
                database.reservations.reserve(order_id, [line(sku)], uuid4()),
                database.reservations.release(order_id, uuid4()),
            )
        )
    )
    await asyncio.gather(
        *(database.reservations.release(order_id, uuid4()) for order_id in order_ids)
    )

    assert (await stock_and_version(database.factory, sku))[0] == 5


async def test_order_cancelled_delivered_before_order_created_never_moves_stock(
    database: Database,
) -> None:
    sku = await add_product(database.factory, stock=5)
    order_id = uuid4()
    broker = InMemoryBroker()
    source = broker.source([ORDERS_TOPIC])
    consumer = build_orders_consumer(database.reservations, source, broker)
    await broker.publish(outgoing(cancelled_event(order_id)))
    await broker.publish(outgoing(created_event(order_id, line(sku, 2))))

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert await stock_and_version(database.factory, sku) == (5, 1)
    assert await database.inventory_events() == []
    assert (
        await database.count(
            "SELECT count(*) FROM stock_reservations WHERE order_id = :id AND status = 'RELEASED'",
            id=order_id,
        )
        == 1
    )
    assert await database.count("SELECT count(*) FROM stock_reservation_lines") == 0

    later = created_event(order_id, line(sku, 2))
    await broker.publish(outgoing(later))
    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)
    assert await stock_and_version(database.factory, sku) == (5, 1)


async def test_the_full_cycle_through_the_consumer_reserves_then_releases(
    database: Database,
) -> None:
    sku = await add_product(database.factory, stock=5)
    order_id = uuid4()
    broker = InMemoryBroker()
    source = broker.source([ORDERS_TOPIC])
    consumer = build_orders_consumer(database.reservations, source, broker)
    for envelope in (
        created_event(order_id, line(sku, 2)),
        cancelled_event(order_id),
        cancelled_event(order_id),
    ):
        await broker.publish(outgoing(envelope))

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert await stock_and_version(database.factory, sku) == (5, 3)
    names = [name for name, _ in events_of(await database.inventory_events(), order_id)]
    assert names == [STOCK_RESERVED, "stock.released"]


async def test_the_database_itself_refuses_negative_stock(database: Database) -> None:
    sku = await add_product(database.factory, stock=1)

    with pytest.raises(Exception, match="ck_products_stock_non_negative"):
        async with database.sessions() as session:
            await session.execute(
                text("UPDATE products SET stock = stock - 2 WHERE sku = :sku"), {"sku": sku}
            )
