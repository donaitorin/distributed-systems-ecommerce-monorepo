from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from ecommerce_contracts import (
    INVENTORY_TOPIC,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    Envelope,
    PaymentFailedV1,
    PaymentRefundedV1,
    PaymentSucceededV1,
    ReservedLineV1,
    StockReservationFailedV1,
    StockReservedV1,
)
from ecommerce_messaging import OutgoingMessage

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
PAYMENT_ID = UUID("33333333-3333-4333-8333-333333333333")


def stock_reserved(order_id: UUID, lines: list[tuple[str, str, int, str]]) -> Envelope[Any]:
    return Envelope[StockReservedV1](
        event_type=STOCK_RESERVED,
        event_version=1,
        correlation_id=uuid4(),
        producer="catalog-service",
        payload=StockReservedV1(
            order_id=order_id,
            lines=[
                ReservedLineV1(sku=sku, name=name, quantity=quantity, unit_price=Decimal(price))
                for sku, name, quantity, price in lines
            ],
            occurred_at=NOW,
        ),
    )


def reservation_failed(order_id: UUID, reason: str = "insufficient_stock") -> Envelope[Any]:
    return Envelope[StockReservationFailedV1](
        event_type=STOCK_RESERVATION_FAILED,
        event_version=1,
        correlation_id=uuid4(),
        producer="catalog-service",
        payload=StockReservationFailedV1(order_id=order_id, reason=reason, occurred_at=NOW),
    )


def payment_succeeded(order_id: UUID, amount: str = "92.30") -> Envelope[Any]:
    return Envelope[PaymentSucceededV1](
        event_type=PAYMENT_SUCCEEDED,
        event_version=1,
        correlation_id=uuid4(),
        producer="payments-service",
        payload=PaymentSucceededV1(
            order_id=order_id,
            payment_id=PAYMENT_ID,
            amount=Decimal(amount),
            currency="USD",
            occurred_at=NOW,
        ),
    )


def payment_failed(order_id: UUID, reason: str = "card_declined") -> Envelope[Any]:
    return Envelope[PaymentFailedV1](
        event_type=PAYMENT_FAILED,
        event_version=1,
        correlation_id=uuid4(),
        producer="payments-service",
        payload=PaymentFailedV1(
            order_id=order_id, payment_id=PAYMENT_ID, reason=reason, occurred_at=NOW
        ),
    )


def payment_refunded(order_id: UUID, amount: str = "92.30") -> Envelope[Any]:
    return Envelope[PaymentRefundedV1](
        event_type=PAYMENT_REFUNDED,
        event_version=1,
        correlation_id=uuid4(),
        producer="payments-service",
        payload=PaymentRefundedV1(
            order_id=order_id,
            payment_id=PAYMENT_ID,
            amount=Decimal(amount),
            currency="USD",
            reason="order_already_cancelled",
            occurred_at=NOW,
        ),
    )


def outgoing(envelope: Envelope[Any]) -> OutgoingMessage:
    topic = INVENTORY_TOPIC if envelope.event_type.startswith("stock.") else PAYMENTS_TOPIC
    return OutgoingMessage(
        topic, str(envelope.payload.order_id), envelope.model_dump_json().encode()
    )
