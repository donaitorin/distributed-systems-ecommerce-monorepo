import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from catalog.application.errors import (
    DuplicateCategoryError,
    DuplicateSkuError,
    ProductNotFoundError,
    UnknownCategoryError,
)
from catalog.domain.csv_import import ImportableRow
from catalog.domain.imports import (
    ChangedProduct,
    ExistingProduct,
    Progress,
    UpsertResult,
    classify,
)
from catalog.domain.listing import (
    Direction,
    ListedProduct,
    PageRequest,
    ProductFilters,
    SearchResult,
    Sort,
    SortKey,
    TextMode,
    Total,
)
from catalog.domain.product import Category, NewProduct, Product, ProductData
from catalog.domain.reservation import (
    AlreadyHandled,
    Rejected,
    ReleasedItem,
    ReservationLine,
    ReservationStatus,
    Reserved,
    ReservedItem,
    ReserveResult,
    diagnose,
)
from catalog.infra.memory_imports import (
    ImportData,
    InMemoryEventOutbox,
    InMemoryImportRepository,
    empty_import_data,
)


@dataclass(slots=True)
class StoredProduct:
    id: UUID
    sku: str
    name: str
    description: str | None
    category_id: UUID | None
    price: Decimal
    stock: int
    weight_kg: Decimal | None
    version: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    image_key: str | None = None


@dataclass(slots=True)
class StoredReservation:
    status: ReservationStatus
    lines: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class InMemoryStore:
    products: dict[str, StoredProduct] = field(default_factory=dict)
    reservations: dict[UUID, StoredReservation] = field(default_factory=dict)
    categories: dict[UUID, Category] = field(default_factory=dict)
    import_data: ImportData = field(default_factory=empty_import_data)

    def seed_categories(self, *names_and_slugs: tuple[str, str]) -> list[Category]:
        created = [Category(uuid4(), name, slug) for name, slug in names_and_slugs]
        self.categories.update({category.id: category for category in created})
        return created


def _matches(item: StoredProduct, filters: ProductFilters, categories: dict[UUID, str]) -> bool:
    if filters.query is not None and _score(item, filters) is None:
        return False
    if filters.category is not None and (
        item.category_id is None or categories.get(item.category_id) != filters.category
    ):
        return False
    if filters.min_price is not None and item.price < filters.min_price:
        return False
    if filters.max_price is not None and item.price > filters.max_price:
        return False
    return not (filters.in_stock and item.stock <= 0)


def _category_slug(item: StoredProduct, categories: dict[UUID, str]) -> str | None:
    return categories.get(item.category_id) if item.category_id is not None else None


def _score(item: StoredProduct, filters: ProductFilters) -> float | None:
    if filters.query is None:
        return None
    terms = filters.query.lower().split()
    haystack = f"{item.name} {item.sku} {item.description or ''}".lower()
    if not all(term in haystack for term in terms):
        return None
    in_name = sum(term in item.name.lower() for term in terms)
    return 1.0 + in_name / len(terms) - len(item.name) / 10_000


def _order_key(row: ListedProduct, sort: Sort) -> tuple[SortKey, UUID]:
    position = row.position(sort)
    return position.key, position.id


def _changed(stored: StoredProduct) -> ChangedProduct:
    return ChangedProduct(
        stored.sku, stored.name, stored.price, stored.stock, stored.image_key, stored.version
    )


class InMemoryProductRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get(self, sku: str) -> Product | None:
        stored = self._active(sku)
        return self._to_product(stored) if stored else None

    async def get_for_update(self, sku: str) -> Product | None:
        return await self.get(sku)

    async def search(self, filters: ProductFilters, sort: Sort, page: PageRequest) -> SearchResult:
        listed = [
            ListedProduct(self._to_product(item), _score(item, filters))
            for item in self._matching(filters)
        ]
        descending = sort is not Sort.PRICE_ASC
        ordered_descending = descending if page.direction is Direction.AFTER else not descending
        ordered = sorted(listed, key=lambda row: _order_key(row, sort), reverse=ordered_descending)
        if page.position is not None:
            boundary = (page.position.key, page.position.id)
            ordered = [
                row
                for row in ordered
                if (
                    _order_key(row, sort) < boundary
                    if ordered_descending
                    else _order_key(row, sort) > boundary
                )
            ]
        mode = TextMode.FULL_TEXT if filters.query is not None else None
        return SearchResult(ordered[: page.limit + 1], mode)

    async def count(self, filters: ProductFilters, mode: TextMode | None) -> Total:
        return Total(len(self._matching(filters)), exact=True)

    def _matching(self, filters: ProductFilters) -> list[StoredProduct]:
        categories = {item.id: item.slug for item in self._store.categories.values()}
        return [
            item
            for item in self._store.products.values()
            if item.deleted_at is None and _matches(item, filters, categories)
        ]

    async def add(self, new_product: NewProduct, now: datetime) -> Product:
        if new_product.sku in self._store.products:
            raise DuplicateSkuError(new_product.sku)
        data = new_product.data
        self._require_category(data.category_id)
        stored = StoredProduct(
            id=uuid4(),
            sku=new_product.sku,
            name=data.name,
            description=data.description,
            category_id=data.category_id,
            price=data.price,
            stock=data.stock,
            weight_kg=data.weight_kg,
            version=1,
            created_at=now,
            updated_at=now,
        )
        self._store.products[stored.sku] = stored
        return self._to_product(stored)

    async def replace(self, sku: str, data: ProductData, now: datetime) -> Product:
        stored = self._active(sku)
        if stored is None:
            raise ProductNotFoundError(sku)
        self._require_category(data.category_id)
        stored.name = data.name
        stored.description = data.description
        stored.category_id = data.category_id
        stored.price = data.price
        stored.stock = data.stock
        stored.weight_kg = data.weight_kg
        stored.version += 1
        stored.updated_at = now
        return self._to_product(stored)

    async def soft_delete(self, sku: str, now: datetime) -> int:
        stored = self._active(sku)
        if stored is None:
            raise ProductNotFoundError(sku)
        stored.deleted_at = now
        stored.updated_at = now
        stored.version += 1
        return stored.version

    async def upsert_many(self, rows: Sequence[ImportableRow], now: datetime) -> UpsertResult:
        existing = await self.existing([row.product.sku for row in rows])
        created, updated, restored, unchanged = classify(rows, existing)
        changed: list[ChangedProduct] = []
        for row in rows:
            data = row.product.data
            stored = self._store.products.get(row.product.sku)
            if stored is None:
                self._store.products[row.product.sku] = StoredProduct(
                    id=uuid4(),
                    sku=row.product.sku,
                    name=data.name,
                    description=data.description,
                    category_id=data.category_id,
                    price=data.price,
                    stock=data.stock,
                    weight_kg=data.weight_kg,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                stored = self._store.products[row.product.sku]
                changed.append(_changed(stored))
            elif stored.deleted_at is not None or existing[row.product.sku].data != data:
                stored.name = data.name
                stored.description = data.description
                stored.category_id = data.category_id
                stored.price = data.price
                stored.stock = data.stock
                stored.weight_kg = data.weight_kg
                stored.version += 1
                stored.updated_at = now
                stored.deleted_at = None
                changed.append(_changed(stored))
        progress = Progress(len(rows), created, updated, restored, unchanged)
        return UpsertResult(progress, tuple(changed))

    async def existing(self, skus: Sequence[str]) -> Mapping[str, ExistingProduct]:
        found: dict[str, ExistingProduct] = {}
        for sku in skus:
            stored = self._store.products.get(sku)
            if stored is not None:
                found[sku] = ExistingProduct(
                    deleted=stored.deleted_at is not None,
                    data=ProductData(
                        stored.name,
                        stored.description,
                        stored.category_id,
                        stored.price,
                        stored.stock,
                        stored.weight_kg,
                    ),
                )
        return found

    async def set_image(self, sku: str, image_key: str | None, now: datetime) -> Product:
        stored = self._active(sku)
        if stored is None:
            raise ProductNotFoundError(sku)
        stored.image_key = image_key
        stored.version += 1
        stored.updated_at = now
        return self._to_product(stored)

    def _require_category(self, category_id: UUID | None) -> None:
        if category_id is not None and category_id not in self._store.categories:
            raise UnknownCategoryError("category does not exist")

    def _active(self, sku: str) -> StoredProduct | None:
        stored = self._store.products.get(sku)
        return stored if stored is not None and stored.deleted_at is None else None

    def _to_product(self, stored: StoredProduct) -> Product:
        category = self._store.categories.get(stored.category_id) if stored.category_id else None
        return Product(
            id=stored.id,
            sku=stored.sku,
            name=stored.name,
            description=stored.description,
            category=category,
            price=stored.price,
            stock=stored.stock,
            weight_kg=stored.weight_kg,
            image_key=stored.image_key,
            version=stored.version,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )


class InMemoryCategoryRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def list_all(self) -> list[Category]:
        return sorted(self._store.categories.values(), key=lambda item: item.name.lower())

    async def get(self, category_id: UUID) -> Category | None:
        return self._store.categories.get(category_id)

    async def add(self, name: str, slug: str) -> Category:
        for existing in self._store.categories.values():
            if existing.name.lower() == name.lower() or existing.slug == slug:
                raise DuplicateCategoryError(name)
        category = Category(uuid4(), name, slug)
        self._store.categories[category.id] = category
        return category


class InMemoryStockReservationRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def reserve(
        self, order_id: UUID, lines: tuple[ReservationLine, ...], now: datetime
    ) -> ReserveResult:
        if order_id in self._store.reservations:
            return AlreadyHandled()
        ordered = sorted(lines, key=lambda line: line.sku)
        for line in ordered:
            stored = self._store.products.get(line.sku)
            usable = stored is not None and stored.deleted_at is None
            available = stored.stock if usable and stored is not None else None
            price = stored.price if usable and stored is not None else None
            if price != line.expected_price or available is None or available < line.quantity:
                self._store.reservations[order_id] = StoredReservation(ReservationStatus.FAILED)
                return Rejected(diagnose(line, price, available))
        items: list[ReservedItem] = []
        for line in ordered:
            stored = self._store.products[line.sku]
            stored.stock -= line.quantity
            stored.version += 1
            stored.updated_at = now
            items.append(ReservedItem(_changed(stored), line.quantity))
        self._store.reservations[order_id] = StoredReservation(
            ReservationStatus.RESERVED, {line.sku: line.quantity for line in ordered}
        )
        return Reserved(tuple(items))

    async def release(self, order_id: UUID, now: datetime) -> tuple[ReleasedItem, ...]:
        reservation = self._store.reservations.get(order_id)
        if reservation is None:
            self._store.reservations[order_id] = StoredReservation(ReservationStatus.RELEASED)
            return ()
        if reservation.status is not ReservationStatus.RESERVED:
            return ()
        reservation.status = ReservationStatus.RELEASED
        items: list[ReleasedItem] = []
        for sku, quantity in sorted(reservation.lines.items()):
            stored = self._store.products[sku]
            stored.stock += quantity
            stored.version += 1
            stored.updated_at = now
            items.append(ReleasedItem(_changed(stored), quantity, stored.deleted_at is not None))
        return tuple(items)


class InMemoryUnitOfWork:
    products: InMemoryProductRepository
    reservations: InMemoryStockReservationRepository
    categories: InMemoryCategoryRepository
    imports: InMemoryImportRepository
    events: InMemoryEventOutbox

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._snapshot: InMemoryStore | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._snapshot = copy.deepcopy(self._store)
        self._committed = False
        self.products = InMemoryProductRepository(self._store)
        self.categories = InMemoryCategoryRepository(self._store)
        self.imports = InMemoryImportRepository(self._store.import_data)
        self.reservations = InMemoryStockReservationRepository(self._store)
        self.events = InMemoryEventOutbox(self._store.import_data)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed and self._snapshot is not None:
            self._store.products = self._snapshot.products
            self._store.reservations = self._snapshot.reservations
            self._store.categories = self._snapshot.categories
            self._store.import_data = self._snapshot.import_data

    async def commit(self) -> None:
        self._committed = True
