from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from catalog_testing.reservations import NOW, add_product, line, restock, retire, stock_and_version

from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.reservation import (
    AlreadyHandled,
    FailureReason,
    Rejected,
    ReleasedItem,
    ReservationLine,
    Reserved,
    ReserveResult,
)


async def reserve(
    factory: UnitOfWorkFactory, order_id: UUID, *lines: ReservationLine
) -> ReserveResult:
    async with factory() as uow:
        result = await uow.reservations.reserve(order_id, tuple(lines), NOW)
        await uow.commit()
    return result


async def release(factory: UnitOfWorkFactory, order_id: UUID) -> tuple[ReleasedItem, ...]:
    async with factory() as uow:
        items = await uow.reservations.release(order_id, NOW)
        await uow.commit()
    return items


async def test_a_reservation_returns_the_authoritative_product_after_the_decrement(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, price="12.50", stock=5)

    result = await reserve(unit_of_work, uuid4(), line(sku, 2, "12.50"))

    assert isinstance(result, Reserved)
    [item] = result.items
    assert (item.quantity, item.product.stock, item.product.version) == (2, 3, 2)
    assert (item.product.name, item.product.price) == ("Widget", Decimal("12.50"))
    assert await stock_and_version(unit_of_work, sku) == (3, 2)


async def test_a_rejected_line_rolls_back_the_lines_already_taken(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    first = await add_product(unit_of_work, stock=10, sku="A" + uuid4().hex[:10].upper())
    second = await add_product(unit_of_work, stock=1, sku="B" + uuid4().hex[:10].upper())

    result = await reserve(unit_of_work, uuid4(), line(first, 4), line(second, 2))

    assert isinstance(result, Rejected)
    assert result.failure.reason is FailureReason.INSUFFICIENT_STOCK
    assert (result.failure.sku, result.failure.available) == (second, 1)
    assert await stock_and_version(unit_of_work, first) == (10, 1)
    assert await stock_and_version(unit_of_work, second) == (1, 1)


async def test_a_different_price_is_refused_with_the_current_one(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, price="10.00")

    result = await reserve(unit_of_work, uuid4(), line(sku, 1, "9.99"))

    assert isinstance(result, Rejected)
    assert result.failure.reason is FailureReason.PRICE_CHANGED
    assert result.failure.current_price == Decimal("10.00")


@pytest.mark.parametrize("retired", [False, True])
async def test_unknown_and_retired_products_are_unavailable(
    unit_of_work: UnitOfWorkFactory, retired: bool
) -> None:
    sku = await add_product(unit_of_work)
    if retired:
        await retire(unit_of_work, sku)
    else:
        sku = "MISSING-" + uuid4().hex[:6].upper()

    result = await reserve(unit_of_work, uuid4(), line(sku))

    assert isinstance(result, Rejected)
    assert result.failure.reason is FailureReason.PRODUCT_UNAVAILABLE


async def test_the_same_order_is_never_reserved_twice(unit_of_work: UnitOfWorkFactory) -> None:
    sku = await add_product(unit_of_work, stock=5)
    order_id = uuid4()
    await reserve(unit_of_work, order_id, line(sku, 2))

    again = await reserve(unit_of_work, order_id, line(sku, 2))

    assert isinstance(again, AlreadyHandled)
    assert await stock_and_version(unit_of_work, sku) == (3, 2)


async def test_a_rejected_order_stays_rejected_after_a_restock(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, stock=1)
    order_id = uuid4()
    await reserve(unit_of_work, order_id, line(sku, 2))
    await restock(unit_of_work, sku, 50)

    again = await reserve(unit_of_work, order_id, line(sku, 2))

    assert isinstance(again, AlreadyHandled)
    assert (await stock_and_version(unit_of_work, sku))[0] == 50


async def test_a_release_returns_exactly_what_was_taken_and_only_once(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, stock=5)
    order_id = uuid4()
    await reserve(unit_of_work, order_id, line(sku, 3))

    first = await release(unit_of_work, order_id)
    second = await release(unit_of_work, order_id)

    [item] = first
    assert (item.quantity, item.product.stock, item.retired) == (3, 5, False)
    assert second == ()
    assert await stock_and_version(unit_of_work, sku) == (5, 3)


async def test_a_release_before_the_reservation_blocks_the_reservation(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, stock=5)
    order_id = uuid4()

    assert await release(unit_of_work, order_id) == ()
    result = await reserve(unit_of_work, order_id, line(sku, 2))

    assert isinstance(result, AlreadyHandled)
    assert await stock_and_version(unit_of_work, sku) == (5, 1)


async def test_releasing_a_retired_product_restores_its_stock_and_says_it_is_retired(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    sku = await add_product(unit_of_work, stock=5)
    order_id = uuid4()
    await reserve(unit_of_work, order_id, line(sku, 2))
    await retire(unit_of_work, sku)

    [item] = await release(unit_of_work, order_id)

    assert item.retired
    assert item.product.stock == 5


async def test_releasing_a_rejected_order_moves_nothing(unit_of_work: UnitOfWorkFactory) -> None:
    sku = await add_product(unit_of_work, stock=1)
    order_id = uuid4()
    await reserve(unit_of_work, order_id, line(sku, 2))

    assert await release(unit_of_work, order_id) == ()
    assert await stock_and_version(unit_of_work, sku) == (1, 1)
