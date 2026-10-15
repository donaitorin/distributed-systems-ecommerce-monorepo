from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel

from catalog.domain.csv_import import ImportableRow, Problem
from catalog.domain.imports import (
    CategoryRef,
    ExistingProduct,
    ImportRecord,
    ImportStatus,
    ImportSummary,
    NewImport,
    Progress,
    StoredProblem,
)
from catalog.domain.listing import (
    PageRequest,
    ProductFilters,
    SearchResult,
    Sort,
    TextMode,
    Total,
)
from catalog.domain.product import Category, NewProduct, Product, ProductData


@dataclass(frozen=True, slots=True)
class ImageRenditions:
    thumbnail: bytes
    full: bytes


class ImageProcessor(Protocol):
    def render(self, data: bytes) -> ImageRenditions: ...


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

    async def set_image(self, sku: str, image_key: str | None, now: datetime) -> Product: ...

    async def existing(self, skus: Sequence[str]) -> Mapping[str, ExistingProduct]: ...

    async def upsert_many(self, rows: Sequence[ImportableRow], now: datetime) -> Progress: ...


class CategoryRepository(Protocol):
    async def list_all(self) -> list[Category]: ...

    async def get(self, category_id: UUID) -> Category | None: ...

    async def add(self, name: str, slug: str) -> Category: ...


class ImportRepository(Protocol):
    async def add(self, new: NewImport, now: datetime) -> ImportRecord: ...

    async def get(self, import_id: UUID) -> ImportRecord | None: ...

    async def get_for_update(self, import_id: UUID) -> ImportRecord | None: ...

    async def find_by_hash(self, sha256: str) -> ImportRecord | None: ...

    async def transition(
        self,
        import_id: UUID,
        expected: Collection[ImportStatus],
        status: ImportStatus,
        now: datetime,
        failure_reason: str | None = None,
    ) -> bool: ...

    async def save_validation(
        self,
        import_id: UUID,
        status: ImportStatus,
        summary: ImportSummary,
        problems: Sequence[Problem],
        snapshot: Sequence[CategoryRef],
        now: datetime,
    ) -> bool: ...

    async def category_snapshot(self, import_id: UUID) -> list[CategoryRef]: ...

    async def problems(
        self, import_id: UUID, severity: str | None, after_id: int | None, limit: int
    ) -> list[StoredProblem]: ...

    async def record_progress(self, import_id: UUID, progress: Progress, now: datetime) -> None: ...


class EventOutbox(Protocol):
    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None: ...


class UnitOfWork(Protocol):
    @property
    def products(self) -> ProductRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    @property
    def imports(self) -> ImportRepository: ...

    @property
    def events(self) -> EventOutbox: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
