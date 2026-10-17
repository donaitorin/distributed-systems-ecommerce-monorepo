from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

CURRENCY = "USD"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


CARD_DECLINED = "card_declined"
ORDER_CANCELLED_REFUND = "order_cancelled"


@dataclass(frozen=True, slots=True)
class NewPayment:
    order_id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
    card_last4: str
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class Payment:
    id: UUID
    order_id: UUID
    customer_id: UUID
    amount: Decimal
    currency: str
    card_last4: str
    status: PaymentStatus
    failure_reason: str | None
    order_cancelled: bool
    submitted_at: datetime | None
    check_after: datetime | None
    refunded_at: datetime | None
    correlation_id: UUID
    created_at: datetime
    updated_at: datetime

    @property
    def awaiting_provider(self) -> bool:
        return self.status is PaymentStatus.PENDING and self.submitted_at is None


@dataclass(frozen=True, slots=True)
class ChargeRequest:
    order_id: UUID
    amount: Decimal
    currency: str
    card_last4: str
    idempotency_key: str

    @classmethod
    def for_payment(cls, payment: Payment) -> "ChargeRequest":
        return cls(
            payment.order_id,
            payment.amount,
            payment.currency,
            payment.card_last4,
            str(payment.order_id),
        )


@dataclass(frozen=True, slots=True)
class RefundRequest:
    order_id: UUID
    amount: Decimal
    currency: str
    idempotency_key: str

    @classmethod
    def for_payment(cls, payment: Payment) -> "RefundRequest":
        return cls(payment.order_id, payment.amount, payment.currency, f"refund-{payment.order_id}")


@dataclass(frozen=True, slots=True)
class Succeeded:
    reference: str


@dataclass(frozen=True, slots=True)
class Declined:
    reason: str


@dataclass(frozen=True, slots=True)
class Processing:
    check_after: datetime | None


type ChargeOutcome = Succeeded | Declined | Processing
