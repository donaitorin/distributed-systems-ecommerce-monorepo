import re
from dataclasses import dataclass
from decimal import Decimal

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")


def normalize_sku(raw: str) -> str | None:
    candidate = raw.strip().upper()
    return candidate if SKU_PATTERN.match(candidate) else None


@dataclass(frozen=True, slots=True)
class ProductState:
    sku: str
    name: str
    price: Decimal
    stock: int
    version: int
    deleted: bool
    image_key: str | None
