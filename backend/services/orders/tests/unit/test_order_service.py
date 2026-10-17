from uuid import UUID, uuid4

import pytest
from orders_testing.data import CUSTOMER, OTHER_CUSTOMER, SteppingClock, order_request

from ecommerce_contracts import ORDER_CREATED, ORDERS_TOPIC, OrderCreatedV1
from orders.application.cursors import InvalidCursorError
from orders.application.errors import (
    IdempotencyKeyReusedError,
    InvalidIdempotencyKeyError,
    OrderNotFoundError,
)
from orders.application.orders import OrderService
from orders.domain.listing import OrderFilters
from orders.domain.status import ORDER_CREATED_REASON, OrderStatus
from orders.infra.memory import InMemoryStore, InMemoryUnitOfWork

KEY = "checkout-0001"
CORRELATION = UUID(int=77)


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> OrderService:
    return OrderService(lambda: InMemoryUnitOfWork(store), clock)


async def test_placing_an_order_stores_it_pending_with_its_lines_history_and_event(
    service: OrderService, store: InMemoryStore
) -> None:
    placement = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    order = await service.get_own(CUSTOMER, placement.order_id)
    assert placement.status_code == 202
    assert placement.body == {"id": str(placement.order_id), "status": "PENDING"}
    assert not placement.replayed
    assert (order.status, str(order.total), order.currency) == (
        OrderStatus.PENDING,
        "92.30",
        "USD",
    )
    assert [(line.sku, line.quantity, str(line.unit_price)) for line in order.lines] == [
        ("RS-001", 2, "39.90"),
        ("XS-001", 1, "12.50"),
    ]
    assert [(h.from_status, h.to_status, h.reason) for h in order.history] == [
        (None, OrderStatus.PENDING, ORDER_CREATED_REASON)
    ]
    [event] = store.outbox
    assert (event.topic, event.event_type, event.key) == (
        ORDERS_TOPIC,
        ORDER_CREATED,
        str(order.id),
    )
    assert event.correlation_id == CORRELATION
    assert isinstance(event.payload, OrderCreatedV1)
    assert [line.sku for line in event.payload.lines] == ["RS-001", "XS-001"]


async def test_the_email_of_the_customer_is_kept_on_the_order_and_its_summary(
    service: OrderService,
) -> None:
    placement = await service.place(
        CUSTOMER, KEY, order_request(), CORRELATION, customer_email="ada@example.com"
    )

    order = await service.get_any(placement.order_id)
    page = await service.list_all(OrderFilters(), 25, None)
    assert order.customer_email == "ada@example.com"
    assert [item.customer_email for item in page.items] == ["ada@example.com"]


async def test_an_order_placed_without_an_email_has_none(service: OrderService) -> None:
    placement = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    assert (await service.get_any(placement.order_id)).customer_email is None


async def test_a_replay_does_not_change_the_stored_email(service: OrderService) -> None:
    first = await service.place(
        CUSTOMER, KEY, order_request(), CORRELATION, customer_email="ada@example.com"
    )

    again = await service.place(
        CUSTOMER, KEY, order_request(), CORRELATION, customer_email="new@example.com"
    )

    assert again.replayed
    assert (await service.get_any(first.order_id)).customer_email == "ada@example.com"


async def test_the_same_key_and_body_return_the_same_order_without_a_second_event(
    service: OrderService, store: InMemoryStore
) -> None:
    first = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    second = await service.place(CUSTOMER, KEY, order_request(), uuid4())

    assert second.replayed
    assert (second.order_id, second.status_code, second.body) == (
        first.order_id,
        first.status_code,
        first.body,
    )
    assert len(store.orders) == 1
    assert len(store.outbox) == 1


async def test_the_replayed_response_does_not_change_when_the_order_moves_on(
    service: OrderService, store: InMemoryStore, clock: SteppingClock
) -> None:
    first = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)
    async with InMemoryUnitOfWork(store) as uow:
        await uow.orders.transition(
            first.order_id,
            {OrderStatus.PENDING},
            OrderStatus.CANCELLED,
            store.orders[first.order_id].created_at,
            "x",
        )
        await uow.commit()

    again = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    assert again.body["status"] == "PENDING"


async def test_the_same_key_with_a_different_body_is_rejected(
    service: OrderService, store: InMemoryStore
) -> None:
    await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    with pytest.raises(IdempotencyKeyReusedError):
        await service.place(CUSTOMER, KEY, order_request([("RS-001", 3, "39.90")]), CORRELATION)

    assert len(store.orders) == 1


