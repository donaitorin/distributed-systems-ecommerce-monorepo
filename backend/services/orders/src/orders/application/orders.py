from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from orders.application.clock import utc_now
from orders.application.cursors import decode_cursor, encode_cursor, fingerprint_of
from orders.application.errors import (
    IdempotencyKeyReusedError,
    InvalidIdempotencyKeyError,
    OrderNotFoundError,
)
from orders.application.order_events import publish_created
from orders.application.ports import ResponseBody, UnitOfWorkFactory
from orders.domain import idempotency
from orders.domain.idempotency import IdempotencyRecord
from orders.domain.listing import OrderFilters, Position
from orders.domain.order import NewOrder, Order, OrderRequest, OrderSummary
from orders.domain.status import OrderStatus

ACCEPTED_STATUS = 202


@dataclass(frozen=True, slots=True)
class Placement:
    order_id: UUID
    status_code: int
    body: ResponseBody
    replayed: bool


@dataclass(frozen=True, slots=True)
class OrderPage:
    items: list[OrderSummary]
    next_cursor: str | None


class OrderService:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        clock: Callable[[], datetime] = utc_now,
        new_id: Callable[[], UUID] = uuid4,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._new_id = new_id

    async def place(
        self,
        customer_id: UUID,
        key: str,
        request: OrderRequest,
        correlation_id: UUID,
    ) -> Placement:
        if not idempotency.is_valid_key(key):
            raise InvalidIdempotencyKeyError(
                f"the Idempotency-Key must have {idempotency.KEY_MIN_LENGTH} to "
                f"{idempotency.KEY_MAX_LENGTH} letters, digits, hyphens, underscores, "
                "colons or dots"
            )
        now = self._clock()
        order = NewOrder(self._new_id(), customer_id, request, correlation_id)
        record = IdempotencyRecord(
            user_id=customer_id,
            key=key,
            fingerprint=idempotency.fingerprint_of(request),
            order_id=order.id,
            response_status=ACCEPTED_STATUS,
            response_body={"id": str(order.id), "status": OrderStatus.PENDING.value},
            created_at=now,
            expires_at=now + idempotency.IDEMPOTENCY_TTL,
        )
        async with self._unit_of_work() as uow:
            existing = await uow.idempotency.claim(record, now)
            if existing is not None:
                if existing.fingerprint != record.fingerprint:
                    raise IdempotencyKeyReusedError(key)
                return Placement(
                    existing.order_id, existing.response_status, existing.response_body, True
                )
            await uow.orders.add(order, request.total, now)
            await publish_created(uow, order, now)
            await uow.commit()
        return Placement(order.id, record.response_status, record.response_body, False)

    async def get_own(self, customer_id: UUID, order_id: UUID) -> Order:
        order = await self._get(order_id)
        if order.customer_id != customer_id:
            raise OrderNotFoundError(order_id)
        return order

    async def get_any(self, order_id: UUID) -> Order:
        return await self._get(order_id)

    async def list_own(
        self, customer_id: UUID, filters: OrderFilters, limit: int, cursor: str | None
    ) -> OrderPage:
        return await self._list(customer_id, filters, limit, cursor)

    async def list_all(self, filters: OrderFilters, limit: int, cursor: str | None) -> OrderPage:
        return await self._list(None, filters, limit, cursor)

    async def _get(self, order_id: UUID) -> Order:
        async with self._unit_of_work() as uow:
            order = await uow.orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order

    async def _list(
        self, customer_id: UUID | None, filters: OrderFilters, limit: int, cursor: str | None
    ) -> OrderPage:
        fingerprint = fingerprint_of(filters)
        after = decode_cursor(cursor, fingerprint) if cursor else None
        async with self._unit_of_work() as uow:
            rows = await uow.orders.list_page(customer_id, filters, after, limit)
        items = rows[:limit]
        next_cursor = None
        if len(rows) > limit:
            last = items[-1]
            next_cursor = encode_cursor(fingerprint, Position(last.created_at, last.id))
        return OrderPage(items, next_cursor)
