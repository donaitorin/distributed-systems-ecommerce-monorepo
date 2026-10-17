from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Self

from cart.domain.product import ProductState

MAX_QUANTITY: Final = 99
MAX_LINES: Final = 100


class FlagType(StrEnum):
    PRICE_CHANGED = "price_changed"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_STOCK = "insufficient_stock"


@dataclass(frozen=True, slots=True)
class Flag:
    type: FlagType
    old_price: Decimal | None = None
    new_price: Decimal | None = None
    available: int | None = None


@dataclass(frozen=True, slots=True)
class CartLine:
    sku: str
    name: str
    price: Decimal
    quantity: int
    image_key: str | None
    added_at: datetime

    @classmethod
    def started(cls, product: ProductState, quantity: int, added_at: datetime) -> Self:
        return cls(product.sku, product.name, product.price, quantity, product.image_key, added_at)

    def with_quantity(self, quantity: int) -> Self:
        return replace(self, quantity=quantity)

    def with_snapshot_of(self, product: ProductState) -> Self:
        return replace(self, name=product.name, price=product.price, image_key=product.image_key)

    @property
    def total(self) -> Decimal:
        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class CartEntry:
    line: CartLine
    flags: tuple[Flag, ...]


@dataclass(frozen=True, slots=True)
class CartView:
    entries: tuple[CartEntry, ...]

    @property
    def item_count(self) -> int:
        return sum(entry.line.quantity for entry in self.entries)

    @property
    def subtotal(self) -> Decimal:
        return sum((entry.line.total for entry in self.entries), Decimal("0.00"))


def flags_for(line: CartLine, product: ProductState | None) -> tuple[Flag, ...]:
    if product is None:
        return ()
    if product.deleted:
        return (Flag(FlagType.UNAVAILABLE),)
    flags: list[Flag] = []
    if product.price != line.price:
        flags.append(Flag(FlagType.PRICE_CHANGED, old_price=line.price, new_price=product.price))
    if line.quantity > product.stock:
        flags.append(Flag(FlagType.INSUFFICIENT_STOCK, available=product.stock))
    return tuple(flags)