async def test_two_customers_can_use_the_same_key_independently(
    service: OrderService, store: InMemoryStore
) -> None:
    first = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)
    second = await service.place(OTHER_CUSTOMER, KEY, order_request(), CORRELATION)

    assert first.order_id != second.order_id
    assert not second.replayed


async def test_a_key_can_be_used_again_after_twenty_four_hours(
    service: OrderService, clock: SteppingClock
) -> None:
    first = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)
    clock.advance(seconds=24 * 3600)

    later = await service.place(CUSTOMER, KEY, order_request([("RS-001", 3, "39.90")]), CORRELATION)

    assert later.order_id != first.order_id
    assert not later.replayed


async def test_a_key_still_replays_just_before_it_expires(
    service: OrderService, clock: SteppingClock
) -> None:
    first = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)
    clock.advance(seconds=24 * 3600 - 1)

    assert (
        await service.place(CUSTOMER, KEY, order_request(), CORRELATION)
    ).order_id == first.order_id


@pytest.mark.parametrize("key", ["", "short", "has space in it", "x" * 129])
async def test_a_malformed_key_is_rejected_before_anything_is_stored(
    service: OrderService, store: InMemoryStore, key: str
) -> None:
    with pytest.raises(InvalidIdempotencyKeyError):
        await service.place(CUSTOMER, key, order_request(), CORRELATION)

    assert not store.orders
    assert not store.idempotency


async def test_a_customer_cannot_read_someone_elses_order(service: OrderService) -> None:
    placed = await service.place(CUSTOMER, KEY, order_request(), CORRELATION)

    with pytest.raises(OrderNotFoundError):
        await service.get_own(OTHER_CUSTOMER, placed.order_id)
    assert (await service.get_any(placed.order_id)).id == placed.order_id


async def test_an_unknown_order_is_not_found(service: OrderService) -> None:
    with pytest.raises(OrderNotFoundError):
        await service.get_any(uuid4())


async def place_many(service: OrderService, clock: SteppingClock, count: int) -> list[UUID]:
    ids = []
    for index in range(count):
        clock.advance(seconds=1)
        placed = await service.place(
            CUSTOMER, f"checkout-{index:04d}", order_request(), CORRELATION
        )
        ids.append(placed.order_id)
    return ids


async def test_the_list_is_newest_first_and_the_cursor_walks_every_order_once(
    service: OrderService, clock: SteppingClock
) -> None:
    ids = await place_many(service, clock, 7)
    seen: list[UUID] = []
    cursor = None

    while True:
        page = await service.list_own(CUSTOMER, OrderFilters(), 3, cursor)
        seen.extend(item.id for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert seen == list(reversed(ids))


async def test_the_list_only_shows_the_customers_own_orders(
    service: OrderService, clock: SteppingClock
) -> None:
    await place_many(service, clock, 2)
    await service.place(OTHER_CUSTOMER, KEY, order_request(), CORRELATION)

    own = await service.list_own(CUSTOMER, OrderFilters(), 25, None)
    everything = await service.list_all(OrderFilters(), 25, None)

    assert len(own.items) == 2
    assert len(everything.items) == 3
    assert own.items[0].item_count == 3


async def test_filters_narrow_by_status_and_dates(
    service: OrderService, clock: SteppingClock, store: InMemoryStore
) -> None:
    ids = await place_many(service, clock, 4)
    async with InMemoryUnitOfWork(store) as uow:
        await uow.orders.transition(
            ids[1], {OrderStatus.PENDING}, OrderStatus.CANCELLED, clock.now, "test"
        )
        await uow.commit()

    cancelled = await service.list_all(OrderFilters(status=OrderStatus.CANCELLED), 25, None)
    window = await service.list_all(
        OrderFilters(
            created_from=store.orders[ids[1]].created_at,
            created_to=store.orders[ids[3]].created_at,
        ),
        25,
        None,
    )

    assert [item.id for item in cancelled.items] == [ids[1]]
    assert [item.id for item in window.items] == [ids[2], ids[1]]


async def test_a_cursor_from_other_filters_is_refused(
    service: OrderService, clock: SteppingClock
) -> None:
    await place_many(service, clock, 3)
    page = await service.list_all(OrderFilters(), 1, None)

    with pytest.raises(InvalidCursorError):
        await service.list_all(OrderFilters(status=OrderStatus.CONFIRMED), 1, page.next_cursor)
