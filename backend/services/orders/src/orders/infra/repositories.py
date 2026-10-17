from collections.abc import Collection, Mapping
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from orders.domain.idempotency import IdempotencyRecord
from orders.domain.listing import OrderFilters, Position
from orders.domain.order import (
    HistoryEntry,
    NewOrder,
    Order,
    OrderLine,
    OrderSummary,
    ShippingAddress,
)
from orders.domain.status import ORDER_CREATED_REASON, OrderStatus
from orders.infra.models import (
    IdempotencyKeyModel,
    OrderLineModel,
    OrderModel,
    OrderStatusHistoryModel,
)


def to_summary(model: OrderModel, item_count: int) -> OrderSummary:
    return OrderSummary(
        id=model.id,
        customer_id=model.customer_id,
        status=OrderStatus(model.status),
        total=model.total,
        currency=model.currency,
        item_count=item_count,
        created_at=model.created_at,
        updated_at=model.updated_at,
        customer_email=model.customer_email,
    )


class SqlOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: NewOrder, total: Decimal, now: datetime) -> None:
        request = order.request
        await self._session.execute(
            insert(OrderModel).values(
                id=order.id,
                customer_id=order.customer_id,
                customer_email=order.customer_email,
                status=OrderStatus.PENDING.value,
                total=total,
                currency="USD",
                card_last4=request.card_last4,
                shipping_address=asdict(request.shipping_address),
                correlation_id=order.correlation_id,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.execute(
            insert(OrderLineModel),
            [
                {
                    "order_id": order.id,
                    "sku": line.sku,
                    "position": position,
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                }
                for position, line in enumerate(request.lines)
            ],
        )
        await self._record(order.id, None, OrderStatus.PENDING, ORDER_CREATED_REASON, now)

    async def get(self, order_id: UUID) -> Order | None:
        model = await self._session.get(OrderModel, order_id, populate_existing=True)
        if model is None:
            return None
        lines = (
            await self._session.execute(
                select(OrderLineModel)
                .where(OrderLineModel.order_id == order_id)
                .order_by(OrderLineModel.position)
                .execution_options(populate_existing=True)
            )
        ).scalars()
        history = (
            await self._session.execute(
                select(OrderStatusHistoryModel)
                .where(OrderStatusHistoryModel.order_id == order_id)
                .order_by(OrderStatusHistoryModel.id)
            )
        ).scalars()
        return Order(
            id=model.id,
            customer_id=model.customer_id,
            status=OrderStatus(model.status),
            total=model.total,
            currency=model.currency,
            card_last4=model.card_last4,
            shipping_address=ShippingAddress(**model.shipping_address),
            correlation_id=model.correlation_id,
            cancel_reason=model.cancel_reason,
            refunded_at=model.refunded_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
            customer_email=model.customer_email,
            lines=tuple(
                OrderLine(item.position, item.sku, item.name, item.quantity, item.unit_price)
                for item in lines
            ),
            history=tuple(
                HistoryEntry(
                    OrderStatus(item.from_status) if item.from_status else None,
                    OrderStatus(item.to_status),
                    item.reason,
                    item.at,
                )
                for item in history
            ),
        )

    async def transition(
        self,
        order_id: UUID,
        expected: Collection[OrderStatus],
        target: OrderStatus,
        now: datetime,
        reason: str,
    ) -> bool:
        current = await self._session.scalar(
            select(OrderModel.status).where(OrderModel.id == order_id).with_for_update()
        )
        if current is None or OrderStatus(current) not in expected:
            return False
        values: dict[str, Any] = {"status": target.value, "updated_at": now}
        if target is OrderStatus.CANCELLED:
            values["cancel_reason"] = reason
        updated = await self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.status == current)
            .values(**values)
            .returning(OrderModel.id)
        )
        if updated.scalar_one_or_none() is None:
            return False
        await self._record(order_id, OrderStatus(current), target, reason, now)
        return True

    async def name_lines(self, order_id: UUID, names: Mapping[str, str]) -> None:
        for sku, name in names.items():
            await self._session.execute(
                update(OrderLineModel)
                .where(OrderLineModel.order_id == order_id, OrderLineModel.sku == sku)
                .values(name=name)
            )

    async def mark_refunded(self, order_id: UUID, now: datetime, reason: str) -> bool:
        updated = await self._session.execute(
            update(OrderModel)
            .where(
                OrderModel.id == order_id,
                OrderModel.status == OrderStatus.CANCELLED.value,
                OrderModel.refunded_at.is_(None),
            )
            .values(refunded_at=now, updated_at=now)
            .returning(OrderModel.id)
        )
        if updated.scalar_one_or_none() is None:
            return False
        await self._record(order_id, OrderStatus.CANCELLED, OrderStatus.CANCELLED, reason, now)
        return True

    async def list_page(
        self,
        customer_id: UUID | None,
        filters: OrderFilters,
        after: Position | None,
        limit: int,
    ) -> list[OrderSummary]:
        item_count = (
            select(func.coalesce(func.sum(OrderLineModel.quantity), 0))
            .where(OrderLineModel.order_id == OrderModel.id)
            .scalar_subquery()
        )
        statement = select(OrderModel, item_count)
        if customer_id is not None:
            statement = statement.where(OrderModel.customer_id == customer_id)
        if filters.status is not None:
            statement = statement.where(OrderModel.status == filters.status.value)
        if filters.created_from is not None:
            statement = statement.where(OrderModel.created_at >= filters.created_from)
        if filters.created_to is not None:
            statement = statement.where(OrderModel.created_at < filters.created_to)
        if after is not None:
            statement = statement.where(
                or_(
                    OrderModel.created_at < after.created_at,
                    and_(OrderModel.created_at == after.created_at, OrderModel.id < after.order_id),
                )
            )
        statement = statement.order_by(OrderModel.created_at.desc(), OrderModel.id.desc()).limit(
            limit + 1
        )
        rows = (await self._session.execute(statement)).all()
        return [to_summary(model, int(count)) for model, count in rows]

    async def lock_expired(self, created_before: datetime, limit: int) -> list[UUID]:
        statement = (
            select(OrderModel.id)
            .where(
                OrderModel.status.in_(
                    [OrderStatus.PENDING.value, OrderStatus.STOCK_RESERVED.value]
                ),
                OrderModel.created_at <= created_before,
            )
            .order_by(OrderModel.created_at, OrderModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self._session.execute(statement)).scalars())

    async def _record(
        self,
        order_id: UUID,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        reason: str,
        now: datetime,
    ) -> None:
        await self._session.execute(
            insert(OrderStatusHistoryModel).values(
                order_id=order_id,
                from_status=from_status.value if from_status else None,
                to_status=to_status.value,
                reason=reason,
                at=now,
            )
        )


class SqlIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim(self, record: IdempotencyRecord, now: datetime) -> IdempotencyRecord | None:
        values = {
            "user_id": record.user_id,
            "key": record.key,
            "fingerprint": record.fingerprint,
            "order_id": record.order_id,
            "response_status": record.response_status,
            "response_body": record.response_body,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
        }
        insertion = pg_insert(IdempotencyKeyModel).values(values)
        statement = insertion.on_conflict_do_update(
            index_elements=[IdempotencyKeyModel.user_id, IdempotencyKeyModel.key],
            set_={name: getattr(insertion.excluded, name) for name in values if name != "user_id"},
            where=IdempotencyKeyModel.expires_at <= now,
        ).returning(IdempotencyKeyModel.key)
        if (await self._session.execute(statement)).scalar_one_or_none() is not None:
            return None
        existing = await self._session.scalar(
            select(IdempotencyKeyModel)
            .where(
                IdempotencyKeyModel.user_id == record.user_id,
                IdempotencyKeyModel.key == record.key,
            )
            .execution_options(populate_existing=True)
        )
        assert existing is not None
        return IdempotencyRecord(
            existing.user_id,
            existing.key,
            existing.fingerprint,
            existing.order_id,
            existing.response_status,
            existing.response_body,
            existing.created_at,
            existing.expires_at,
        )

    async def purge_expired(self, now: datetime) -> int:
        result = await self._session.execute(
            delete(IdempotencyKeyModel).where(IdempotencyKeyModel.expires_at <= now)
        )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]
