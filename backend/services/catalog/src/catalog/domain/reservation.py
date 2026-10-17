from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from catalog.domain.imports import ChangedProduct

PRICE_STEP = Decimal("0.01")


class ReservationStatus(StrEnum):
    RESERVED = "RESERVED"
    FAILED = "FAILED"
    RELEASED = "RELEASED"


class FailureReason(StrEnum):
    INSUFFICIENT_STOCK = "insufficient_stock"
    PRODUCT_UNAVAILABLE = "product_unavailable"
    PRICE_CHANGED = "price_changed"


@dataclass(frozen=True, slots=True)
class ReservationLine:
    sku: str
    quantity: int
    expected_price: Decimal

    @classmethod
    def of(cls, sku: str, quantity: int, expected_price: Decimal) -> "ReservationLine":
        return cls(sku, quantity, expected_price.quantize(PRICE_STEP))


@dataclass(frozen=True, slots=True)
class ReservedItem:
    product: ChangedProduct
    quantity: int


@dataclass(frozen=True, slots=True)
class ReleasedItem:
    product: ChangedProduct
    quantity: int
    retired: bool


@dataclass(frozen=True, slots=True)
class ReservationFailure:
    reason: FailureReason
    sku: str
    available: int | None = None
    current_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Reserved:
    items: tuple[ReservedItem, ...]


@dataclass(frozen=True, slots=True)
class Rejected:
    failure: ReservationFailure


@dataclass(frozen=True, slots=True)
class AlreadyHandled:
    pass


type ReserveResult = Reserved | Rejected | AlreadyHandled


def diagnose(
    line: ReservationLine, current_price: Decimal | None, stock: int | None
) -> ReservationFailure:
    if current_price is None or stock is None:
        return ReservationFailure(FailureReason.PRODUCT_UNAVAILABLE, line.sku)
    if current_price != line.expected_price:
        return ReservationFailure(
            FailureReason.PRICE_CHANGED, line.sku, current_price=current_price
        )
    return ReservationFailure(FailureReason.INSUFFICIENT_STOCK, line.sku, available=stock)
