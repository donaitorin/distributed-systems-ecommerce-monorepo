from decimal import Decimal
from typing import Final
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ecommerce_contracts.orders import CURRENCY_PATTERN

PAYMENTS_TOPIC: Final = "payments.events"
PAYMENT_SUCCEEDED: Final = "payment.succeeded"
PAYMENT_FAILED: Final = "payment.failed"
PAYMENT_REFUNDED: Final = "payment.refunded"


class PaymentSucceededV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    payment_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    occurred_at: AwareDatetime


class PaymentFailedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    payment_id: UUID
    reason: str = Field(min_length=1)
    occurred_at: AwareDatetime


class PaymentRefundedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    payment_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    reason: str = Field(min_length=1)
    occurred_at: AwareDatetime
