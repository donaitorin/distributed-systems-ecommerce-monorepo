from itertools import product

import pytest

from orders.domain.status import (
    ALLOWED_TRANSITIONS,
    CANCELLABLE,
    InvalidTransitionError,
    OrderStatus,
    ensure_transition_allowed,
    sources_of,
)

VALID = [
    (OrderStatus.PENDING, OrderStatus.STOCK_RESERVED),
    (OrderStatus.PENDING, OrderStatus.CANCELLED),
    (OrderStatus.STOCK_RESERVED, OrderStatus.PAID),
    (OrderStatus.STOCK_RESERVED, OrderStatus.CONFIRMED),
    (OrderStatus.STOCK_RESERVED, OrderStatus.CANCELLED),
    (OrderStatus.PAID, OrderStatus.CONFIRMED),
]


@pytest.mark.parametrize(("current", "target"), VALID)
def test_the_documented_transitions_are_allowed(current: OrderStatus, target: OrderStatus) -> None:
    ensure_transition_allowed(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [pair for pair in product(OrderStatus, OrderStatus) if pair not in VALID],
)
def test_every_other_transition_is_refused(current: OrderStatus, target: OrderStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        ensure_transition_allowed(current, target)


@pytest.mark.parametrize("final", [OrderStatus.CONFIRMED, OrderStatus.CANCELLED])
def test_confirmed_and_cancelled_are_final(final: OrderStatus) -> None:
    assert ALLOWED_TRANSITIONS[final] == frozenset()


def test_only_orders_that_have_not_been_paid_can_be_cancelled() -> None:
    assert {OrderStatus.PENDING, OrderStatus.STOCK_RESERVED} == CANCELLABLE
    assert sources_of(OrderStatus.CANCELLED) == CANCELLABLE


def test_a_confirmed_order_can_come_from_paid_or_from_a_zero_total_reservation() -> None:
    assert sources_of(OrderStatus.CONFIRMED) == {OrderStatus.PAID, OrderStatus.STOCK_RESERVED}
