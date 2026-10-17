from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_messaging import OutboxWriter
from orders.infra.models import OUTBOX

PRODUCER = "orders-service"


class SqlEventOutbox:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._writer = OutboxWriter(OUTBOX, PRODUCER)

    async def add(
        self, *, topic: str, key: str, event_type: str, payload: BaseModel, correlation_id: UUID
    ) -> None:
        await self._writer.add(
            self._session,
            topic=topic,
            key=key,
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
        )
