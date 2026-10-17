from datetime import datetime

from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_CONFIRMED,
    ORDER_CREATED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
    OrderCancelledV1,
    OrderConfirmedV1,
    OrderCreatedV1,
    OrderLineV1,
    OrderPaymentRequestedV1,
)
from orders.application.ports import UnitOfWork
from orders.domain.order import NewOrder, Order


def _lines_of(order: Order) -> list[OrderLineV1]:
    return [
        OrderLineV1(sku=line.sku, quantity=line.quantity, unit_price=line.unit_price)
        for line in order.lines
    ]


async def publish_created(uow: UnitOfWork, order: NewOrder, now: datetime) -> None:
    await uow.events.add(
        topic=ORDERS_TOPIC,
        key=str(order.id),
        event_type=ORDER_CREATED,
        payload=OrderCreatedV1(
            order_id=order.id,
            customer_id=order.customer_id,
            lines=[
                OrderLineV1(sku=line.sku, quantity=line.quantity, unit_price=line.unit_price)
                for line in order.request.lines
            ],
            occurred_at=now,
        ),
        correlation_id=order.correlation_id,
    )


async def publish_payment_requested(uow: UnitOfWork, order: Order, now: datetime) -> None:
    await uow.events.add(
        topic=ORDERS_TOPIC,
        key=str(order.id),
        event_type=ORDER_PAYMENT_REQUESTED,
        payload=OrderPaymentRequestedV1(
            order_id=order.id,
            customer_id=order.customer_id,
            amount=order.total,
            currency=order.currency,
            card_last4=order.card_last4,
            occurred_at=now,
        ),
        correlation_id=order.correlation_id,
    )


async def publish_confirmed(uow: UnitOfWork, order: Order, now: datetime) -> None:
    await uow.events.add(
        topic=ORDERS_TOPIC,
        key=str(order.id),
        event_type=ORDER_CONFIRMED,
        payload=OrderConfirmedV1(
            order_id=order.id,
            customer_id=order.customer_id,
            lines=_lines_of(order),
            total=order.total,
            currency=order.currency,
            occurred_at=now,
        ),
        correlation_id=order.correlation_id,
    )


async def publish_cancelled(uow: UnitOfWork, order: Order, reason: str, now: datetime) -> None:
    await uow.events.add(
        topic=ORDERS_TOPIC,
        key=str(order.id),
        event_type=ORDER_CANCELLED,
        payload=OrderCancelledV1(
            order_id=order.id, customer_id=order.customer_id, reason=reason, occurred_at=now
        ),
        correlation_id=order.correlation_id,
    )
