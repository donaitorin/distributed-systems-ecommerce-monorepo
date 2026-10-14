from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from catalog.application.errors import PreconditionFailedError, ProductNotFoundError
from catalog.application.ports import UnitOfWork, UnitOfWorkFactory
from catalog.domain.errors import ValidationFailedError, Violation
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

    async def list(self, limit: int) -> list[Product]:
        async with self._unit_of_work() as uow:
            return await uow.products.list(limit)

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
