from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from catalog.application.ports import UnitOfWorkFactory
from catalog.application.products import ProductService
from catalog.domain.listing import ProductFilters, ProductListing, Sort
from catalog.domain.product import NewProduct, Product, ProductData

BASE = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
PRICES = [
    Decimal(value) for value in ("10.00", "20.00", "20.00", "35.50", "5.25", "20.00", "99.99")
]
SORTS = [Sort.NEWEST, Sort.PRICE_ASC, Sort.PRICE_DESC]


class Catalog:
    def __init__(self, unit_of_work: UnitOfWorkFactory, slug: str) -> None:
        self.unit_of_work = unit_of_work
        self.slug = slug
        self.service = ProductService(unit_of_work)
        self.products: list[Product] = []

    @property
    def filters(self) -> ProductFilters:
        return ProductFilters(category=self.slug)

    async def add(
        self, name: str, description: str | None, price: Decimal, stock: int, tick: int
    ) -> Product:
        async with self.unit_of_work() as uow:
            categories = await uow.categories.list_all()
            category_id = next(item.id for item in categories if item.slug == self.slug)
            data = ProductData(name, description, category_id, price, stock, None)
            product = await uow.products.add(
                NewProduct(f"L{uuid4().hex[:12].upper()}", data), BASE + timedelta(minutes=tick)
            )
            await uow.commit()
        self.products.append(product)
        return product

    async def walk(
        self, sort: Sort | None, limit: int, filters: ProductFilters | None = None
    ) -> list[ProductListing]:
        pages: list[ProductListing] = []
        cursor: str | None = None
        while True:
            page = await self.service.search(filters or self.filters, sort, limit, cursor)
            pages.append(page)
            if page.next_cursor is None:
                return pages
            cursor = page.next_cursor

    async def walk_back(
        self,
        last_page: ProductListing,
        sort: Sort | None,
        limit: int,
        filters: ProductFilters | None = None,
    ) -> list[ProductListing]:
        pages = [last_page]
        while pages[-1].prev_cursor is not None:
            pages.append(
                await self.service.search(
                    filters or self.filters, sort, limit, pages[-1].prev_cursor
                )
            )
        return pages


async def fill_with_ties(catalog: Catalog, count: int = 53) -> None:
    for index in range(count):
        await catalog.add(
            f"Item {index}",
            None,
            PRICES[index % len(PRICES)],
            0 if index % 4 == 0 else index,
            tick=index % 9,
        )


async def create_catalog(unit_of_work: UnitOfWorkFactory) -> Catalog:
    slug = f"listing-{uuid4().hex[:10]}"
    async with unit_of_work() as uow:
        await uow.categories.add(f"Listing {slug}", slug)
        await uow.commit()
    return Catalog(unit_of_work, slug)
