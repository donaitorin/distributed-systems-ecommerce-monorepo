import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from catalog.domain.errors import ValidationFailedError, Violation

SKU_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,63}$")
NAME_MAX_LENGTH = 255
DESCRIPTION_MAX_LENGTH = 5000
PRICE_MAX = Decimal("9999999999.99")
WEIGHT_MAX = Decimal("99999.999")
STOCK_MAX = 2_147_483_647
PRICE_STEP = Decimal("0.01")
WEIGHT_STEP = Decimal("0.001")


@dataclass(frozen=True, slots=True)
class Category:
    id: UUID
    name: str
    slug: str


@dataclass(frozen=True, slots=True)
class ProductData:
    name: str
    description: str | None
    category_id: UUID | None
    price: Decimal
    stock: int
    weight_kg: Decimal | None


@dataclass(frozen=True, slots=True)
class NewProduct:
    sku: str
    data: ProductData


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    sku: str
    name: str
    description: str | None
    category: Category | None
    price: Decimal
    stock: int
    weight_kg: Decimal | None
    image_key: str | None
    version: int
    created_at: datetime
    updated_at: datetime


def normalize_sku(raw: str) -> str | None:
    candidate = raw.strip().upper()
    return candidate if SKU_PATTERN.match(candidate) else None


def build_new_product(
    sku: str,
    name: str,
    description: str | None,
    category_id: UUID | None,
    price: Decimal,
    stock: int,
    weight_kg: Decimal | None,
) -> NewProduct:
    violations: list[Violation] = []
    normalized_sku = normalize_sku(sku)
    if normalized_sku is None:
        violations.append(
            Violation(
                "sku",
                "must be 1-64 characters: letters, digits, dot, underscore or hyphen",
                "invalid_sku",
            )
        )
    data = _validate_data(name, description, category_id, price, stock, weight_kg, violations)
    if violations or normalized_sku is None or data is None:
        raise ValidationFailedError(violations)
    return NewProduct(sku=normalized_sku, data=data)


def build_product_data(
    name: str,
    description: str | None,
    category_id: UUID | None,
    price: Decimal,
    stock: int,
    weight_kg: Decimal | None,
) -> ProductData:
    violations: list[Violation] = []
    data = _validate_data(name, description, category_id, price, stock, weight_kg, violations)
    if violations or data is None:
        raise ValidationFailedError(violations)
    return data


def _validate_data(
    name: str,
    description: str | None,
    category_id: UUID | None,
    price: Decimal,
    stock: int,
    weight_kg: Decimal | None,
    violations: list[Violation],
) -> ProductData | None:
    clean_name = name.strip()
    if not clean_name:
        violations.append(Violation("name", "must not be empty", "required"))
    elif len(clean_name) > NAME_MAX_LENGTH:
        violations.append(
            Violation("name", f"must be at most {NAME_MAX_LENGTH} characters", "too_long")
        )

    clean_description = description.strip() if description is not None else None
    if clean_description is not None and len(clean_description) > DESCRIPTION_MAX_LENGTH:
        violations.append(
            Violation(
                "description", f"must be at most {DESCRIPTION_MAX_LENGTH} characters", "too_long"
            )
        )

    clean_price = _validate_decimal("price", price, PRICE_STEP, PRICE_MAX, violations)

    if stock < 0:
        violations.append(Violation("stock", "must not be negative", "negative"))
    elif stock > STOCK_MAX:
        violations.append(Violation("stock", f"must be at most {STOCK_MAX}", "too_large"))

    clean_weight = (
        _validate_decimal("weight_kg", weight_kg, WEIGHT_STEP, WEIGHT_MAX, violations)
        if weight_kg is not None
        else None
    )

    if violations or clean_price is None:
        return None
    return ProductData(
        name=clean_name,
        description=clean_description or None,
        category_id=category_id,
        price=clean_price,
        stock=stock,
        weight_kg=clean_weight,
    )


def _validate_decimal(
    field: str, value: Decimal, step: Decimal, maximum: Decimal, violations: list[Violation]
) -> Decimal | None:
    if not value.is_finite():
        violations.append(Violation(field, "must be a finite number", "not_finite"))
        return None
    if value < 0:
        violations.append(Violation(field, "must not be negative", "negative"))
        return None
    exponent = step.as_tuple().exponent
    if not isinstance(exponent, int) or value != value.quantize(step):
        places = -exponent if isinstance(exponent, int) else 0
        violations.append(
            Violation(field, f"must have at most {places} decimal places", "too_many_decimals")
        )
        return None
    if value > maximum:
        violations.append(Violation(field, f"must be at most {maximum}", "too_large"))
        return None
    return value.quantize(step)
