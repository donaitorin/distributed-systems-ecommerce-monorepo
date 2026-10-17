from datetime import timedelta
from uuid import UUID

import pytest
from cart_testing.events import OCCURRED, confirmed_event
from cart_testing.support import product

from cart.application.purchases import PurchasedLines
from cart.domain.cart import CartLine
from cart.infra.memory import InMemoryCartStore

CUSTOMER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture
def store() -> InMemoryCartStore:
    return InMemoryCartStore()


async def put(
    store: InMemoryCartStore, user: UUID, sku: str, added_at: object = OCCURRED - timedelta(hours=1)
) -> None:
    line = CartLine.started(product(sku=sku), 2, added_at)  # type: ignore[arg-type]
    await store.put_line(str(user), line, 100)


async def skus(store: InMemoryCartStore, user: UUID) -> list[str]:
    return [line.sku for line in await store.lines(str(user))]


async def test_the_purchased_lines_leave_the_cart_and_the_others_stay(
    store: InMemoryCartStore,
) -> None:
    for sku in ("A-1", "B-2", "C-3"):
        await put(store, CUSTOMER, sku)

    await PurchasedLines(store).confirmed(confirmed_event(CUSTOMER, ["A-1", "C-3"]))

    assert await skus(store, CUSTOMER) == ["B-2"]


async def test_only_the_customer_who_bought_loses_lines(store: InMemoryCartStore) -> None:
    await put(store, CUSTOMER, "A-1")
    await put(store, OTHER, "A-1")

    await PurchasedLines(store).confirmed(confirmed_event(CUSTOMER, ["A-1"]))

    assert await skus(store, CUSTOMER) == []
    assert await skus(store, OTHER) == ["A-1"]


async def test_delivering_the_same_confirmation_twice_changes_nothing_more(
    store: InMemoryCartStore,
) -> None:
    await put(store, CUSTOMER, "A-1")
    await put(store, CUSTOMER, "B-2")
    event = confirmed_event(CUSTOMER, ["A-1"])

    await PurchasedLines(store).confirmed(event)
    await PurchasedLines(store).confirmed(event)

    assert await skus(store, CUSTOMER) == ["B-2"]


async def test_a_line_added_after_the_purchase_survives_a_replay_of_the_confirmation(
    store: InMemoryCartStore,
) -> None:
    await put(store, CUSTOMER, "A-1", added_at=OCCURRED + timedelta(minutes=5))

    await PurchasedLines(store).confirmed(confirmed_event(CUSTOMER, ["A-1"]))

    assert await skus(store, CUSTOMER) == ["A-1"]


async def test_a_confirmation_for_an_empty_or_unknown_cart_is_harmless(
    store: InMemoryCartStore,
) -> None:
    await PurchasedLines(store).confirmed(confirmed_event(CUSTOMER, ["A-1", "B-2"]))

    assert await skus(store, CUSTOMER) == []
