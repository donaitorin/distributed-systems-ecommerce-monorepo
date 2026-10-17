from collections.abc import Callable, Collection, Mapping
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from pydantic import BaseModel

from orders.domain.idempotency import IdempotencyRecord
from orders.domain.listing import OrderFilters, Position
from orders.domain.order import NewOrder, Order, OrderSummary
from orders.domain.status import OrderStatus


class OrderRepository(Protocol):
    async def add(self, order: NewOrder, total: Decimal, now: datetime) -> None: ...

    async def get(self, order_id: UUID) -> Order | None: ...

    async def transition(
        self,
        order_id: UUID,
        expected: Collection[OrderStatus],
        target: OrderStatus,
        now: datetime,
        reason: str,
    ) -> bool: ...

    async def name_lines(self, order_id: UUID, names: Mapping[str, str]) -> None: ...

    async def mark_refunded(self, order_id: UUID, now: datetime, reason: str) -> bool: ...

    async def list_page(
        self,
        customer_id: UUID | None,
        filters: OrderFilters,
        after: Position | None,
        limit: int,
    ) -> list[OrderSummary]: ...

    async def lock_expired(self, created_before: datetime, limit: int) -> list[UUID]: ...


class IdempotencyRepository(Protocol):
    async def claim(self, record: IdempotencyRecord, now: datetime) -> IdempotencyRecord | None: ...

    async def purge_expired(self, now: datetime) -> int: ...


class EventOutbox(Protocol):
    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None: ...


class UnitOfWork(Protocol):
    @property
    def orders(self) -> OrderRepository: ...

    @property
    def idempotency(self) -> IdempotencyRepository: ...

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
type ResponseBody = dict[str, Any]
