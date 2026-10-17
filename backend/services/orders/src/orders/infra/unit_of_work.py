from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from orders.infra.events import SqlEventOutbox
from orders.infra.repositories import SqlIdempotencyRepository, SqlOrderRepository


class SqlAlchemyUnitOfWork:
    orders: SqlOrderRepository
    idempotency: SqlIdempotencyRepository
    events: SqlEventOutbox
    _session: AsyncSession

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.orders = SqlOrderRepository(self._session)
        self.idempotency = SqlIdempotencyRepository(self._session)
        self.events = SqlEventOutbox(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()
