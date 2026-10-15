from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from catalog.domain.listing import (
    PageRequest,
    ProductFilters,
    SearchResult,
    Sort,
    TextMode,
    Total,
)
from catalog.domain.product import Category, NewProduct, Product, ProductData


class ProductRepository(Protocol):
    async def get(self, sku: str) -> Product | None: ...

    async def get_for_update(self, sku: str) -> Product | None: ...

    async def search(
        self, filters: ProductFilters, sort: Sort, page: PageRequest
    ) -> SearchResult: ...

    async def count(self, filters: ProductFilters, mode: TextMode | None) -> Total: ...

    async def add(self, new_product: NewProduct, now: datetime) -> Product: ...

    async def replace(self, sku: str, data: ProductData, now: datetime) -> Product: ...

    async def soft_delete(self, sku: str, now: datetime) -> None: ...


class CategoryRepository(Protocol):
    async def list_all(self) -> list[Category]: ...

    async def get(self, category_id: UUID) -> Category | None: ...

    async def add(self, name: str, slug: str) -> Category: ...


class UnitOfWork(Protocol):
    @property
    def products(self) -> ProductRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
