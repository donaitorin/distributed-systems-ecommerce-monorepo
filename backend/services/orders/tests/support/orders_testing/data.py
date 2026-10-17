from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from orders.domain.order import LineRequest, OrderRequest, ShippingAddress

START = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)
CUSTOMER = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CUSTOMER = UUID("22222222-2222-4222-8222-222222222222")
CARD_NUMBER = "4929 1234 5678 1111"
CARD_DIGITS = "4929123456781111"

ADDRESS: dict[str, Any] = {
    "recipient_name": "Ada Lovelace",
    "line1": "12 Analytical St",
    "line2": "Floor 2",
    "city": "London",
    "region": "Greater London",
    "postal_code": "N1 9GU",
    "country": "GB",
    "phone": "+442071234567",
}


class SteppingClock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float = 0, days: float = 0) -> None:
        self.now += timedelta(seconds=seconds, days=days)


def order_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "lines": [
            {"sku": "RS-001", "quantity": 2, "unit_price": "39.90"},
            {"sku": "XS-001", "quantity": 1, "unit_price": "12.50"},
        ],
        "shipping_address": dict(ADDRESS),
        "payment": {"card_number": CARD_NUMBER},
    }
    return body | overrides


def order_request(
    lines: list[tuple[str, int, str]] | None = None, card_last4: str = "1111"
) -> OrderRequest:
    chosen = lines or [("RS-001", 2, "39.90"), ("XS-001", 1, "12.50")]
    return OrderRequest(
        tuple(LineRequest(sku, quantity, Decimal(price)) for sku, quantity, price in chosen),
        ShippingAddress(**ADDRESS),
        card_last4,
    )
