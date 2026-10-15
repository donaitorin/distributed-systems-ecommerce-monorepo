import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from catalog.application.import_jobs import ImportJobs
from catalog.infra.database import create_engine, create_session_factory
from catalog.infra.models import OUTBOX, PROCESSED_EVENTS
from catalog.infra.unit_of_work import SqlAlchemyUnitOfWork
from catalog.main import build_imports_storage
from catalog.settings import CatalogSettings
from ecommerce_contracts import (
    IMPORT_REQUESTED,
    IMPORT_VALIDATION_REQUESTED,
    IMPORTS_TOPIC,
    Envelope,
    ImportFileReference,
    ImportRequestedV1,
    ImportValidationRequestedV1,
)
from ecommerce_messaging import (
    DeadLetter,
    EventConsumer,
    Handler,
    KafkaPublisher,
    KafkaSettings,
    KafkaSource,
    MessageSource,
    OutboxRelay,
    Publisher,
    RetryPolicy,
    standalone_handler,
)
from ecommerce_messaging.consumer import DEFAULT_RETRY
from ecommerce_observability import configure_logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "catalog-worker"
CONSUMER_GROUP = "catalog-imports"


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    catalog: CatalogSettings
    kafka: KafkaSettings

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            catalog=CatalogSettings.from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
        )


def import_handlers(jobs: ImportJobs) -> Sequence[Handler]:
    async def on_validation_requested(envelope: Envelope[ImportValidationRequestedV1]) -> None:
        await jobs.validate(envelope.payload.import_id)

    async def on_requested(envelope: Envelope[ImportRequestedV1]) -> None:
        await jobs.process(envelope.payload.import_id)

    return [
        standalone_handler(
            IMPORT_VALIDATION_REQUESTED, 1, ImportValidationRequestedV1, on_validation_requested
        ),
        standalone_handler(IMPORT_REQUESTED, 1, ImportRequestedV1, on_requested),
    ]


def mark_failed_on_dead_letter(jobs: ImportJobs) -> Callable[[DeadLetter], Awaitable[None]]:
    async def hook(letter: DeadLetter) -> None:
        if letter.envelope is None or not isinstance(letter.envelope.payload, ImportFileReference):
            return
        reason = f"{letter.error_type}: {letter.error}"
        await jobs.fail(letter.envelope.payload.import_id, reason)

    return hook


def build_consumer(
    jobs: ImportJobs,
    source: MessageSource,
    dead_letters: Publisher,
    session_factory: async_sessionmaker[AsyncSession],
    group: str = CONSUMER_GROUP,
    retry: RetryPolicy = DEFAULT_RETRY,
) -> EventConsumer:
    return EventConsumer(
        group=group,
        source=source,
        dead_letters=dead_letters,
        session_factory=session_factory,
        processed_events=PROCESSED_EVENTS,
        handlers=import_handlers(jobs),
        retry=retry,
        on_dead_letter=mark_failed_on_dead_letter(jobs),
    )


async def run_worker(settings: WorkerSettings, stop: asyncio.Event) -> None:
    engine = create_engine(settings.catalog.database_url)
    session_factory = create_session_factory(engine)
    jobs = ImportJobs(
        lambda: SqlAlchemyUnitOfWork(session_factory, settings.catalog.search_timeout_ms),
        build_imports_storage(settings.catalog),
    )
    publisher = KafkaPublisher(settings.kafka)
    source = KafkaSource(settings.kafka, [IMPORTS_TOPIC], CONSUMER_GROUP)
    relay = OutboxRelay(OUTBOX, session_factory, publisher)
    consumer = build_consumer(jobs, source, publisher, session_factory)
    logger.info("catalog worker started")
    try:
        await asyncio.gather(relay.run(stop), consumer.run(stop))
    finally:
        await source.close()
        await publisher.close()
        await engine.dispose()
        logger.info("catalog worker stopped")


def main() -> None:
    settings = WorkerSettings.from_env(os.environ)
    configure_logging(SERVICE_NAME, settings.catalog.log_level)

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for name in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(name, stop.set)
        await run_worker(settings, stop)

    asyncio.run(run())


if __name__ == "__main__":
    main()
