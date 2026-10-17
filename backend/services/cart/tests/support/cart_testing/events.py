from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ecommerce_contracts import (
    CATALOG_TOPIC,
    ORDER_CONFIRMED,
    ORDERS_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    Envelope,
    OrderConfirmedV1,
    OrderLineV1,
    ProductDeletedV1,
    ProductUpdatedV1,
)
from ecommerce_messaging import IncomingMessage

CORRELATION = UUID("9a4e6b21-0d7c-4f35-8b12-c3e5a7d90f68")
OCCURRED = datetime(2026, 10, 16, 10, 30, tzinfo=UTC)


def updated_event(
    sku: str = "RS-001",
    version: int = 2,
    price: str = "79.90",
    stock: int = 5,
    name: str = "Running Shoes",
    image_key: str | None = None,
) -> Envelope[ProductUpdatedV1]:
    return Envelope[ProductUpdatedV1](
        event_id=uuid4(),
        event_type=PRODUCT_UPDATED,
        event_version=1,
        correlation_id=CORRELATION,
        producer="catalog-service",
        payload=ProductUpdatedV1(
            sku=sku,
            name=name,
            price=Decimal(price),
            stock=stock,
            image_key=image_key,
            version=version,
            occurred_at=OCCURRED,
        ),
    )


def deleted_event(sku: str = "RS-001", version: int = 3) -> Envelope[ProductDeletedV1]:
    return Envelope[ProductDeletedV1](
        event_id=uuid4(),
        event_type=PRODUCT_DELETED,
        event_version=1,
        correlation_id=CORRELATION,
        producer="catalog-service",
        payload=ProductDeletedV1(sku=sku, version=version, occurred_at=OCCURRED),
    )


def message_of(
    event: Envelope[ProductUpdatedV1] | Envelope[ProductDeletedV1], offset: int = 0
) -> IncomingMessage:
    return IncomingMessage(
        CATALOG_TOPIC, 0, offset, event.payload.sku, event.model_dump_json().encode()
    )


def confirmed_event(
    customer_id: UUID,
    skus: list[str],
    occurred_at: datetime = OCCURRED,
    order_id: UUID | None = None,
) -> Envelope[OrderConfirmedV1]:
    return Envelope[OrderConfirmedV1](
        event_id=uuid4(),
        event_type=ORDER_CONFIRMED,
        event_version=1,
        correlation_id=CORRELATION,
        producer="orders-service",
        payload=OrderConfirmedV1(
            order_id=order_id or uuid4(),
            customer_id=customer_id,
            lines=[OrderLineV1(sku=sku, quantity=1, unit_price=Decimal("10.00")) for sku in skus],
            total=Decimal("10.00") * len(skus),
            currency="USD",
            occurred_at=occurred_at,
        ),
    )


def order_message_of(event: Envelope[OrderConfirmedV1], offset: int = 0) -> IncomingMessage:
    return IncomingMessage(
        ORDERS_TOPIC, 0, offset, str(event.payload.order_id), event.model_dump_json().encode()
    )
