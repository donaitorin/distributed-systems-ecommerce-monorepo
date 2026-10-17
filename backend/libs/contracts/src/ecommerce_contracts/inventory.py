from decimal import Decimal
from typing import Final
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ecommerce_contracts.lines import require_unique_skus

INVENTORY_TOPIC: Final = "inventory.events"
STOCK_RESERVED: Final = "stock.reserved"
STOCK_RESERVATION_FAILED: Final = "stock.reservation_failed"
STOCK_RELEASED: Final = "stock.released"

INSUFFICIENT_STOCK: Final = "insufficient_stock"
PRODUCT_UNAVAILABLE: Final = "product_unavailable"
PRICE_CHANGED: Final = "price_changed"


class ReservedLineV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ReleasedLineV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class StockReservedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    lines: list[ReservedLineV1] = Field(min_length=1)
    occurred_at: AwareDatetime

    @field_validator("lines")
    @classmethod
    def reject_duplicate_skus(cls, lines: list[ReservedLineV1]) -> list[ReservedLineV1]:
        return require_unique_skus(lines)


class StockReservationFailedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    reason: str = Field(min_length=1)
    sku: str | None = None
    available: int | None = Field(default=None, ge=0)
    current_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    occurred_at: AwareDatetime


class StockReleasedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: UUID
    lines: list[ReleasedLineV1] = Field(min_length=1)
    occurred_at: AwareDatetime
