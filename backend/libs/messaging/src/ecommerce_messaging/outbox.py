import asyncio
import logging
import zlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Final, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import (
    BigInteger,
    Column,
    CursorResult,
    DateTime,
    Identity,
    Index,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce_contracts import Envelope
from ecommerce_messaging.errors import PublishError
from ecommerce_messaging.ports import OutgoingMessage, Publisher

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE: Final = 100
DEFAULT_POLL_INTERVAL_SECONDS: Final = 0.5
MAX_BACKOFF_SECONDS: Final = 10.0
DEFAULT_RETENTION: Final = timedelta(days=1)
PURGE_EVERY_SECONDS: Final = 3600.0


def outbox_table(metadata: MetaData, name: str = "outbox") -> Table:
    return Table(
        name,
        metadata,
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("event_id", PG_UUID(as_uuid=True), nullable=False, unique=True),
        Column("topic", String(255), nullable=False),
        Column("key", String(255), nullable=False),
        Column("payload", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("published_at", DateTime(timezone=True), nullable=True),
        Index(
            f"ix_{name}_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


class OutboxWriter:
    def __init__(self, table: Table, producer: str) -> None:
        self._table = table
        self._producer = producer

    async def add[PayloadT: BaseModel](
        self,
        session: AsyncSession,
        *,
        topic: str,
        key: str,
        event_type: str,
        payload: PayloadT,
        correlation_id: UUID,
        event_version: int = 1,
    ) -> Envelope[PayloadT]:
        envelope = Envelope[PayloadT](
            event_type=event_type,
            event_version=event_version,
            correlation_id=correlation_id,
            producer=self._producer,
            payload=payload,
        )
        await session.execute(
            insert(self._table).values(
                event_id=envelope.event_id,
                topic=topic,
                key=key,
                payload=envelope.model_dump_json(),
            )
        )
        return envelope


class OutboxRelay:
    def __init__(
        self,
        table: Table,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: Publisher,
        batch_size: int = DEFAULT_BATCH_SIZE,
        poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
        retention: timedelta = DEFAULT_RETENTION,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._table = table
        self._session_factory = session_factory
        self._publisher = publisher
        self._batch_size = batch_size
        self._poll_interval = poll_interval_seconds
        self._retention = retention
        self._clock = clock
        self._lock_id = zlib.crc32(table.name.encode())

    async def drain_once(self) -> int:
        async with self._session_factory() as session, session.begin():
            leader = await session.scalar(
                text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": self._lock_id}
            )
            if not leader:
                return 0
            rows = (
                await session.execute(
                    select(self._table)
                    .where(self._table.c.published_at.is_(None))
                    .order_by(self._table.c.id)
                    .limit(self._batch_size)
                    .with_for_update()
                )
            ).all()
            delivered: list[int] = []
            failure: PublishError | None = None
            for row in rows:
                try:
                    await self._publisher.publish(
                        OutgoingMessage(row.topic, row.key, row.payload.encode())
                    )
                except PublishError as error:
                    failure = error
                    break
                delivered.append(row.id)
            if delivered:
                await session.execute(
                    update(self._table)
                    .where(self._table.c.id.in_(delivered))
                    .values(published_at=self._clock())
                )
        if failure is not None:
            raise failure
        return len(delivered)

    async def purge_published(self) -> int:
        cutoff = self._clock() - self._retention
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                delete(self._table).where(
                    self._table.c.published_at.is_not(None), self._table.c.published_at < cutoff
                )
            )
        return int(cast(CursorResult[Any], result).rowcount)

    async def run(self, stop: asyncio.Event) -> None:
        backoff = self._poll_interval
        loop = asyncio.get_running_loop()
        next_purge = loop.time() + PURGE_EVERY_SECONDS
        while not stop.is_set():
            try:
                delivered = await self.drain_once()
                backoff = self._poll_interval
                if loop.time() >= next_purge:
                    await self.purge_published()
                    next_purge = loop.time() + PURGE_EVERY_SECONDS
            except (PublishError, SQLAlchemyError, OSError) as error:
                logger.warning(
                    "outbox relay could not deliver, will retry",
                    extra={"error": str(error), "retry_in_seconds": backoff},
                )
                delivered = 0
                await _sleep_or_stop(stop, backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue
            if delivered < self._batch_size:
                await _sleep_or_stop(stop, self._poll_interval)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except TimeoutError:
        return
