import copy
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
from catalog.domain.product import Category, NewProduct, Product, ProductData


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


@dataclass(slots=True)
class InMemoryStore:
    products: dict[str, StoredProduct] = field(default_factory=dict)
    categories: dict[UUID, Category] = field(default_factory=dict)

    def seed_categories(self, *names_and_slugs: tuple[str, str]) -> list[Category]:
        created = [Category(uuid4(), name, slug) for name, slug in names_and_slugs]
        self.categories.update({category.id: category for category in created})
        return created


class InMemoryProductRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get(self, sku: str) -> Product | None:
        stored = self._active(sku)
        return self._to_product(stored) if stored else None

    async def get_for_update(self, sku: str) -> Product | None:
        return await self.get(sku)

    async def list(self, limit: int) -> list[Product]:
        active = sorted(
            (item for item in self._store.products.values() if item.deleted_at is None),
            key=lambda item: item.sku,
        )
        return [self._to_product(item) for item in active[:limit]]

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

    async def soft_delete(self, sku: str, now: datetime) -> None:
        stored = self._active(sku)
        if stored is not None:
            stored.deleted_at = now
            stored.updated_at = now
            stored.version += 1

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
            image_key=None,
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


class InMemoryUnitOfWork:
    products: InMemoryProductRepository
    categories: InMemoryCategoryRepository

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._snapshot: InMemoryStore | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._snapshot = copy.deepcopy(self._store)
        self._committed = False
        self.products = InMemoryProductRepository(self._store)
        self.categories = InMemoryCategoryRepository(self._store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed and self._snapshot is not None:
            self._store.products = self._snapshot.products
            self._store.categories = self._snapshot.categories

    async def commit(self) -> None:
        self._committed = True
