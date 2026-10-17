from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from catalog.application.ports import UnitOfWorkFactory
from catalog.domain.product import NewProduct, ProductData
from catalog.domain.reservation import ReservationLine
from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_CREATED,
    ORDERS_TOPIC,
    Envelope,
    OrderCancelledV1,
    OrderCreatedV1,
    OrderLineV1,
)
from ecommerce_messaging import OutgoingMessage

NOW = datetime(2026, 10, 17, 9, 0, tzinfo=UTC)
CUSTOMER = UUID(int=7)


def unique_sku() -> str:
    return f"R{uuid4().hex[:12].upper()}"


async def add_product(
    factory: UnitOfWorkFactory, price: str = "10.00", stock: int = 5, sku: str | None = None
) -> str:
    chosen = sku or unique_sku()
    data = ProductData("Widget", None, None, Decimal(price), stock, None)
    async with factory() as uow:
        await uow.products.add(NewProduct(chosen, data), NOW)
        await uow.commit()
    return chosen


async def stock_and_version(factory: UnitOfWorkFactory, sku: str) -> tuple[int, int]:
    async with factory() as uow:
        product = await uow.products.get(sku)
    assert product is not None
    return product.stock, product.version


async def retire(factory: UnitOfWorkFactory, sku: str) -> None:
    async with factory() as uow:
        await uow.products.soft_delete(sku, NOW)
        await uow.commit()


async def restock(factory: UnitOfWorkFactory, sku: str, stock: int) -> None:
    async with factory() as uow:
        product = await uow.products.get(sku)
        assert product is not None
        data = ProductData(product.name, None, None, product.price, stock, None)
        await uow.products.replace(sku, data, NOW)
        await uow.commit()


def line(sku: str, quantity: int = 1, price: str = "10.00") -> ReservationLine:
    return ReservationLine.of(sku, quantity, Decimal(price))


def created_event(
    order_id: UUID, *lines: ReservationLine, correlation_id: UUID | None = None
) -> Envelope[OrderCreatedV1]:
    return Envelope[OrderCreatedV1](
        event_type=ORDER_CREATED,
        event_version=1,
        correlation_id=correlation_id or uuid4(),
        producer="orders-service",
        payload=OrderCreatedV1(
            order_id=order_id,
            customer_id=CUSTOMER,
            lines=[
                OrderLineV1(sku=item.sku, quantity=item.quantity, unit_price=item.expected_price)
                for item in lines
            ],
            occurred_at=NOW,
        ),
    )


def cancelled_event(
    order_id: UUID, correlation_id: UUID | None = None
) -> Envelope[OrderCancelledV1]:
    return Envelope[OrderCancelledV1](
        event_type=ORDER_CANCELLED,
        event_version=1,
        correlation_id=correlation_id or uuid4(),
        producer="orders-service",
        payload=OrderCancelledV1(
            order_id=order_id, customer_id=CUSTOMER, reason="payment_failed", occurred_at=NOW
        ),
    )


def outgoing(envelope: Envelope[Any]) -> OutgoingMessage:
    key = str(getattr(envelope.payload, "order_id", ""))
    return OutgoingMessage(ORDERS_TOPIC, key, envelope.model_dump_json().encode())
