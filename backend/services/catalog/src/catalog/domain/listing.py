import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from catalog.domain.product import Product

PAGE_SIZES = (12, 24, 48)
DEFAULT_PAGE_SIZE: Final = 24
QUERY_MAX_LENGTH = 100
CATEGORY_MAX_LENGTH = 120
PRICE_STEP = Decimal("0.01")
WHITESPACE = re.compile(r"\s+")


class Sort(StrEnum):
    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NEWEST = "newest"


class TextMode(StrEnum):
    FULL_TEXT = "full_text"
    TRIGRAM = "trigram"


class Direction(StrEnum):
    AFTER = "after"
    BEFORE = "before"


type SortKey = datetime | Decimal | float


@dataclass(frozen=True, slots=True)
class ProductFilters:
    query: str | None = None
    category: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock: bool = False

    def fingerprint(self, sort: Sort) -> str:
        parts = [
            self.query,
            self.category,
            str(self.min_price) if self.min_price is not None else None,
            str(self.max_price) if self.max_price is not None else None,
            self.in_stock,
            sort.value,
        ]
        digest = hashlib.sha256(json.dumps(parts).encode()).hexdigest()
        return digest[:16]


@dataclass(frozen=True, slots=True)
class Position:
    key: SortKey
    id: UUID


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int
    direction: Direction = Direction.AFTER
    position: Position | None = None
    mode: TextMode | None = None


@dataclass(frozen=True, slots=True)
class ListedProduct:
    product: Product
    score: float | None = None

    def position(self, sort: Sort) -> Position:
        match sort:
            case Sort.NEWEST:
                return Position(self.product.created_at, self.product.id)
            case Sort.PRICE_ASC | Sort.PRICE_DESC:
                return Position(self.product.price, self.product.id)
            case Sort.RELEVANCE:
                return Position(self.score or 0.0, self.product.id)


@dataclass(frozen=True, slots=True)
class SearchResult:
    rows: list[ListedProduct]
    mode: TextMode | None


@dataclass(frozen=True, slots=True)
class Total:
    value: int
    exact: bool


@dataclass(frozen=True, slots=True)
class ProductListing:
    items: list[Product]
    next_cursor: str | None
    prev_cursor: str | None
    total: Total


def build_filters(
    query: str | None,
    category: str | None,
    min_price: Decimal | None,
    max_price: Decimal | None,
    in_stock: bool | None,
) -> ProductFilters:
    clean_query = WHITESPACE.sub(" ", query).strip() if query else None
    clean_category = category.strip().lower() if category else None
    return ProductFilters(
        query=clean_query or None,
        category=clean_category or None,
        min_price=min_price.quantize(PRICE_STEP) if min_price is not None else None,
        max_price=max_price.quantize(PRICE_STEP) if max_price is not None else None,
        in_stock=bool(in_stock),
    )


def resolve_sort(requested: Sort | None, filters: ProductFilters) -> Sort:
    has_query = filters.query is not None
    if requested is None or (requested is Sort.RELEVANCE and not has_query):
        return Sort.RELEVANCE if has_query else Sort.NEWEST
    return requested
