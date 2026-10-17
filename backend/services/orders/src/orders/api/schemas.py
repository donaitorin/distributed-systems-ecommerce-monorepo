import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    Field,
    SecretStr,
    StringConstraints,
    field_validator,
)

from orders.application.orders import OrderPage
from orders.domain.order import (
    MONEY_MAX,
    HistoryEntry,
    LineRequest,
    Order,
    OrderLine,
    OrderRequest,
    OrderSummary,
    ShippingAddress,
)
from orders.domain.status import OrderStatus

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
PHONE_SEPARATORS = re.compile(r"[ \-.()]")
PHONE_PATTERN = re.compile(r"\+\d{8,15}")
COUNTRY_PATTERN = re.compile(r"[A-Z]{2}")
CARD_SEPARATORS = re.compile(r"[ -]")
CARD_PATTERN = re.compile(r"\d{12,19}")
MAX_LINES = 50
MAX_QUANTITY = 99
PAGE_SIZES = (25, 50, 100)


def upper_sku(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def check_sku(value: str) -> str:
    if not SKU_PATTERN.fullmatch(value):
        raise ValueError("sku must be 1-64 characters: letters, digits, dot, underscore or hyphen")
    return value


def normalize_phone(value: object) -> object:
    return PHONE_SEPARATORS.sub("", value.strip()) if isinstance(value, str) else value


def check_phone(value: str) -> str:
    if not PHONE_PATTERN.fullmatch(value):
        raise ValueError("phone must start with + and have 8 to 15 digits")
    return value


def upper_country(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def check_country(value: str) -> str:
    if not COUNTRY_PATTERN.fullmatch(value):
        raise ValueError("country must be an ISO 3166-1 alpha-2 code")
    return value


def blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


def require_page_size(value: int) -> int:
    if value not in PAGE_SIZES:
        raise ValueError("limit must be 25, 50 or 100")
    return value


def trimmed(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


PageSize = Annotated[int, AfterValidator(require_page_size)]
SkuField = Annotated[str, BeforeValidator(upper_sku), AfterValidator(check_sku)]
PhoneField = Annotated[str, BeforeValidator(normalize_phone), AfterValidator(check_phone)]
CountryField = Annotated[str, BeforeValidator(upper_country), AfterValidator(check_country)]
OptionalText = Annotated[Annotated[str, trimmed(200)] | None, BeforeValidator(blank_to_none)]


class OrderLineIn(BaseModel):
    sku: SkuField = Field(examples=["RS-001"])
    quantity: int = Field(ge=1, le=MAX_QUANTITY)
    unit_price: Decimal = Field(
        ge=0, max_digits=12, decimal_places=2, description="The price the customer saw"
    )


class ShippingAddressIn(BaseModel):
    recipient_name: Annotated[str, trimmed(100)]
    line1: Annotated[str, trimmed(200)]
    line2: OptionalText = None
    city: Annotated[str, trimmed(100)]
    region: OptionalText = None
    postal_code: Annotated[str, trimmed(20)]
    country: CountryField = Field(examples=["ES"])
    phone: Annotated[PhoneField | None, BeforeValidator(blank_to_none)] = None

    def to_domain(self) -> ShippingAddress:
        return ShippingAddress(**self.model_dump())


class PaymentIn(BaseModel):
    card_number: SecretStr = Field(
        description="Simulated card number. Only the last 4 digits are kept",
        examples=["4111 1111 1111 1111"],
    )

    @field_validator("card_number", mode="after")
    @classmethod
    def check_card_number(cls, value: SecretStr) -> SecretStr:
        digits = CARD_SEPARATORS.sub("", value.get_secret_value())
        if not CARD_PATTERN.fullmatch(digits):
            raise ValueError("card number must have 12 to 19 digits")
        return SecretStr(digits)


class OrderIn(BaseModel):
    lines: Annotated[list[OrderLineIn], Field(min_length=1, max_length=MAX_LINES)]
    shipping_address: ShippingAddressIn
    payment: PaymentIn

    @field_validator("lines")
    @classmethod
    def reject_repeated_skus(cls, lines: list[OrderLineIn]) -> list[OrderLineIn]:
        skus = [line.sku for line in lines]
        if len(set(skus)) != len(skus):
            raise ValueError("each sku can appear only once; raise its quantity instead")
        return lines

    @field_validator("lines")
    @classmethod
    def reject_totals_above_the_limit(cls, lines: list[OrderLineIn]) -> list[OrderLineIn]:
        if sum((line.unit_price * line.quantity for line in lines), Decimal(0)) > MONEY_MAX:
            raise ValueError("the order total is too large")
        return lines

    def to_domain(self) -> OrderRequest:
        return OrderRequest(
            lines=tuple(
                LineRequest(item.sku, item.quantity, item.unit_price) for item in self.lines
            ),
            shipping_address=self.shipping_address.to_domain(),
            card_last4=self.payment.card_number.get_secret_value()[-4:],
        )


class OrderAcceptedOut(BaseModel):
    id: UUID
    status: OrderStatus


class OrderLineOut(BaseModel):
    sku: str
    name: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal

    @classmethod
    def from_domain(cls, line: OrderLine) -> "OrderLineOut":
        return cls(
            sku=line.sku,
            name=line.name,
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.total,
        )


class HistoryEntryOut(BaseModel):
    from_status: OrderStatus | None
    to_status: OrderStatus
    reason: str | None
    at: datetime

    @classmethod
    def from_domain(cls, entry: HistoryEntry) -> "HistoryEntryOut":
        return cls(
            from_status=entry.from_status,
            to_status=entry.to_status,
            reason=entry.reason,
            at=entry.at,
        )


class ShippingAddressOut(BaseModel):
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    phone: str | None


class OrderSummaryOut(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total: Decimal
    currency: str
    item_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, summary: OrderSummary) -> "OrderSummaryOut":
        return cls(
            id=summary.id,
            customer_id=summary.customer_id,
            status=summary.status,
            total=summary.total,
            currency=summary.currency,
            item_count=summary.item_count,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )


class OrderDetailOut(BaseModel):
    id: UUID
    customer_id: UUID
    status: OrderStatus
    total: Decimal
    currency: str
    card_last4: str
    shipping_address: ShippingAddressOut
    cancel_reason: str | None
    refunded_at: datetime | None
    created_at: datetime
    updated_at: datetime
    lines: list[OrderLineOut]
    history: list[HistoryEntryOut]

    @classmethod
    def from_domain(cls, order: Order) -> "OrderDetailOut":
        return cls(
            id=order.id,
            customer_id=order.customer_id,
            status=order.status,
            total=order.total,
            currency=order.currency,
            card_last4=order.card_last4,
            shipping_address=ShippingAddressOut.model_validate(
                order.shipping_address, from_attributes=True
            ),
            cancel_reason=order.cancel_reason,
            refunded_at=order.refunded_at,
            created_at=order.created_at,
            updated_at=order.updated_at,
            lines=[OrderLineOut.from_domain(line) for line in order.lines],
            history=[HistoryEntryOut.from_domain(entry) for entry in order.history],
        )


class OrderPageOut(BaseModel):
    items: list[OrderSummaryOut]
    next_cursor: str | None

    @classmethod
    def from_domain(cls, page: OrderPage) -> "OrderPageOut":
        return cls(
            items=[OrderSummaryOut.from_domain(item) for item in page.items],
            next_cursor=page.next_cursor,
        )


class FieldProblem(BaseModel):
    location: str
    message: str
    type: str


class ProblemOut(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str
    request_id: str | None = None
    errors: list[FieldProblem] | None = None
    code: str | None = None
