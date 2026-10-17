import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Self

from cart.application.ports import ProductProjection
from cart.application.projection import ProjectionUpdates
from cart.infra.redis_client import create_redis
from cart.infra.redis_projection import RedisProductProjection
from cart.settings import CART_TTL_SECONDS, RedisSettings
from ecommerce_contracts import (
    CATALOG_TOPIC,
    PRODUCT_DELETED,
    PRODUCT_UPDATED,
    Envelope,
    ProductDeletedV1,
    ProductUpdatedV1,
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
    idempotent_handler,
)
from ecommerce_messaging.consumer import Sleeper
from ecommerce_observability import configure_logging

logger = logging.getLogger(__name__)

SERVICE_NAME = "cart-worker"
CONSUMER_GROUP = "cart-catalog-events"
PATIENT_RETRY = RetryPolicy(max_attempts=8, base_delay_seconds=0.5, max_delay_seconds=8.0)


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    redis: RedisSettings
    kafka: KafkaSettings
    ttl_seconds: int = CART_TTL_SECONDS
    log_level: str = "INFO"
    topic: str = CATALOG_TOPIC
    group: str = CONSUMER_GROUP

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            redis=RedisSettings.from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
            ttl_seconds=int(environ.get("CART_TTL_SECONDS", CART_TTL_SECONDS)),
            log_level=environ.get("LOG_LEVEL", "INFO"),
        )


def product_handlers(updates: ProjectionUpdates) -> Sequence[Handler]:
    async def on_updated(envelope: Envelope[ProductUpdatedV1]) -> None:
        await updates.updated(envelope)

    async def on_deleted(envelope: Envelope[ProductDeletedV1]) -> None:
        await updates.deleted(envelope)

    return [
        idempotent_handler(PRODUCT_UPDATED, 1, ProductUpdatedV1, on_updated),
        idempotent_handler(PRODUCT_DELETED, 1, ProductDeletedV1, on_deleted),
    ]


async def log_dead_letter(letter: DeadLetter) -> None:
    logger.warning(
        "catalog event dead-lettered",
        extra={
            "group": letter.group,
            "event_id": str(letter.envelope.event_id) if letter.envelope is not None else None,
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
    projection: ProductProjection,
    group: str = CONSUMER_GROUP,
    retry: RetryPolicy = PATIENT_RETRY,
    sleep: Sleeper = asyncio.sleep,
) -> EventConsumer:
    return EventConsumer(
        group=group,
        source=source,
        dead_letters=dead_letters,
        handlers=product_handlers(ProjectionUpdates(projection)),
        retry=retry,
        on_dead_letter=log_dead_letter,
        sleep=sleep,
    )


async def run_worker(settings: WorkerSettings, stop: asyncio.Event) -> None:
    redis = create_redis(settings.redis)
    publisher = KafkaPublisher(settings.kafka)
    source = build_source(settings)
    consumer = build_consumer(
        source,
        publisher,
        RedisProductProjection(redis, settings.ttl_seconds),
        group=settings.group,
    )
    logger.info("cart worker started")
    try:
        await consumer.run(stop)
    finally:
        await source.close()
        await publisher.close()
        await redis.aclose()
        logger.info("cart worker stopped")


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
