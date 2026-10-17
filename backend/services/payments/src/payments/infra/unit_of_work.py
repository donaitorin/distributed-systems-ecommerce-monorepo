from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payments.infra.events import SqlEventOutbox
from payments.infra.repositories import SqlPaymentRepository


class SqlAlchemyUnitOfWork:
    payments: SqlPaymentRepository
    events: SqlEventOutbox
    _session: AsyncSession

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.payments = SqlPaymentRepository(self._session)
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
