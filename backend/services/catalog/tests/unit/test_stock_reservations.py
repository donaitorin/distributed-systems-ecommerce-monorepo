from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from catalog_testing.reservations import NOW, add_product, line, retire, stock_and_version
from catalog_testing.support import seeded_store

from catalog.application.reservations import StockReservations
from catalog.infra.memory import InMemoryStore, InMemoryUnitOfWork
from catalog.infra.memory_imports import OutboxEntry
from ecommerce_contracts import (
    CATALOG_TOPIC,
    INSUFFICIENT_STOCK,
    INVENTORY_TOPIC,
    PRICE_CHANGED,
    PRODUCT_DELETED,
    PRODUCT_UNAVAILABLE,
    PRODUCT_UPDATED,
    STOCK_RELEASED,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    ProductUpdatedV1,
    StockReleasedV1,
    StockReservationFailedV1,
    StockReservedV1,
)

CORRELATION = UUID(int=99)


@pytest.fixture
def store() -> InMemoryStore:
    return seeded_store()


@pytest.fixture
def reservations(store: InMemoryStore) -> StockReservations:
    return StockReservations(lambda: InMemoryUnitOfWork(store), lambda: NOW)


def factory(store: InMemoryStore):  # type: ignore[no-untyped-def]
    return lambda: InMemoryUnitOfWork(store)


def events(store: InMemoryStore, topic: str) -> list[OutboxEntry]:
    return [entry for entry in store.import_data.outbox if entry.topic == topic]


async def test_a_reservation_takes_the_stock_bumps_the_version_and_replies_with_authoritative_data(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), price="12.50", stock=5)
    order_id = uuid4()

    await reservations.reserve(order_id, [line(sku, 2, "12.5")], CORRELATION)

    assert await stock_and_version(factory(store), sku) == (3, 2)
    [reply] = events(store, INVENTORY_TOPIC)
    assert (reply.event_type, reply.key, reply.correlation_id) == (
        STOCK_RESERVED,
        str(order_id),
        CORRELATION,
    )
    assert isinstance(reply.payload, StockReservedV1)
    [reserved] = reply.payload.lines
    assert (reserved.sku, reserved.name, reserved.quantity, reserved.unit_price) == (
        sku,
        "Widget",
        2,
        Decimal("12.50"),
    )


async def test_every_reserved_sku_emits_product_updated_with_the_new_stock_and_version(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    first = await add_product(factory(store), stock=5)
    second = await add_product(factory(store), stock=2)

    await reservations.reserve(uuid4(), [line(second), line(first, 3)], CORRELATION)

    updates = [
        entry.payload
        for entry in events(store, CATALOG_TOPIC)
        if entry.event_type == PRODUCT_UPDATED
    ][-2:]
    assert all(isinstance(item, ProductUpdatedV1) for item in updates)
    by_sku = {item.sku: (item.stock, item.version) for item in updates}  # type: ignore[attr-defined]
    assert by_sku == {first: (2, 2), second: (1, 2)}


async def test_the_reply_lists_lines_in_sku_order(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    low = await add_product(factory(store), sku="AAA-1")
    high = await add_product(factory(store), sku="ZZZ-1")

    await reservations.reserve(uuid4(), [line(high), line(low)], CORRELATION)

    [reply] = events(store, INVENTORY_TOPIC)
    assert isinstance(reply.payload, StockReservedV1)
    assert [item.sku for item in reply.payload.lines] == [low, high]


async def test_one_short_line_rejects_the_whole_order_and_leaves_every_stock_alone(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    plenty = await add_product(factory(store), stock=10)
    scarce = await add_product(factory(store), stock=1)

    await reservations.reserve(uuid4(), [line(plenty, 4), line(scarce, 2)], CORRELATION)

    assert await stock_and_version(factory(store), plenty) == (10, 1)
    assert await stock_and_version(factory(store), scarce) == (1, 1)
    [reply] = events(store, INVENTORY_TOPIC)
    assert reply.event_type == STOCK_RESERVATION_FAILED
    assert isinstance(reply.payload, StockReservationFailedV1)
    assert (reply.payload.reason, reply.payload.sku, reply.payload.available) == (
        INSUFFICIENT_STOCK,
        scarce,
        1,
    )
    assert events(store, CATALOG_TOPIC) == []


async def test_a_failed_reservation_emits_no_product_event(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=1)
    before = len(events(store, CATALOG_TOPIC))

    await reservations.reserve(uuid4(), [line(sku, 2)], CORRELATION)

    assert len(events(store, CATALOG_TOPIC)) == before


async def test_a_price_different_from_the_one_the_customer_saw_is_refused_with_the_current_price(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), price="10.00")

    await reservations.reserve(uuid4(), [line(sku, 1, "9.99")], CORRELATION)

    [reply] = events(store, INVENTORY_TOPIC)
    assert isinstance(reply.payload, StockReservationFailedV1)
    assert (reply.payload.reason, reply.payload.current_price) == (PRICE_CHANGED, Decimal("10.00"))
    assert await stock_and_version(factory(store), sku) == (5, 1)


async def test_the_price_is_compared_quantized_to_two_places(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), price="10.50")

    await reservations.reserve(uuid4(), [line(sku, 1, "10.5")], CORRELATION)

    [reply] = events(store, INVENTORY_TOPIC)
    assert reply.event_type == STOCK_RESERVED


@pytest.mark.parametrize("retired", [False, True])
async def test_an_unknown_or_retired_product_is_unavailable(
    store: InMemoryStore, reservations: StockReservations, retired: bool
) -> None:
    sku = await add_product(factory(store))
    if retired:
        await retire(factory(store), sku)
    else:
        sku = "NOPE-1"

    await reservations.reserve(uuid4(), [line(sku)], CORRELATION)

    [reply] = events(store, INVENTORY_TOPIC)
    assert isinstance(reply.payload, StockReservationFailedV1)
    assert (reply.payload.reason, reply.payload.sku) == (PRODUCT_UNAVAILABLE, sku)


async def test_replaying_the_same_order_changes_nothing_and_emits_nothing_more(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=5)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)
    emitted = len(store.import_data.outbox)

    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)

    assert await stock_and_version(factory(store), sku) == (3, 2)
    assert len(store.import_data.outbox) == emitted


