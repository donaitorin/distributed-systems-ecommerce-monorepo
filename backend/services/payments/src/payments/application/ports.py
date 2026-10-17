from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel

from payments.domain.payment import (
    ChargeOutcome,
    ChargeRequest,
    NewPayment,
    Payment,
    RefundRequest,
)


class PaymentProvider(Protocol):
    async def charge(self, request: ChargeRequest) -> ChargeOutcome: ...

    async def status_of(self, request: ChargeRequest) -> ChargeOutcome: ...

    async def refund(self, request: RefundRequest) -> None: ...


class PaymentRepository(Protocol):
    async def add(self, payment: NewPayment, now: datetime) -> bool: ...

    async def get_by_order(self, order_id: UUID) -> Payment | None: ...

    async def mark_submitted(
        self, order_id: UUID, check_after: datetime | None, now: datetime
    ) -> bool: ...

    async def succeed(self, order_id: UUID, now: datetime) -> bool: ...

    async def fail(self, order_id: UUID, reason: str, now: datetime) -> bool: ...

    async def refund(self, order_id: UUID, now: datetime) -> bool: ...

    async def flag_order_cancelled(self, order_id: UUID, now: datetime) -> Payment | None: ...

    async def due_for_check(self, now: datetime, limit: int) -> list[UUID]: ...

    async def refunds_due(self, limit: int) -> list[UUID]: ...


class EventOutbox(Protocol):
    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None: ...


class UnitOfWork(Protocol):
    @property
    def payments(self) -> PaymentRepository: ...

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
