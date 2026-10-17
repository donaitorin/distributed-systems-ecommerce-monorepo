import copy
from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel

from payments.domain.payment import NewPayment, Payment, PaymentStatus


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
    payments: dict[UUID, Payment] = field(default_factory=dict)
    outbox: list[OutboxEntry] = field(default_factory=list)


class InMemoryPaymentRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, payment: NewPayment, now: datetime) -> bool:
        if payment.order_id in self._store.payments:
            return False
        self._store.payments[payment.order_id] = Payment(
            id=uuid4(),
            order_id=payment.order_id,
            customer_id=payment.customer_id,
            amount=payment.amount,
            currency=payment.currency,
            card_last4=payment.card_last4,
            status=PaymentStatus.PENDING,
            failure_reason=None,
            order_cancelled=False,
            submitted_at=None,
            check_after=None,
            refunded_at=None,
            correlation_id=payment.correlation_id,
            created_at=now,
            updated_at=now,
        )
        return True

    async def get_by_order(self, order_id: UUID) -> Payment | None:
        return self._store.payments.get(order_id)

    async def mark_submitted(
        self, order_id: UUID, check_after: datetime | None, now: datetime
    ) -> bool:
        return self._change(
            order_id,
            PaymentStatus.PENDING,
            submitted_at=now,
            check_after=check_after,
            updated_at=now,
        )

    async def succeed(self, order_id: UUID, now: datetime) -> bool:
        return self._change(
            order_id,
            PaymentStatus.PENDING,
            status=PaymentStatus.SUCCEEDED,
            check_after=None,
            updated_at=now,
        )

    async def fail(self, order_id: UUID, reason: str, now: datetime) -> bool:
        return self._change(
            order_id,
            PaymentStatus.PENDING,
            status=PaymentStatus.FAILED,
            failure_reason=reason,
            check_after=None,
            updated_at=now,
        )

    async def refund(self, order_id: UUID, now: datetime) -> bool:
        return self._change(
            order_id,
            PaymentStatus.SUCCEEDED,
            status=PaymentStatus.REFUNDED,
            refunded_at=now,
            updated_at=now,
        )

    async def flag_order_cancelled(self, order_id: UUID, now: datetime) -> Payment | None:
        payment = self._store.payments.get(order_id)
        if payment is None:
            return None
        self._store.payments[order_id] = replace(payment, order_cancelled=True, updated_at=now)
        return self._store.payments[order_id]

    async def due_for_check(self, now: datetime, limit: int) -> list[UUID]:
        due = [
            payment
            for payment in self._store.payments.values()
            if payment.status is PaymentStatus.PENDING
            and payment.check_after is not None
            and payment.check_after <= now
        ]
        due.sort(key=lambda payment: payment.check_after or now)
        return [payment.order_id for payment in due[:limit]]

    async def refunds_due(self, limit: int) -> list[UUID]:
        due = [
            payment
            for payment in self._store.payments.values()
            if payment.status is PaymentStatus.SUCCEEDED and payment.order_cancelled
        ]
        due.sort(key=lambda payment: payment.updated_at)
        return [payment.order_id for payment in due[:limit]]

    def _change(self, order_id: UUID, expected: PaymentStatus, **values: object) -> bool:
        payment = self._store.payments.get(order_id)
        if payment is None or payment.status is not expected:
            return False
        self._store.payments[order_id] = replace(payment, **values)  # type: ignore[arg-type]
        return True


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
    payments: InMemoryPaymentRepository
    events: InMemoryEventOutbox

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self._snapshot: InMemoryStore | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._snapshot = copy.deepcopy(self._store)
        self._committed = False
        self.payments = InMemoryPaymentRepository(self._store)
        self.events = InMemoryEventOutbox(self._store)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._committed and self._snapshot is not None:
            self._store.payments = self._snapshot.payments
            self._store.outbox = self._snapshot.outbox

    async def commit(self) -> None:
        self._committed = True
