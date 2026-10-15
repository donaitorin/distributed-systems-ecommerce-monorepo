import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from catalog.domain.csv_import import problems as codes
from catalog.domain.csv_import.categories import CategoryIndex
from catalog.domain.csv_import.fields import parse_price, parse_stock, parse_weight
from catalog.domain.csv_import.problems import Problem, Severity, error, warning
from catalog.domain.errors import ValidationFailedError
from catalog.domain.product import NewProduct, ProductData, build_new_product, normalize_sku

PLACEHOLDER_SKU = "X"
PLACEHOLDER_PRICE = Decimal("0")
PLACEHOLDER_STOCK = 0


@dataclass(frozen=True, slots=True)
class BlankRow:
    row: int


@dataclass(frozen=True, slots=True)
class InvalidRow:
    row: int
    sku: str | None
    problems: tuple[Problem, ...]
    unknown_category: str | None = None


@dataclass(frozen=True, slots=True)
class ValidRow:
    row: int
    product: NewProduct
    digest: bytes
    warnings: tuple[Problem, ...]


type RowOutcome = BlankRow | InvalidRow | ValidRow


def evaluate_row(
    row: int, record: Sequence[str], columns: Sequence[str], categories: CategoryIndex
) -> RowOutcome:
    if not any(field.strip() for field in record):
        return BlankRow(row)
    if len(record) != len(columns):
        reason = f"expected {len(columns)} fields but found {len(record)}"
        return InvalidRow(row, None, (error(row, None, None, codes.COLUMN_COUNT, reason),))
    fields: Mapping[str, str] = dict(zip(columns, record, strict=True))
    return _evaluate_fields(row, fields, categories)


def _evaluate_fields(row: int, fields: Mapping[str, str], categories: CategoryIndex) -> RowOutcome:
    raw_sku = fields.get("sku", "")
    name = fields.get("name", "")
    description = fields.get("description", "")
    raw_category = fields.get("category", "")
    errors: list[Problem] = []
    warnings: list[Problem] = []

    sku = normalize_sku(raw_sku)
    if not raw_sku.strip():
        errors.append(error(row, "sku", raw_sku, codes.REQUIRED, "sku is required"))
    elif sku is not None and raw_sku.strip() != sku:
        reason = f"read as {sku}"
        warnings.append(warning(row, "sku", raw_sku, codes.SKU_UPPERCASED, reason))

    price = parse_price(fields.get("price", ""), row)
    stock = parse_stock(fields.get("stock", ""), row)
    weight = parse_weight(fields.get("weight_kg", ""), row)
    for parsed in (price, stock, weight):
        errors.extend(item for item in parsed.problems if item.severity is Severity.ERROR)
        warnings.extend(item for item in parsed.problems if item.severity is Severity.WARNING)

    category_id: UUID | None = None
    unknown_category: str | None = None
    if raw_category.strip():
        category_id = categories.resolve(raw_category)
        if category_id is None:
            unknown_category = raw_category
            reason = _unknown_category_reason(raw_category, categories)
            errors.append(error(row, "category", raw_category, codes.UNKNOWN_CATEGORY, reason))

    product = _domain_check(
        row,
        fields,
        errors,
        sku_text=raw_sku if raw_sku.strip() else PLACEHOLDER_SKU,
        price=price.value if price.value is not None else PLACEHOLDER_PRICE,
        stock=stock.value if stock.value is not None else PLACEHOLDER_STOCK,
        weight=weight.value,
        category_id=category_id,
        name=name,
        description=description,
    )
    if errors or product is None:
        return InvalidRow(row, sku, tuple(errors), unknown_category)
    return ValidRow(row, product, _digest(product.data), tuple(warnings))


def _domain_check(
    row: int,
    fields: Mapping[str, str],
    errors: list[Problem],
    *,
    sku_text: str,
    price: Decimal,
    stock: int,
    weight: Decimal | None,
    category_id: UUID | None,
    name: str,
    description: str,
) -> NewProduct | None:
    try:
        return build_new_product(
            sku_text, name, description or None, category_id, price, stock, weight
        )
    except ValidationFailedError as failure:
        for violation in failure.violations:
            errors.append(
                error(
                    row,
                    violation.location,
                    fields.get(violation.location),
                    violation.code,
                    f"{violation.location} {violation.message}",
                )
            )
        return None


def _digest(data: ProductData) -> bytes:
    canonical = "\x1f".join(
        (
            data.name,
            data.description or "",
            str(data.category_id or ""),
            str(data.price),
            str(data.stock),
            str(data.weight_kg) if data.weight_kg is not None else "",
        )
    )
    return hashlib.blake2b(canonical.encode(), digest_size=16).digest()


def _unknown_category_reason(raw: str, categories: CategoryIndex) -> str:
    suggestion = categories.suggest(raw)
    base = "category does not exist and is not created automatically"
    return f"{base}; did you mean {suggestion}?" if suggestion else base
