import asyncio
import contextlib
import logging
from collections.abc import Callable, Collection, Mapping
from datetime import datetime, timedelta
from uuid import UUID

from orders.application.clock import utc_now
from orders.application.order_events import (
    publish_cancelled,
    publish_confirmed,
    publish_payment_requested,
)
from orders.application.ports import UnitOfWork, UnitOfWorkFactory
from orders.domain.status import (
    CANCELLABLE,
    NO_PAYMENT_DUE_REASON,
    ORDER_CONFIRMED_REASON,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED_REASON,
    PAYMENT_SUCCEEDED_REASON,
    SAGA_TIMEOUT,
    STOCK_RESERVED_REASON,
    OrderStatus,
    ensure_transition_allowed,
)

logger = logging.getLogger(__name__)

SWEEP_BATCH_SIZE = 100


async def move(
    uow: UnitOfWork,
    order_id: UUID,
    expected: Collection[OrderStatus],
    target: OrderStatus,
    now: datetime,
    reason: str,
) -> bool:
    for current in expected:
        ensure_transition_allowed(current, target)
    return await uow.orders.transition(order_id, expected, target, now, reason)


class OrderSaga:
    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def stock_reserved(self, order_id: UUID, names: Mapping[str, str]) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            order = await uow.orders.get(order_id)
            if order is None:
                logger.warning("stock reserved for an unknown order", extra={"order_id": order_id})
                return
            reserved = {OrderStatus.PENDING}
            if not await move(
                uow, order_id, reserved, OrderStatus.STOCK_RESERVED, now, STOCK_RESERVED_REASON
            ):
                return
            await uow.orders.name_lines(order_id, names)
            if order.total > 0:
                await publish_payment_requested(uow, order, now)
            else:
                await move(
                    uow,
                    order_id,
                    {OrderStatus.STOCK_RESERVED},
                    OrderStatus.CONFIRMED,
                    now,
                    NO_PAYMENT_DUE_REASON,
                )
                await publish_confirmed(uow, order, now)
            await uow.commit()

    async def reservation_failed(self, order_id: UUID, reason: str) -> None:
        await self._cancel(order_id, {OrderStatus.PENDING}, reason)

    async def payment_succeeded(self, order_id: UUID) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            order = await uow.orders.get(order_id)
            if order is None:
                logger.warning("payment for an unknown order", extra={"order_id": order_id})
                return
            if not await move(
                uow,
                order_id,
                {OrderStatus.STOCK_RESERVED},
                OrderStatus.PAID,
                now,
                PAYMENT_SUCCEEDED_REASON,
            ):
                return
            await move(
                uow,
                order_id,
                {OrderStatus.PAID},
                OrderStatus.CONFIRMED,
                now,
                ORDER_CONFIRMED_REASON,
            )
            await publish_confirmed(uow, order, now)
            await uow.commit()

    async def payment_failed(self, order_id: UUID) -> None:
        await self._cancel(order_id, {OrderStatus.STOCK_RESERVED}, PAYMENT_FAILED)

    async def payment_refunded(self, order_id: UUID) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            await uow.orders.mark_refunded(order_id, now, PAYMENT_REFUNDED_REASON)
            await uow.commit()

    async def _cancel(self, order_id: UUID, expected: Collection[OrderStatus], reason: str) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            if await cancel(uow, order_id, expected, reason, now):
                await uow.commit()


async def cancel(
    uow: UnitOfWork,
    order_id: UUID,
    expected: Collection[OrderStatus],
    reason: str,
    now: datetime,
) -> bool:
    order = await uow.orders.get(order_id)
    if order is None:
        logger.warning("cancelling an unknown order", extra={"order_id": order_id})
        return False
    if not await move(uow, order_id, expected, OrderStatus.CANCELLED, now, reason):
        return False
    await publish_cancelled(uow, order, reason, now)
    return True


class SagaTimeouts:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        timeout: timedelta,
        clock: Callable[[], datetime] = utc_now,
        batch_size: int = SWEEP_BATCH_SIZE,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._timeout = timeout
        self._clock = clock
        self._batch_size = batch_size

    async def sweep(self) -> int:
        now = self._clock()
        async with self._unit_of_work() as uow:
            expired = await uow.orders.lock_expired(now - self._timeout, self._batch_size)
            cancelled = 0
            for order_id in expired:
                if await cancel(uow, order_id, CANCELLABLE, SAGA_TIMEOUT, now):
                    cancelled += 1
            await uow.commit()
        if cancelled:
            logger.info("saga timeout cancelled orders", extra={"count": cancelled})
        return len(expired)

    async def purge_idempotency_keys(self) -> int:
        async with self._unit_of_work() as uow:
            purged = await uow.idempotency.purge_expired(self._clock())
            await uow.commit()
        return purged

    async def run(self, stop: asyncio.Event, interval_seconds: float) -> None:
        while not stop.is_set():
            try:
                while await self.sweep() >= self._batch_size:
                    pass
                await self.purge_idempotency_keys()
            except Exception:
                logger.exception("saga timeout sweep failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), interval_seconds)
