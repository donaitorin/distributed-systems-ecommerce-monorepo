from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from payments.domain.payment import NewPayment, Payment, PaymentStatus
from payments.infra.models import PaymentModel


def to_payment(model: PaymentModel) -> Payment:
    return Payment(
        id=model.id,
        order_id=model.order_id,
        customer_id=model.customer_id,
        amount=model.amount,
        currency=model.currency,
        card_last4=model.card_last4,
        status=PaymentStatus(model.status),
        failure_reason=model.failure_reason,
        order_cancelled=model.order_cancelled,
        submitted_at=model.submitted_at,
        check_after=model.check_after,
        refunded_at=model.refunded_at,
        correlation_id=model.correlation_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: NewPayment, now: datetime) -> bool:
        statement = (
            pg_insert(PaymentModel)
            .values(
                id=uuid4(),
                order_id=payment.order_id,
                customer_id=payment.customer_id,
                amount=payment.amount,
                currency=payment.currency,
                card_last4=payment.card_last4,
                status=PaymentStatus.PENDING.value,
                correlation_id=payment.correlation_id,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[PaymentModel.order_id])
            .returning(PaymentModel.id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def get_by_order(self, order_id: UUID) -> Payment | None:
        model = await self._session.scalar(
            select(PaymentModel)
            .where(PaymentModel.order_id == order_id)
            .execution_options(populate_existing=True)
        )
        return to_payment(model) if model is not None else None

    async def mark_submitted(
        self, order_id: UUID, check_after: datetime | None, now: datetime
    ) -> bool:
        return await self._transition(
            order_id,
            PaymentStatus.PENDING,
            submitted_at=now,
            check_after=check_after,
            updated_at=now,
        )

    async def succeed(self, order_id: UUID, now: datetime) -> bool:
        return await self._transition(
            order_id,
            PaymentStatus.PENDING,
            status=PaymentStatus.SUCCEEDED.value,
            check_after=None,
            updated_at=now,
        )

    async def fail(self, order_id: UUID, reason: str, now: datetime) -> bool:
        return await self._transition(
            order_id,
            PaymentStatus.PENDING,
            status=PaymentStatus.FAILED.value,
            failure_reason=reason,
            check_after=None,
            updated_at=now,
        )

    async def refund(self, order_id: UUID, now: datetime) -> bool:
        return await self._transition(
            order_id,
            PaymentStatus.SUCCEEDED,
            status=PaymentStatus.REFUNDED.value,
            refunded_at=now,
            updated_at=now,
        )

    async def flag_order_cancelled(self, order_id: UUID, now: datetime) -> Payment | None:
        model = await self._session.scalar(
            update(PaymentModel)
            .where(PaymentModel.order_id == order_id)
            .values(order_cancelled=True, updated_at=now)
            .returning(PaymentModel)
            .execution_options(populate_existing=True)
        )
        return to_payment(model) if model is not None else None

    async def due_for_check(self, now: datetime, limit: int) -> list[UUID]:
        statement = (
            select(PaymentModel.order_id)
            .where(
                PaymentModel.status == PaymentStatus.PENDING.value,
                PaymentModel.check_after.is_not(None),
                PaymentModel.check_after <= now,
            )
            .order_by(PaymentModel.check_after)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def refunds_due(self, limit: int) -> list[UUID]:
        statement = (
            select(PaymentModel.order_id)
            .where(
                PaymentModel.status == PaymentStatus.SUCCEEDED.value,
                PaymentModel.order_cancelled.is_(True),
            )
            .order_by(PaymentModel.updated_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())

    async def _transition(self, order_id: UUID, expected: PaymentStatus, **values: object) -> bool:
        updated = await self._session.execute(
            update(PaymentModel)
            .where(PaymentModel.order_id == order_id, PaymentModel.status == expected.value)
            .values(**values)
            .returning(PaymentModel.id)
        )
        return updated.scalar_one_or_none() is not None
