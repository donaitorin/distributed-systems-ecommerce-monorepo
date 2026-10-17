import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from uuid import UUID

from catalog.application.ports import UnitOfWork, UnitOfWorkFactory
from catalog.application.product_events import publish_product_deleted, publish_product_updated
from catalog.application.products import utc_now
from catalog.domain.reservation import (
    AlreadyHandled,
    Rejected,
    ReleasedItem,
    ReservationLine,
    Reserved,
    ReservedItem,
)
from ecommerce_contracts import (
    INVENTORY_TOPIC,
    STOCK_RELEASED,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    ReleasedLineV1,
    ReservedLineV1,
    StockReleasedV1,
    StockReservationFailedV1,
    StockReservedV1,
)

logger = logging.getLogger(__name__)


class StockReservations:
    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def reserve(
        self, order_id: UUID, lines: Sequence[ReservationLine], correlation_id: UUID
    ) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            result = await uow.reservations.reserve(order_id, tuple(lines), now)
            match result:
                case AlreadyHandled():
                    logger.info("reservation already handled", extra={"order_id": str(order_id)})
                    return
                case Reserved(items):
                    await self._publish_reserved(uow, order_id, items, now, correlation_id)
                case Rejected(failure):
                    await uow.events.add(
                        topic=INVENTORY_TOPIC,
                        key=str(order_id),
                        event_type=STOCK_RESERVATION_FAILED,
                        payload=StockReservationFailedV1(
                            order_id=order_id,
                            reason=failure.reason.value,
                            sku=failure.sku,
                            available=failure.available,
                            current_price=failure.current_price,
                            occurred_at=now,
                        ),
                        correlation_id=correlation_id,
                    )
            await uow.commit()

    async def release(self, order_id: UUID, correlation_id: UUID) -> None:
        now = self._clock()
        async with self._unit_of_work() as uow:
            items = await uow.reservations.release(order_id, now)
            if items:
                await self._publish_released(uow, order_id, items, now, correlation_id)
            await uow.commit()

    async def _publish_reserved(
        self,
        uow: UnitOfWork,
        order_id: UUID,
        items: Sequence[ReservedItem],
        now: datetime,
        correlation_id: UUID,
    ) -> None:
        for item in items:
            await publish_product_updated(uow, item.product, now, correlation_id)
        await uow.events.add(
            topic=INVENTORY_TOPIC,
            key=str(order_id),
            event_type=STOCK_RESERVED,
            payload=StockReservedV1(
                order_id=order_id,
                lines=[
                    ReservedLineV1(
                        sku=item.product.sku,
                        name=item.product.name,
                        quantity=item.quantity,
                        unit_price=item.product.price,
                    )
                    for item in items
                ],
                occurred_at=now,
            ),
            correlation_id=correlation_id,
        )

    async def _publish_released(
        self,
        uow: UnitOfWork,
        order_id: UUID,
        items: Sequence[ReleasedItem],
        now: datetime,
        correlation_id: UUID,
    ) -> None:
        for item in items:
            if item.retired:
                await publish_product_deleted(
                    uow, item.product.sku, item.product.version, now, correlation_id
                )
            else:
                await publish_product_updated(uow, item.product, now, correlation_id)
        await uow.events.add(
            topic=INVENTORY_TOPIC,
            key=str(order_id),
            event_type=STOCK_RELEASED,
            payload=StockReleasedV1(
                order_id=order_id,
                lines=[
                    ReleasedLineV1(sku=item.product.sku, quantity=item.quantity) for item in items
                ],
                occurred_at=now,
            ),
            correlation_id=correlation_id,
        )
