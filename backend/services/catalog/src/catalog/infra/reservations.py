from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from catalog.domain.imports import ChangedProduct
from catalog.domain.reservation import (
    AlreadyHandled,
    Rejected,
    ReleasedItem,
    ReservationFailure,
    ReservationLine,
    ReservationStatus,
    Reserved,
    ReservedItem,
    ReserveResult,
    diagnose,
)
from catalog.infra.models import ProductModel, StockReservationLineModel, StockReservationModel

PRODUCT_COLUMNS = (
    ProductModel.sku,
    ProductModel.name,
    ProductModel.price,
    ProductModel.stock,
    ProductModel.image_key,
    ProductModel.version,
)


class LineRejectedError(Exception):
    def __init__(self, line: ReservationLine) -> None:
        super().__init__(line.sku)
        self.line = line


class SqlStockReservationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self, order_id: UUID, lines: tuple[ReservationLine, ...], now: datetime
    ) -> ReserveResult:
        if not await self._claim(order_id, ReservationStatus.RESERVED, now):
            return AlreadyHandled()
        try:
            async with self._session.begin_nested():
                items = [await self._take(line, now) for line in sorted(lines, key=_by_sku)]
        except LineRejectedError as rejected:
            failure = await self._diagnose(rejected.line)
            await self._finish(order_id, ReservationStatus.FAILED, now, failure.reason.value)
            return Rejected(failure)
        await self._session.execute(
            insert(StockReservationLineModel),
            [
                {"order_id": order_id, "sku": item.product.sku, "quantity": item.quantity}
                for item in items
            ],
        )
        return Reserved(tuple(items))

    async def release(self, order_id: UUID, now: datetime) -> tuple[ReleasedItem, ...]:
        if await self._claim(order_id, ReservationStatus.RELEASED, now):
            return ()
        released = await self._session.execute(
            update(StockReservationModel)
            .where(
                StockReservationModel.order_id == order_id,
                StockReservationModel.status == ReservationStatus.RESERVED.value,
            )
            .values(status=ReservationStatus.RELEASED.value, updated_at=now)
            .returning(StockReservationModel.order_id)
        )
        if released.scalar_one_or_none() is None:
            return ()
        rows = await self._session.execute(
            select(StockReservationLineModel.sku, StockReservationLineModel.quantity)
            .where(StockReservationLineModel.order_id == order_id)
            .order_by(StockReservationLineModel.sku)
        )
        return tuple([await self._give_back(sku, quantity, now) for sku, quantity in rows.all()])

    async def _claim(self, order_id: UUID, status: ReservationStatus, now: datetime) -> bool:
        statement = (
            pg_insert(StockReservationModel)
            .values(order_id=order_id, status=status.value, created_at=now, updated_at=now)
            .on_conflict_do_nothing(index_elements=[StockReservationModel.order_id])
            .returning(StockReservationModel.order_id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def _finish(
        self, order_id: UUID, status: ReservationStatus, now: datetime, reason: str
    ) -> None:
        await self._session.execute(
            update(StockReservationModel)
            .where(StockReservationModel.order_id == order_id)
            .values(status=status.value, failure_reason=reason, updated_at=now)
        )

    async def _take(self, line: ReservationLine, now: datetime) -> ReservedItem:
        statement = (
            update(ProductModel)
            .where(
                ProductModel.sku == line.sku,
                ProductModel.deleted_at.is_(None),
                ProductModel.price == line.expected_price,
                ProductModel.stock >= line.quantity,
            )
            .values(
                stock=ProductModel.stock - line.quantity,
                version=ProductModel.version + 1,
                updated_at=now,
            )
            .returning(*PRODUCT_COLUMNS)
        )
        row = (await self._session.execute(statement)).first()
        if row is None:
            raise LineRejectedError(line)
        return ReservedItem(ChangedProduct(*row), line.quantity)

    async def _give_back(self, sku: str, quantity: int, now: datetime) -> ReleasedItem:
        statement = (
            update(ProductModel)
            .where(ProductModel.sku == sku)
            .values(
                stock=ProductModel.stock + quantity,
                version=ProductModel.version + 1,
                updated_at=now,
            )
            .returning(*PRODUCT_COLUMNS, ProductModel.deleted_at.is_not(None))
        )
        sku_, name, price, stock, image_key, version, retired = (
            await self._session.execute(statement)
        ).one()
        product = ChangedProduct(sku_, name, price, stock, image_key, version)
        return ReleasedItem(product, quantity, bool(retired))

    async def _diagnose(self, line: ReservationLine) -> ReservationFailure:
        row = (
            await self._session.execute(
                select(ProductModel.price, ProductModel.stock, ProductModel.deleted_at).where(
                    ProductModel.sku == line.sku
                )
            )
        ).first()
        if row is None or row.deleted_at is not None:
            return diagnose(line, None, None)
        return diagnose(line, row.price, row.stock)


def _by_sku(line: ReservationLine) -> str:
    return line.sku
