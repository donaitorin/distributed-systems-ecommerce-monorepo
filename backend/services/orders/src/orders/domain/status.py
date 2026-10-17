from enum import StrEnum


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    STOCK_RESERVED = "STOCK_RESERVED"
    PAID = "PAID"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.STOCK_RESERVED, OrderStatus.CANCELLED}),
    OrderStatus.STOCK_RESERVED: frozenset(
        {OrderStatus.PAID, OrderStatus.CONFIRMED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PAID: frozenset({OrderStatus.CONFIRMED}),
    OrderStatus.CONFIRMED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

CANCELLABLE = frozenset({OrderStatus.PENDING, OrderStatus.STOCK_RESERVED})

ORDER_CREATED_REASON = "order created"
STOCK_RESERVED_REASON = "stock reserved"
PAYMENT_SUCCEEDED_REASON = "payment succeeded"
NO_PAYMENT_DUE_REASON = "nothing to pay"
ORDER_CONFIRMED_REASON = "order confirmed"
PAYMENT_REFUNDED_REASON = "payment refunded"
PAYMENT_FAILED = "payment_failed"
SAGA_TIMEOUT = "saga_timeout"


class InvalidTransitionError(Exception):
    def __init__(self, current: OrderStatus, target: OrderStatus) -> None:
        super().__init__(f"an order cannot go from {current} to {target}")


def ensure_transition_allowed(current: OrderStatus, target: OrderStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransitionError(current, target)


def sources_of(target: OrderStatus) -> frozenset[OrderStatus]:
    return frozenset(
        current for current, targets in ALLOWED_TRANSITIONS.items() if target in targets
    )
