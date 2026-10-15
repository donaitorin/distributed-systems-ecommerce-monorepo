import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Self

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from accounts.application.clock import utc_now
from accounts.application.ports import ProfileRepository
from accounts.application.profile_events import ProfileEvents
from accounts.infra.database import create_engine, create_session_factory
from accounts.infra.models import PROCESSED_EVENTS
from accounts.infra.repositories import SqlProfileRepository
from accounts.settings import database_url_from_env
from ecommerce_contracts import (
    AUTH_TOPIC,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    Envelope,
    UserRegisteredV1,
    UserRoleChangedV1,
)
from ecommerce_messaging import (
    DeadLetter,
    EventConsumer,
    Handler,
    KafkaPublisher,
    KafkaSettings,
    KafkaSource,
    MessageSource,
    Publisher,
    RetryPolicy,
    transactional_handler,
)
from ecommerce_messaging.consumer import DEFAULT_RETRY
from ecommerce_observability import configure_logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "accounts-worker"
CONSUMER_GROUP = "accounts-auth-events"

type RepositoryFactory = Callable[[AsyncSession], ProfileRepository]


def sql_profiles(session: AsyncSession) -> ProfileRepository:
    return SqlProfileRepository(session)


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_url: URL
    kafka: KafkaSettings
    log_level: str = "INFO"
    topic: str = AUTH_TOPIC
    group: str = CONSUMER_GROUP

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
            log_level=environ.get("LOG_LEVEL", "INFO"),
        )


def profile_handlers(
    events: ProfileEvents, repository_for: RepositoryFactory = sql_profiles
) -> Sequence[Handler]:
    async def on_registered(envelope: Envelope[UserRegisteredV1], session: AsyncSession) -> None:
        await events.registered(envelope, repository_for(session))

    async def on_role_changed(envelope: Envelope[UserRoleChangedV1], session: AsyncSession) -> None:
        await events.role_changed(envelope, repository_for(session))

    return [
        transactional_handler(USER_REGISTERED, 1, UserRegisteredV1, on_registered),
        transactional_handler(USER_ROLE_CHANGED, 1, UserRoleChangedV1, on_role_changed),
    ]


async def log_dead_letter(letter: DeadLetter) -> None:
    event_id = str(letter.envelope.event_id) if letter.envelope is not None else None
    logger.warning(
        "auth event dead-lettered",
        extra={
            "group": letter.group,
            "event_id": event_id,
            "event_type": letter.envelope.event_type if letter.envelope is not None else None,
            "error_type": letter.error_type,
            "attempts": letter.attempts,
            "topic": letter.message.topic,
            "partition": letter.message.partition,
            "offset": letter.message.offset,
        },
    )


def build_source(settings: WorkerSettings) -> KafkaSource:
    return KafkaSource(settings.kafka, [settings.topic], settings.group)


def build_consumer(
    source: MessageSource,
    dead_letters: Publisher,
    session_factory: async_sessionmaker[AsyncSession],
    group: str = CONSUMER_GROUP,
    clock: Callable[[], datetime] = utc_now,
    retry: RetryPolicy = DEFAULT_RETRY,
    repository_for: RepositoryFactory = sql_profiles,
) -> EventConsumer:
    return EventConsumer(
        group=group,
        source=source,
        dead_letters=dead_letters,
        session_factory=session_factory,
        processed_events=PROCESSED_EVENTS,
        handlers=profile_handlers(ProfileEvents(clock), repository_for),
        retry=retry,
        on_dead_letter=log_dead_letter,
    )


async def run_worker(settings: WorkerSettings, stop: asyncio.Event) -> None:
    engine = create_engine(settings.database_url)
    publisher = KafkaPublisher(settings.kafka)
    source = build_source(settings)
    consumer = build_consumer(
        source, publisher, create_session_factory(engine), group=settings.group
    )
    logger.info("accounts worker started")
    try:
        await consumer.run(stop)
    finally:
        await source.close()
        await publisher.close()
        await engine.dispose()
        logger.info("accounts worker stopped")


def main() -> None:
    settings = WorkerSettings.from_env(os.environ)
    configure_logging(SERVICE_NAME, settings.log_level)

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
