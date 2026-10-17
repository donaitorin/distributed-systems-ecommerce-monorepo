from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    MetaData,
    Numeric,
    String,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ecommerce_messaging import outbox_table
from payments.domain.payment import PaymentStatus

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

STATUS_LIST = ", ".join(f"'{item.value}'" for item in PaymentStatus)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    order_id: Mapped[UUID] = mapped_column(unique=True)
    customer_id: Mapped[UUID] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3))
    card_last4: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(10))
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    order_cancelled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(f"status IN ({STATUS_LIST})", name="status_known"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("card_last4 ~ '^[0-9]{4}$'", name="card_last4_digits"),
        Index(
            "ix_payments_check_after",
            "check_after",
            postgresql_where=text("status = 'PENDING' AND check_after IS NOT NULL"),
        ),
        Index(
            "ix_payments_refund_due",
            "order_id",
            postgresql_where=text("status = 'SUCCEEDED' AND order_cancelled"),
        ),
    )


OUTBOX = outbox_table(Base.metadata)
