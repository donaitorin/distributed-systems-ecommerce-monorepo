from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from payments.domain.payment import Payment, PaymentStatus


class PaymentOut(BaseModel):
    id: UUID
    order_id: UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    card_last4: str
    failure_reason: str | None
    refunded_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, payment: Payment) -> "PaymentOut":
        return cls(
            id=payment.id,
            order_id=payment.order_id,
            status=payment.status,
            amount=payment.amount,
            currency=payment.currency,
            card_last4=payment.card_last4,
            failure_reason=payment.failure_reason,
            refunded_at=payment.refunded_at,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )


class ProblemOut(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str
    request_id: str | None = None
