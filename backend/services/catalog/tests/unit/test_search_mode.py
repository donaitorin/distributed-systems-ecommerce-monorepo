from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import uuid4

from catalog.application.cursors import decode_cursor
from catalog.application.products import ProductService
from catalog.domain.listing import (
    ListedProduct,
    PageRequest,
    ProductFilters,
    SearchResult,
    Sort,
    TextMode,
    Total,
)
from catalog.domain.product import Product

MOMENT = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def product(sku: str) -> Product:
    return Product(
        id=uuid4(),
        sku=sku,
        name=sku,
        description=None,
        category=None,
        price=Decimal("10.00"),
        stock=1,
        weight_kg=None,
        image_key=None,
        version=1,
        created_at=MOMENT,
        updated_at=MOMENT,
    )


class ScriptedProducts:
    def __init__(self, mode: TextMode | None) -> None:
        self.mode = mode
        self.pages: list[PageRequest] = []
        self.count_modes: list[TextMode | None] = []

    async def search(self, filters: ProductFilters, sort: Sort, page: PageRequest) -> SearchResult:
        self.pages.append(page)
        rows = [ListedProduct(product(f"P-{index}")) for index in range(page.limit + 1)]
        return SearchResult(rows, self.mode)

    async def count(self, filters: ProductFilters, mode: TextMode | None) -> Total:
        self.count_modes.append(mode)
        return Total(0, exact=True)


class ScriptedUnitOfWork:
    def __init__(self, products: ScriptedProducts) -> None:
        self.products = products

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


async def test_the_mode_chosen_on_the_first_page_travels_in_the_cursor_and_is_reused() -> None:
    products = ScriptedProducts(TextMode.TRIGRAM)
    service = ProductService(lambda: ScriptedUnitOfWork(products))  # type: ignore[arg-type, return-value]
    filters = ProductFilters(query="runing shoes")

    first = await service.search(filters, Sort.NEWEST, 2, None)
    assert first.next_cursor is not None
    decoded = decode_cursor(first.next_cursor, Sort.NEWEST, filters.fingerprint(Sort.NEWEST))
    await service.search(filters, Sort.NEWEST, 2, first.next_cursor)

    assert decoded.mode is TextMode.TRIGRAM
    assert [page.mode for page in products.pages] == [None, TextMode.TRIGRAM]
    assert products.count_modes == [TextMode.TRIGRAM, TextMode.TRIGRAM]


async def test_the_previous_cursor_carries_the_mode_too() -> None:
    products = ScriptedProducts(TextMode.FULL_TEXT)
    service = ProductService(lambda: ScriptedUnitOfWork(products))  # type: ignore[arg-type, return-value]
    filters = ProductFilters(query="shoes")
    first = await service.search(filters, Sort.NEWEST, 2, None)
    second = await service.search(filters, Sort.NEWEST, 2, first.next_cursor)

    assert second.prev_cursor is not None
    decoded = decode_cursor(second.prev_cursor, Sort.NEWEST, filters.fingerprint(Sort.NEWEST))

    assert decoded.mode is TextMode.FULL_TEXT


async def test_listings_without_a_query_have_no_mode() -> None:
    products = ScriptedProducts(None)
    service = ProductService(lambda: ScriptedUnitOfWork(products))  # type: ignore[arg-type, return-value]
    filters = ProductFilters()

    first = await service.search(filters, None, 2, None)
    assert first.next_cursor is not None
    decoded = decode_cursor(first.next_cursor, Sort.NEWEST, filters.fingerprint(Sort.NEWEST))

    assert decoded.mode is None
