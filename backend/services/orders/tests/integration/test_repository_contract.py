from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from orders_testing.data import order_request

from orders.application.ports import UnitOfWorkFactory
from orders.domain.idempotency import IdempotencyRecord
from orders.domain.listing import OrderFilters, Position
from orders.domain.order import NewOrder
from orders.domain.status import ORDER_CREATED_REASON, OrderStatus

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def new_order(customer: UUID | None = None, email: str | None = None) -> NewOrder:
    return NewOrder(uuid4(), customer or uuid4(), order_request(), uuid4(), email)


async def add(factory: UnitOfWorkFactory, order: NewOrder, now: datetime = NOW) -> None:
    async with factory() as uow:
        await uow.orders.add(order, order.request.total, now)
        await uow.commit()


def record(
    user_id: UUID,
    key: str = "key-12345678",
    fingerprint: str = "f1",
    expires: timedelta | None = None,
) -> IdempotencyRecord:
    return IdempotencyRecord(
        user_id,
        key,
        fingerprint,
        uuid4(),
        202,
        {"id": "x", "status": "PENDING"},
        NOW,
        NOW + (expires or timedelta(hours=24)),
    )


async def test_an_added_order_reads_back_with_lines_history_and_exact_money(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    order = new_order()
    await add(unit_of_work, order)

    async with unit_of_work() as uow:
        stored = await uow.orders.get(order.id)

    assert stored is not None
    assert (stored.status, str(stored.total), stored.card_last4) == (
        OrderStatus.PENDING,
        "92.30",
        "1111",
    )
    assert stored.correlation_id == order.correlation_id
    assert stored.shipping_address == order.request.shipping_address
    assert [(i.position, i.sku, i.name, i.quantity, str(i.unit_price)) for i in stored.lines] == [
        (0, "RS-001", None, 2, "39.90"),
        (1, "XS-001", None, 1, "12.50"),
    ]
    assert [(h.from_status, h.to_status, h.reason, h.at) for h in stored.history] == [
        (None, OrderStatus.PENDING, ORDER_CREATED_REASON, NOW)
    ]


async def test_an_unknown_order_is_none(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.orders.get(uuid4()) is None


async def test_uncommitted_work_is_discarded(unit_of_work: UnitOfWorkFactory) -> None:
    order = new_order()
    async with unit_of_work() as uow:
        await uow.orders.add(order, order.request.total, NOW)

    async with unit_of_work() as uow:
        assert await uow.orders.get(order.id) is None


async def test_a_transition_only_happens_from_an_expected_status(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    order = new_order()
    await add(unit_of_work, order)
    later = NOW + timedelta(seconds=5)

    async with unit_of_work() as uow:
        wrong = await uow.orders.transition(
            order.id, {OrderStatus.STOCK_RESERVED}, OrderStatus.CANCELLED, later, "nope"
        )
        right = await uow.orders.transition(
            order.id, {OrderStatus.PENDING}, OrderStatus.STOCK_RESERVED, later, "stock reserved"
        )
        again = await uow.orders.transition(
            order.id, {OrderStatus.PENDING}, OrderStatus.STOCK_RESERVED, later, "stock reserved"
        )
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.orders.get(order.id)
    assert (wrong, right, again) == (False, True, False)
    assert stored is not None
    assert (stored.status, stored.updated_at) == (OrderStatus.STOCK_RESERVED, later)
    assert [(h.from_status, h.to_status) for h in stored.history] == [
        (None, OrderStatus.PENDING),
        (OrderStatus.PENDING, OrderStatus.STOCK_RESERVED),
    ]


async def test_cancelling_records_the_reason_on_the_order_and_in_the_history(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    order = new_order()
    await add(unit_of_work, order)

    async with unit_of_work() as uow:
        await uow.orders.transition(
            order.id, {OrderStatus.PENDING}, OrderStatus.CANCELLED, NOW, "insufficient_stock"
        )
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.orders.get(order.id)
    assert stored is not None
    assert stored.cancel_reason == "insufficient_stock"
    assert stored.history[-1].reason == "insufficient_stock"


async def test_line_names_are_filled_from_the_reservation(unit_of_work: UnitOfWorkFactory) -> None:
    order = new_order()
    await add(unit_of_work, order)

    async with unit_of_work() as uow:
        await uow.orders.name_lines(order.id, {"RS-001": "Rust in Action", "OTHER": "ignored"})
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.orders.get(order.id)
    assert stored is not None
    assert [line.name for line in stored.lines] == ["Rust in Action", None]


async def test_a_refund_is_recorded_once_and_only_on_cancelled_orders(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    order = new_order()
    await add(unit_of_work, order)
    async with unit_of_work() as uow:
        early = await uow.orders.mark_refunded(order.id, NOW, "payment refunded")
        await uow.orders.transition(
            order.id, {OrderStatus.PENDING}, OrderStatus.CANCELLED, NOW, "saga_timeout"
        )
        first = await uow.orders.mark_refunded(order.id, NOW, "payment refunded")
        second = await uow.orders.mark_refunded(order.id, NOW, "payment refunded")
        await uow.commit()

    async with unit_of_work() as uow:
        stored = await uow.orders.get(order.id)
    assert (early, first, second) == (False, True, False)
    assert stored is not None
    assert (stored.status, stored.refunded_at) == (OrderStatus.CANCELLED, NOW)
    assert [h.reason for h in stored.history].count("payment refunded") == 1


async def test_pages_are_newest_first_stable_and_scoped_to_the_customer(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    customer = uuid4()
    orders = [new_order(customer) for _ in range(5)]
    for index, order in enumerate(orders):
        await add(unit_of_work, order, NOW + timedelta(seconds=index))
    await add(unit_of_work, new_order())
    seen: list[UUID] = []
    after: Position | None = None

    while True:
        async with unit_of_work() as uow:
            rows = await uow.orders.list_page(customer, OrderFilters(), after, 2)
        seen.extend(row.id for row in rows[:2])
        if len(rows) <= 2:
            break
        after = Position(rows[1].created_at, rows[1].id)

    assert seen == [order.id for order in reversed(orders)]


async def test_equal_timestamps_are_ordered_by_id_without_skipping_rows(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    customer = uuid4()
    orders = [new_order(customer) for _ in range(4)]
    for order in orders:
        await add(unit_of_work, order)
    expected = sorted((order.id for order in orders), reverse=True)

    async with unit_of_work() as uow:
        first = await uow.orders.list_page(customer, OrderFilters(), None, 2)
        after = Position(first[1].created_at, first[1].id)
        rest = await uow.orders.list_page(customer, OrderFilters(), after, 2)

    assert [row.id for row in first[:2] + rest[:2]] == expected


async def test_filters_by_status_and_creation_window(unit_of_work: UnitOfWorkFactory) -> None:
    customer = uuid4()
    orders = [new_order(customer) for _ in range(3)]
    for index, order in enumerate(orders):
        await add(unit_of_work, order, NOW + timedelta(minutes=index))
    async with unit_of_work() as uow:
        await uow.orders.transition(
            orders[1].id, {OrderStatus.PENDING}, OrderStatus.CANCELLED, NOW, "x"
        )
        await uow.commit()

    async with unit_of_work() as uow:
        cancelled = await uow.orders.list_page(
            customer, OrderFilters(status=OrderStatus.CANCELLED), None, 10
        )
        window = await uow.orders.list_page(
            customer,
            OrderFilters(
                created_from=NOW + timedelta(minutes=1), created_to=NOW + timedelta(minutes=2)
            ),
            None,
            10,
        )

    assert [row.id for row in cancelled] == [orders[1].id]
    assert [row.id for row in window] == [orders[1].id]
    assert cancelled[0].item_count == 3


async def test_only_open_orders_older_than_the_cutoff_are_found_for_the_timeout(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    customer = uuid4()
    old, fresh, finished = new_order(customer), new_order(customer), new_order(customer)
    base = datetime(2001, 1, 1, tzinfo=UTC)
    await add(unit_of_work, old, base)
    await add(unit_of_work, finished, base + timedelta(seconds=1))
    await add(unit_of_work, fresh, base + timedelta(days=1))
    async with unit_of_work() as uow:
        await uow.orders.transition(
            finished.id, {OrderStatus.PENDING}, OrderStatus.CANCELLED, base, "x"
        )
        await uow.commit()

    async with unit_of_work() as uow:
        found = await uow.orders.lock_expired(base + timedelta(hours=1), 10)

    assert old.id in found
    assert finished.id not in found
    assert fresh.id not in found


async def test_the_first_claim_wins_and_the_second_sees_the_stored_record(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user = uuid4()
    first, second = record(user), record(user, fingerprint="f2")

    async with unit_of_work() as uow:
        won = await uow.idempotency.claim(first, NOW)
        await uow.commit()
    async with unit_of_work() as uow:
        lost = await uow.idempotency.claim(second, NOW)

    assert won is None
    assert lost == first


async def test_the_same_key_belongs_to_one_customer_only(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.idempotency.claim(record(uuid4()), NOW) is None
        assert await uow.idempotency.claim(record(uuid4()), NOW) is None


async def test_an_expired_key_is_replaced_by_the_next_claim(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user = uuid4()
    old = record(user, expires=timedelta(hours=1))
    async with unit_of_work() as uow:
        await uow.idempotency.claim(old, NOW)
        await uow.commit()
    renewed = record(user, fingerprint="f2")
    later = NOW + timedelta(hours=1)

    async with unit_of_work() as uow:
        outcome = await uow.idempotency.claim(renewed, later)
        await uow.commit()
    async with unit_of_work() as uow:
        again = await uow.idempotency.claim(record(user), later)

    assert outcome is None
    assert again is not None
    assert again.fingerprint == "f2"


async def test_purging_removes_only_expired_keys(unit_of_work: UnitOfWorkFactory) -> None:
    user = uuid4()
    async with unit_of_work() as uow:
        await uow.idempotency.claim(record(user, "short-key-0001", expires=timedelta(hours=1)), NOW)
        await uow.idempotency.claim(record(user, "long-key-00001"), NOW)
        await uow.commit()
    later = NOW + timedelta(hours=2)

    async with unit_of_work() as uow:
        purged = await uow.idempotency.purge_expired(later)
        await uow.commit()
    async with unit_of_work() as uow:
        kept = await uow.idempotency.claim(record(user, "long-key-00001"), later)
        reusable = await uow.idempotency.claim(record(user, "short-key-0001"), later)

    assert purged >= 1
    assert kept is not None
    assert reusable is None


async def test_the_customer_email_is_stored_and_read_back_in_the_order_and_the_list(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    customer = uuid4()
    with_email = new_order(customer, "ada@example.com")
    without = new_order(customer)
    await add(unit_of_work, with_email, NOW)
    await add(unit_of_work, without, NOW + timedelta(seconds=1))

    async with unit_of_work() as uow:
        stored = await uow.orders.get(with_email.id)
        other = await uow.orders.get(without.id)
        rows = await uow.orders.list_page(customer, OrderFilters(), None, 10)

    assert stored is not None
    assert other is not None
    assert (stored.customer_email, other.customer_email) == ("ada@example.com", None)
    assert [row.customer_email for row in rows] == [None, "ada@example.com"]


async def test_changing_the_status_keeps_the_customer_email(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    order = new_order(email="ada@example.com")
    await add(unit_of_work, order)

    async with unit_of_work() as uow:
        await uow.orders.transition(
            order.id, {OrderStatus.PENDING}, OrderStatus.CANCELLED, NOW, "saga_timeout"
        )
        await uow.commit()
        stored = await uow.orders.get(order.id)

    assert stored is not None
    assert (stored.status, stored.customer_email) == (OrderStatus.CANCELLED, "ada@example.com")
