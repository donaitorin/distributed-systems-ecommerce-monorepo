from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field
from pydantic.types import StrictInt

from cart.domain.cart import MAX_QUANTITY, CartEntry, CartView, Flag, FlagType
from ecommerce_storage import build_public_url, thumbnail_key

Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ProblemOut(BaseModel):
    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: StrictInt = Field(ge=1, le=MAX_QUANTITY, examples=[2])
    accepted_price: Money | None = Field(
        default=None,
        description=(
            "The price the customer agreed to. When present it must equal the current "
            "catalog price, otherwise the request fails with 409; on success the line "
            "takes the current price and name."
        ),
    )


class FlagOut(BaseModel):
    type: FlagType
    old_price: Decimal | None = Field(default=None, description="Price saved in the cart")
    new_price: Decimal | None = Field(default=None, description="Current catalog price")
    available: int | None = Field(default=None, description="Units in stock")

    @classmethod
    def from_domain(cls, flag: Flag) -> Self:
        return cls(
            type=flag.type,
            old_price=flag.old_price,
            new_price=flag.new_price,
            available=flag.available,
        )


class LineOut(BaseModel):
    sku: str
    name: str
    quantity: int
    price: Decimal = Field(description="Price saved when the line was added or last accepted")
    line_total: Decimal
    thumbnail_url: str | None = Field(description="Public URL of the 400 px image")
    flags: list[FlagOut]

    @classmethod
    def from_domain(cls, entry: CartEntry, media_base_url: str) -> Self:
        line = entry.line
        return cls(
            sku=line.sku,
            name=line.name,
            quantity=line.quantity,
            price=line.price,
            line_total=line.total,
            thumbnail_url=(
                build_public_url(media_base_url, thumbnail_key(line.image_key))
                if line.image_key is not None
                else None
            ),
            flags=[FlagOut.from_domain(flag) for flag in entry.flags],
        )


class CartOut(BaseModel):
    items: list[LineOut]
    item_count: int = Field(description="Total units in the cart")
    subtotal: Decimal = Field(description="Sum of the line totals at the saved prices")

    @classmethod
    def from_domain(cls, view: CartView, media_base_url: str) -> Self:
        return cls(
            items=[LineOut.from_domain(entry, media_base_url) for entry in view.entries],
            item_count=view.item_count,
            subtotal=view.subtotal,
        )
