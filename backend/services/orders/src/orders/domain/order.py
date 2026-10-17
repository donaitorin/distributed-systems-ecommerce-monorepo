from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orders.domain.status import OrderStatus

CURRENCY = "USD"
MONEY_STEP = Decimal("0.01")
MONEY_MAX = Decimal("9999999999.99")


@dataclass(frozen=True, slots=True)
class LineRequest:
    sku: str
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True)
class ShippingAddress:
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    phone: str | None


@dataclass(frozen=True, slots=True)
class OrderRequest:
    lines: tuple[LineRequest, ...]
    shipping_address: ShippingAddress
    card_last4: str

    @property
    def total(self) -> Decimal:
        return sum((line.total for line in self.lines), Decimal("0.00")).quantize(MONEY_STEP)


@dataclass(frozen=True, slots=True)
class NewOrder:
    id: UUID
    customer_id: UUID
    request: OrderRequest
    correlation_id: UUID


@dataclass(frozen=True, slots=True)
class OrderLine:
    position: int
    sku: str
    name: str | None
    quantity: int
    unit_price: Decimal

    @property
    def total(self) -> Decimal:
        return (self.unit_price * self.quantity).quantize(MONEY_STEP)


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    from_status: OrderStatus | None
    to_status: OrderStatus
    reason: str | None
    at: datetime


@dataclass(frozen=True, slots=True)
class Order:
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total: Decimal
    currency: str
    card_last4: str
    shipping_address: ShippingAddress
    correlation_id: UUID
    cancel_reason: str | None
    refunded_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lines: tuple[OrderLine, ...] = field(default_factory=tuple)
    history: tuple[HistoryEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class OrderSummary:
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total: Decimal
    currency: str
    item_count: int
    created_at: datetime
    updated_at: datetime
