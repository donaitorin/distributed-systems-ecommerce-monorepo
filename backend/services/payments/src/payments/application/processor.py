import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from ecommerce_contracts import OrderPaymentRequestedV1
from payments.application.clock import utc_now
from payments.application.payment_events import (
    publish_failed,
    publish_refunded,
    publish_succeeded,
)
from payments.application.ports import PaymentProvider, UnitOfWorkFactory
from payments.domain.payment import (
    ChargeOutcome,
    ChargeRequest,
    Declined,
    NewPayment,
    PaymentStatus,
    Processing,
    RefundRequest,
    Succeeded,
)

logger = logging.getLogger(__name__)

SETTLE_BATCH_SIZE = 50


class PaymentProcessor:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        provider: PaymentProvider,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._provider = provider
        self._clock = clock

    async def charge_requested(
        self, request: OrderPaymentRequestedV1, correlation_id: UUID
    ) -> None:
        async with self._unit_of_work() as uow:
            await uow.payments.add(
                NewPayment(
                    request.order_id,
                    request.customer_id,
                    request.amount,
                    request.currency,
                    request.card_last4,
                    correlation_id,
                ),
                self._clock(),
            )
            payment = await uow.payments.get_by_order(request.order_id)
            await uow.commit()
        if payment is None or not payment.awaiting_provider:
            return
        outcome = await self._provider.charge(ChargeRequest.for_payment(payment))
        await self.apply(request.order_id, outcome)

    async def order_cancelled(self, order_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            payment = await uow.payments.flag_order_cancelled(order_id, self._clock())
            await uow.commit()
        if payment is not None and payment.status is PaymentStatus.SUCCEEDED:
            await self.refund(order_id)

    async def apply(self, order_id: UUID, outcome: ChargeOutcome) -> None:
        match outcome:
            case Succeeded():
                await self._succeeded(order_id)
            case Declined(reason):
                await self._declined(order_id, reason)
            case Processing(check_after):
                await self._processing(order_id, check_after)

    async def refund(self, order_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            payment = await uow.payments.get_by_order(order_id)
        if payment is None or payment.status is not PaymentStatus.SUCCEEDED:
            return
        await self._provider.refund(RefundRequest.for_payment(payment))
        now = self._clock()
        async with self._unit_of_work() as uow:
            if await uow.payments.refund(order_id, now):
                await publish_refunded(uow, payment, now)
                await uow.commit()

    async def settle_due(self) -> int:
        async with self._unit_of_work() as uow:
            due = await uow.payments.due_for_check(self._clock(), SETTLE_BATCH_SIZE)
        for order_id in due:
            await self._check(order_id)
        return len(due)

    async def refund_due(self) -> int:
        async with self._unit_of_work() as uow:
            due = await uow.payments.refunds_due(SETTLE_BATCH_SIZE)
        for order_id in due:
            await self.refund(order_id)
        return len(due)

    async def _check(self, order_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            payment = await uow.payments.get_by_order(order_id)
        if payment is None or payment.status is not PaymentStatus.PENDING:
            return
        await self.apply(
            order_id, await self._provider.status_of(ChargeRequest.for_payment(payment))
        )

    async def _succeeded(self, order_id: UUID) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            if not await uow.payments.succeed(order_id, now):
                return
            payment = await uow.payments.get_by_order(order_id)
            assert payment is not None
            await publish_succeeded(uow, payment, now)
            await uow.commit()
        if payment.order_cancelled:
            await self.refund(order_id)

    async def _declined(self, order_id: UUID, reason: str) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            if not await uow.payments.fail(order_id, reason, now):
                return
            payment = await uow.payments.get_by_order(order_id)
            assert payment is not None
            await publish_failed(uow, payment, reason, now)
            await uow.commit()

    async def _processing(self, order_id: UUID, check_after: datetime | None) -> None:
        async with self._unit_of_work() as uow:
            await uow.payments.mark_submitted(order_id, check_after, self._clock())
            await uow.commit()
