from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Text,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ecommerce_messaging import outbox_table
from orders.domain.status import OrderStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

STATUS_LIST = ", ".join(f"'{item.value}'" for item in OrderStatus)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class OrderModel(Base):
    __tablename__ = "orders"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    customer_id: Mapped[UUID] = mapped_column()
    customer_email: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    card_last4: Mapped[str] = mapped_column(String(4))
    shipping_address: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[UUID] = mapped_column()
    cancel_reason: Mapped[str | None] = mapped_column(String(100))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"status IN ({STATUS_LIST})", name="status_known"),
        CheckConstraint("total >= 0", name="total_non_negative"),
        CheckConstraint("card_last4 ~ '^[0-9]{4}$'", name="card_last4_digits"),
        Index("ix_orders_customer_id_created_at_id", "customer_id", desc("created_at"), desc("id")),
        Index("ix_orders_created_at_id", desc("created_at"), desc("id")),
        Index("ix_orders_status_created_at_id", "status", desc("created_at"), desc("id")),
        Index(
            "ix_orders_open_created_at",
            "created_at",
            postgresql_where=text("status IN ('PENDING', 'STOCK_RESERVED')"),
        ),
    )


class OrderLineModel(Base):
    __tablename__ = "order_lines"

    order_id: Mapped[UUID] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
    )


class OrderStatusHistoryModel(Base):
    __tablename__ = "order_status_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    order_id: Mapped[UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"to_status IN ({STATUS_LIST})", name="to_status_known"),
        Index("ix_order_status_history_order_id_id", "order_id", "id"),
    )


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    order_id: Mapped[UUID] = mapped_column()
    response_status: Mapped[int] = mapped_column(SmallInteger)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_idempotency_keys_expires_at", "expires_at"),)


OUTBOX = outbox_table(Base.metadata)