async def test_a_failed_order_replayed_after_a_restock_is_still_refused(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=1)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)
    async with InMemoryUnitOfWork(store) as uow:
        store.products[sku].stock = 50
        await uow.commit()

    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)

    assert store.products[sku].stock == 50
    assert [entry.event_type for entry in events(store, INVENTORY_TOPIC)] == [
        STOCK_RESERVATION_FAILED
    ]


async def test_releasing_gives_the_stock_back_and_announces_it(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    first = await add_product(factory(store), stock=5)
    second = await add_product(factory(store), stock=5)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(first, 2), line(second, 1)], CORRELATION)

    await reservations.release(order_id, CORRELATION)

    assert await stock_and_version(factory(store), first) == (5, 3)
    assert await stock_and_version(factory(store), second) == (5, 3)
    released = events(store, INVENTORY_TOPIC)[-1]
    assert released.event_type == STOCK_RELEASED
    assert isinstance(released.payload, StockReleasedV1)
    assert {(item.sku, item.quantity) for item in released.payload.lines} == {
        (first, 2),
        (second, 1),
    }
    latest = {
        entry.payload.sku: entry.payload
        for entry in events(store, CATALOG_TOPIC)
        if isinstance(entry.payload, ProductUpdatedV1)
    }
    assert (latest[first].stock, latest[first].version) == (5, 3)


async def test_releasing_twice_gives_the_stock_back_once(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=5)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)
    await reservations.release(order_id, CORRELATION)
    emitted = len(store.import_data.outbox)

    await reservations.release(order_id, CORRELATION)

    assert await stock_and_version(factory(store), sku) == (5, 3)
    assert len(store.import_data.outbox) == emitted


async def test_releasing_a_failed_reservation_moves_no_stock(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=1)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)
    emitted = len(store.import_data.outbox)

    await reservations.release(order_id, CORRELATION)

    assert await stock_and_version(factory(store), sku) == (1, 1)
    assert len(store.import_data.outbox) == emitted


async def test_a_release_that_arrives_first_leaves_a_tombstone_that_refuses_the_later_reserve(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=5)
    order_id = uuid4()

    await reservations.release(order_id, CORRELATION)
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)

    assert await stock_and_version(factory(store), sku) == (5, 1)
    assert events(store, INVENTORY_TOPIC) == []


async def test_releasing_a_retired_product_restores_stock_and_announces_the_deletion(
    store: InMemoryStore, reservations: StockReservations
) -> None:
    sku = await add_product(factory(store), stock=5)
    order_id = uuid4()
    await reservations.reserve(order_id, [line(sku, 2)], CORRELATION)
    async with InMemoryUnitOfWork(store) as uow:
        await uow.products.soft_delete(sku, NOW)
        await uow.commit()

    await reservations.release(order_id, CORRELATION)

    assert store.products[sku].stock == 5
    last = events(store, CATALOG_TOPIC)[-1]
    assert last.event_type == PRODUCT_DELETED
    assert last.payload.version == store.products[sku].version  # type: ignore[attr-defined]


async def test_a_reservation_that_cannot_complete_is_rolled_back_with_its_unit_of_work(
    store: InMemoryStore,
) -> None:
    sku = await add_product(factory(store), stock=5)
    order_id = uuid4()

    async with InMemoryUnitOfWork(store) as uow:
        await uow.reservations.reserve(order_id, (line(sku, 2),), NOW)

    assert await stock_and_version(factory(store), sku) == (5, 1)
    assert order_id not in store.reservations
