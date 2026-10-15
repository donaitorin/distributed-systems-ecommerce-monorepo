from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from catalog.application.cursors import decode_cursor, encode_cursor
from catalog.application.errors import PreconditionFailedError, ProductNotFoundError
from catalog.application.ports import UnitOfWork, UnitOfWorkFactory
from catalog.domain.errors import ValidationFailedError, Violation
from catalog.domain.listing import (
    Direction,
    ListedProduct,
    PageRequest,
    ProductFilters,
    ProductListing,
    Sort,
    resolve_sort,
)
from catalog.domain.preconditions import VersionPrecondition
from catalog.domain.product import (
    Product,
    build_new_product,
    build_product_data,
    normalize_sku,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class ProductService:
    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def create(
        self,
        sku: str,
        name: str,
        description: str | None,
        category_id: UUID | None,
        price: Decimal,
        stock: int,
        weight_kg: Decimal | None,
    ) -> Product:
        new_product = build_new_product(
            sku, name, description, category_id, price, stock, weight_kg
        )
        async with self._unit_of_work() as uow:
            await _require_known_category(uow, new_product.data.category_id)
            product = await uow.products.add(new_product, self._clock())
            await uow.commit()
        return product

    async def get(self, sku: str) -> Product:
        normalized = normalize_sku(sku)
        if normalized is None:
            raise ProductNotFoundError(sku)
        async with self._unit_of_work() as uow:
            product = await uow.products.get(normalized)
        if product is None:
            raise ProductNotFoundError(normalized)
        return product

    async def search(
        self, filters: ProductFilters, sort: Sort | None, limit: int, cursor: str | None
    ) -> ProductListing:
        effective_sort = resolve_sort(sort, filters)
        fingerprint = filters.fingerprint(effective_sort)
        page = PageRequest(limit)
        if cursor is not None:
            decoded = decode_cursor(cursor, effective_sort, fingerprint)
            page = PageRequest(limit, decoded.direction, decoded.position, decoded.mode)
        async with self._unit_of_work() as uow:
            result = await uow.products.search(filters, effective_sort, page)
            total = await uow.products.count(filters, result.mode)
        has_more = len(result.rows) > limit
        rows = result.rows[:limit]
        going_back = page.direction is Direction.BEFORE
        if going_back:
            rows.reverse()

        def cursor_at(row: ListedProduct, direction: Direction) -> str:
            position = row.position(effective_sort)
            return encode_cursor(direction, effective_sort, fingerprint, position, result.mode)

        has_previous = has_more if going_back else cursor is not None
        has_next = going_back or has_more
        return ProductListing(
            items=[row.product for row in rows],
            next_cursor=cursor_at(rows[-1], Direction.AFTER) if rows and has_next else None,
            prev_cursor=cursor_at(rows[0], Direction.BEFORE) if rows and has_previous else None,
            total=total,
        )

    async def replace(
        self,
        sku: str,
        name: str,
        description: str | None,
        category_id: UUID | None,
        price: Decimal,
        stock: int,
        weight_kg: Decimal | None,
        precondition: VersionPrecondition,
    ) -> Product:
        data = build_product_data(name, description, category_id, price, stock, weight_kg)
        normalized = _require_sku(sku)
        async with self._unit_of_work() as uow:
            await _lock_and_check(uow, normalized, precondition)
            await _require_known_category(uow, data.category_id)
            product = await uow.products.replace(normalized, data, self._clock())
            await uow.commit()
        return product

    async def delete(self, sku: str, precondition: VersionPrecondition) -> None:
        normalized = _require_sku(sku)
        async with self._unit_of_work() as uow:
            await _lock_and_check(uow, normalized, precondition)
            await uow.products.soft_delete(normalized, self._clock())
            await uow.commit()


def _require_sku(raw: str) -> str:
    normalized = normalize_sku(raw)
    if normalized is None:
        raise ProductNotFoundError(raw)
    return normalized


async def _lock_and_check(uow: UnitOfWork, sku: str, precondition: VersionPrecondition) -> Product:
    current = await uow.products.get_for_update(sku)
    if current is None:
        raise ProductNotFoundError(sku)
    if not precondition.satisfied_by(current.version):
        raise PreconditionFailedError(sku)
    return current


async def _require_known_category(uow: UnitOfWork, category_id: UUID | None) -> None:
    if category_id is None:
        return
    if await uow.categories.get(category_id) is None:
        raise ValidationFailedError(
            [Violation("category_id", "does not match any category", "unknown_category")]
        )
