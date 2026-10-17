from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from ecommerce_contracts import (
    CATALOG_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    Envelope,
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
