from datetime import datetime
from uuid import UUID

from catalog.application.ports import UnitOfWork
from catalog.domain.imports import ChangedProduct
from catalog.domain.product import Product
from ecommerce_contracts import (
    CATALOG_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    ProductDeletedV1,
    ProductUpdatedV1,
)


async def publish_product_updated(
    uow: UnitOfWork, product: Product | ChangedProduct, occurred_at: datetime, correlation_id: UUID
) -> None:
    await uow.events.add(
        topic=CATALOG_TOPIC,
        key=product.sku,
        event_type=PRODUCT_UPDATED,
        payload=ProductUpdatedV1(
            sku=product.sku,
            name=product.name,
            price=product.price,
            stock=product.stock,
            image_key=product.image_key,
            version=product.version,
            occurred_at=occurred_at,
        ),
        correlation_id=correlation_id,
    )


async def publish_product_deleted(
    uow: UnitOfWork, sku: str, version: int, occurred_at: datetime, correlation_id: UUID
) -> None:
    await uow.events.add(
        topic=CATALOG_TOPIC,
        key=sku,
        event_type=PRODUCT_DELETED,
        payload=ProductDeletedV1(sku=sku, version=version, occurred_at=occurred_at),
        correlation_id=correlation_id,
    )
