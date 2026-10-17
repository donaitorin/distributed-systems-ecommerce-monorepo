import logging

from cart.application.ports import CartStore
from ecommerce_contracts import Envelope, OrderConfirmedV1

logger = logging.getLogger(__name__)


class PurchasedLines:
    def __init__(self, store: CartStore) -> None:
        self._store = store

    async def confirmed(self, envelope: Envelope[OrderConfirmedV1]) -> None:
        order = envelope.payload
        customer = str(order.customer_id)
        removed = 0
        for line in order.lines:
            if await self._store.remove_line_added_before(customer, line.sku, order.occurred_at):
                removed += 1
        logger.info(
            "cart cleaned after an order",
            extra={"order_id": str(order.order_id), "removed": removed},
        )
