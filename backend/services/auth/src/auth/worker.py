import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from auth.infra.database import create_engine, create_session_factory
from auth.infra.models import OUTBOX
from auth.settings import AuthSettings
from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutboxRelay, Publisher
from ecommerce_observability import configure_logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "auth-worker"


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    auth: AuthSettings
    kafka: KafkaSettings

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            auth=AuthSettings.from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
        )


def build_relay(
    session_factory: async_sessionmaker[AsyncSession], publisher: Publisher
) -> OutboxRelay:
    return OutboxRelay(OUTBOX, session_factory, publisher)


async def run_worker(settings: WorkerSettings, stop: asyncio.Event) -> None:
    engine = create_engine(settings.auth.database_url)
    publisher = KafkaPublisher(settings.kafka)
    relay = build_relay(create_session_factory(engine), publisher)
    logger.info("auth worker started")
    try:
        await relay.run(stop)
    finally:
        await publisher.close()
        await engine.dispose()
        logger.info("auth worker stopped")


def main() -> None:
    settings = WorkerSettings.from_env(os.environ)
    configure_logging(SERVICE_NAME, settings.auth.log_level)

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
