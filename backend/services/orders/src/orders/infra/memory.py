import copy
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel

from orders.domain.idempotency import IdempotencyRecord
from orders.domain.listing import OrderFilters, Position
from orders.domain.order import HistoryEntry, NewOrder, Order, OrderLine, OrderSummary
from orders.domain.status import ORDER_CREATED_REASON, OrderStatus


@dataclass(slots=True)
class OutboxEntry:
    event_id: UUID
    topic: str
    key: str
    event_type: str
    payload: BaseModel
    correlation_id: UUID


@dataclass(slots=True)
class InMemoryStore:
    orders: dict[UUID, Order] = field(default_factory=dict)
    idempotency: dict[tuple[UUID, str], IdempotencyRecord] = field(default_factory=dict)
    outbox: list[OutboxEntry] = field(default_factory=list)


def _summary_of(order: Order) -> OrderSummary:
    return OrderSummary(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total=order.total,
        currency=order.currency,
        item_count=sum(line.quantity for line in order.lines),
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _matches(order: Order, customer_id: UUID | None, filters: OrderFilters) -> bool:
    return (
        (customer_id is None or order.customer_id == customer_id)
        and (filters.status is None or order.status is filters.status)
        and (filters.created_from is None or order.created_at >= filters.created_from)
        and (filters.created_to is None or order.created_at < filters.created_to)
    )


class InMemoryOrderRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, order: NewOrder, total: Decimal, now: datetime) -> None:
        request = order.request
        self._store.orders[order.id] = Order(
            id=order.id,
            customer_id=order.customer_id,
            status=OrderStatus.PENDING,
            total=total,
            currency="USD",
            card_last4=request.card_last4,
            shipping_address=request.shipping_address,
            correlation_id=order.correlation_id,
            cancel_reason=None,
            refunded_at=None,
            created_at=now,
            updated_at=now,
            lines=tuple(
                OrderLine(position, line.sku, None, line.quantity, line.unit_price)
                for position, line in enumerate(request.lines)
            ),
            history=(HistoryEntry(None, OrderStatus.PENDING, ORDER_CREATED_REASON, now),),
        )

    async def get(self, order_id: UUID) -> Order | None:
        return self._store.orders.get(order_id)

    async def transition(
        self,
        order_id: UUID,
        expected: Collection[OrderStatus],
        target: OrderStatus,
        now: datetime,
        reason: str,
    ) -> bool:
        order = self._store.orders.get(order_id)
        if order is None or order.status not in expected:
            return False
        self._store.orders[order_id] = replace(
            order,
            status=target,
            updated_at=now,
            cancel_reason=reason if target is OrderStatus.CANCELLED else order.cancel_reason,
            history=(*order.history, HistoryEntry(order.status, target, reason, now)),
        )
        return True

    async def name_lines(self, order_id: UUID, names: Mapping[str, str]) -> None:
        order = self._store.orders[order_id]
        self._store.orders[order_id] = replace(
            order,
            lines=tuple(replace(line, name=names.get(line.sku, line.name)) for line in order.lines),
        )

    async def mark_refunded(self, order_id: UUID, now: datetime, reason: str) -> bool:
        order = self._store.orders.get(order_id)
        if order is None or order.status is not OrderStatus.CANCELLED or order.refunded_at:
            return False
        self._store.orders[order_id] = replace(
            order,
            refunded_at=now,
            updated_at=now,
            history=(
                *order.history,
                HistoryEntry(OrderStatus.CANCELLED, OrderStatus.CANCELLED, reason, now),
            ),
        )
        return True

    async def list_page(
        self,
        customer_id: UUID | None,
        filters: OrderFilters,
        after: Position | None,
        limit: int,
    ) -> list[OrderSummary]:
        ordered = sorted(
            (
                order
                for order in self._store.orders.values()
                if _matches(order, customer_id, filters)
            ),
            key=lambda order: (order.created_at, order.id),
            reverse=True,
        )
        if after is not None:
            ordered = [
                order
                for order in ordered
                if (order.created_at, order.id) < (after.created_at, after.order_id)
            ]
        return [_summary_of(order) for order in ordered[: limit + 1]]

    async def lock_expired(self, created_before: datetime, limit: int) -> list[UUID]:
        open_statuses = {OrderStatus.PENDING, OrderStatus.STOCK_RESERVED}
        expired = sorted(
            (
                order
                for order in self._store.orders.values()
                if order.status in open_statuses and order.created_at <= created_before
            ),
            key=lambda order: (order.created_at, order.id),
        )
        return [order.id for order in expired[:limit]]


class InMemoryIdempotencyRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def claim(self, record: IdempotencyRecord, now: datetime) -> IdempotencyRecord | None:
        existing = self._store.idempotency.get((record.user_id, record.key))
        if existing is not None and existing.expires_at > now:
            return existing
        self._store.idempotency[(record.user_id, record.key)] = record
        return None

    async def purge_expired(self, now: datetime) -> int:
        expired = [key for key, item in self._store.idempotency.items() if item.expires_at <= now]
        for key in expired:
            del self._store.idempotency[key]
        return len(expired)


class InMemoryEventOutbox:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None:
        self._store.outbox.append(
            OutboxEntry(uuid4(), topic, key, event_type, payload, correlation_id)
        )


class InMemoryUnitOfWork:
    orders: InMemoryOrderRepository
    idempotency: InMemoryIdempotencyRepository
    events: InMemoryEventOutbox

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._snapshot: InMemoryStore | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._snapshot = copy.deepcopy(self._store)
        self._committed = False
        self.orders = InMemoryOrderRepository(self._store)
        self.idempotency = InMemoryIdempotencyRepository(self._store)
        self.events = InMemoryEventOutbox(self._store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed and self._snapshot is not None:
            self._store.orders = self._snapshot.orders
            self._store.idempotency = self._snapshot.idempotency
            self._store.outbox = self._snapshot.outbox

    async def commit(self) -> None:
        self._committed = True
