from decimal import Decimal
from typing import Final
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ecommerce_contracts.lines import require_unique_skus

ORDERS_TOPIC: Final = "orders.events"
ORDER_CREATED: Final = "order.created"
ORDER_PAYMENT_REQUESTED: Final = "order.payment_requested"
ORDER_CONFIRMED: Final = "order.confirmed"
ORDER_CANCELLED: Final = "order.cancelled"

CURRENCY_PATTERN: Final = r"^[A-Z]{3}$"
CARD_LAST4_PATTERN: Final = r"^[0-9]{4}$"


class OrderLineV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class OrderCreatedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    customer_id: UUID
    lines: list[OrderLineV1] = Field(min_length=1)
    occurred_at: AwareDatetime

    @field_validator("lines")
    @classmethod
    def reject_duplicate_skus(cls, lines: list[OrderLineV1]) -> list[OrderLineV1]:
        return require_unique_skus(lines)


class OrderPaymentRequestedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    customer_id: UUID
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    card_last4: str = Field(pattern=CARD_LAST4_PATTERN)
    occurred_at: AwareDatetime


class OrderConfirmedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    customer_id: UUID
    lines: list[OrderLineV1] = Field(min_length=1)
    total: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    occurred_at: AwareDatetime

    @field_validator("lines")
    @classmethod
    def reject_duplicate_skus(cls, lines: list[OrderLineV1]) -> list[OrderLineV1]:
        return require_unique_skus(lines)


class OrderCancelledV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    customer_id: UUID
    reason: str = Field(min_length=1)
    occurred_at: AwareDatetime
