from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.infra.repositories import SqlCategoryRepository, SqlProductRepository
from catalog.settings import DEFAULT_SEARCH_TIMEOUT_MS


class SqlAlchemyUnitOfWork:
    products: SqlProductRepository
    categories: SqlCategoryRepository
    _session: AsyncSession

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        search_timeout_ms: int = DEFAULT_SEARCH_TIMEOUT_MS,
    ) -> None:
        self._session_factory = session_factory
        self._search_timeout_ms = search_timeout_ms

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self.products = SqlProductRepository(self._session, self._search_timeout_ms)
        self.categories = SqlCategoryRepository(self._session)
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
