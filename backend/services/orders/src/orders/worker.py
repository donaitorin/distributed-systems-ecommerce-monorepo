import asyncio
import contextlib
import logging
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Self

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce_contracts import (
    INVENTORY_TOPIC,
    PAYMENT_FAILED,
    PAYMENT_REFUNDED,
    PAYMENT_SUCCEEDED,
    PAYMENTS_TOPIC,
    STOCK_RESERVATION_FAILED,
    STOCK_RESERVED,
    Envelope,
    PaymentFailedV1,
    PaymentRefundedV1,
    PaymentSucceededV1,
    StockReservationFailedV1,
    StockReservedV1,
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
    idempotent_handler,
)
from ecommerce_messaging.consumer import DEFAULT_RETRY
from ecommerce_observability import configure_logging
from orders.application.clock import utc_now
from orders.application.saga import OrderSaga, SagaTimeouts
from orders.infra.database import create_engine, create_session_factory
from orders.infra.models import OUTBOX
from orders.infra.unit_of_work import SqlAlchemyUnitOfWork
from orders.settings import (
    DEFAULT_SAGA_TIMEOUT_SECONDS,
    DEFAULT_SWEEP_INTERVAL_SECONDS,
    database_url_from_env,
    positive_seconds_from_env,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "orders-worker"
CONSUMER_GROUP = "orders-saga"
SAGA_TOPICS = (INVENTORY_TOPIC, PAYMENTS_TOPIC)


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_url: URL
    kafka: KafkaSettings
    saga_timeout_seconds: float = DEFAULT_SAGA_TIMEOUT_SECONDS
    sweep_interval_seconds: float = DEFAULT_SWEEP_INTERVAL_SECONDS
    log_level: str = "INFO"
    topics: Sequence[str] = SAGA_TOPICS
    group: str = CONSUMER_GROUP

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
            saga_timeout_seconds=positive_seconds_from_env(
                environ, "ORDERS_SAGA_TIMEOUT_SECONDS", DEFAULT_SAGA_TIMEOUT_SECONDS
            ),
            sweep_interval_seconds=positive_seconds_from_env(
                environ, "ORDERS_SAGA_SWEEP_INTERVAL_SECONDS", DEFAULT_SWEEP_INTERVAL_SECONDS
            ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
        )


def saga_handlers(saga: OrderSaga) -> Sequence[Handler]:
    async def on_stock_reserved(envelope: Envelope[StockReservedV1]) -> None:
        names = {line.sku: line.name for line in envelope.payload.lines}
        await saga.stock_reserved(envelope.payload.order_id, names)

    async def on_reservation_failed(envelope: Envelope[StockReservationFailedV1]) -> None:
        await saga.reservation_failed(envelope.payload.order_id, envelope.payload.reason)

    async def on_payment_succeeded(envelope: Envelope[PaymentSucceededV1]) -> None:
        await saga.payment_succeeded(envelope.payload.order_id)

    async def on_payment_failed(envelope: Envelope[PaymentFailedV1]) -> None:
        await saga.payment_failed(envelope.payload.order_id)

    async def on_payment_refunded(envelope: Envelope[PaymentRefundedV1]) -> None:
        await saga.payment_refunded(envelope.payload.order_id)

    return [
        idempotent_handler(STOCK_RESERVED, 1, StockReservedV1, on_stock_reserved),
        idempotent_handler(
            STOCK_RESERVATION_FAILED, 1, StockReservationFailedV1, on_reservation_failed
        ),
        idempotent_handler(PAYMENT_SUCCEEDED, 1, PaymentSucceededV1, on_payment_succeeded),
        idempotent_handler(PAYMENT_FAILED, 1, PaymentFailedV1, on_payment_failed),
        idempotent_handler(PAYMENT_REFUNDED, 1, PaymentRefundedV1, on_payment_refunded),
    ]


async def log_dead_letter(letter: DeadLetter) -> None:
    logger.warning(
        "saga event dead-lettered",
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


def build_consumer(
    saga: OrderSaga,
    source: MessageSource,
    dead_letters: Publisher,
    group: str = CONSUMER_GROUP,
    retry: RetryPolicy = DEFAULT_RETRY,
) -> EventConsumer:
    return EventConsumer(
        group=group,
        source=source,
        dead_letters=dead_letters,
        handlers=saga_handlers(saga),
        retry=retry,
        on_dead_letter=log_dead_letter,
    )


async def run_worker(
    settings: WorkerSettings,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = utc_now,
) -> None:
    engine = create_engine(settings.database_url)
    session_factory: async_sessionmaker[AsyncSession] = create_session_factory(engine)

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    publisher = KafkaPublisher(settings.kafka)
    source = KafkaSource(settings.kafka, list(settings.topics), settings.group)
    relay = OutboxRelay(OUTBOX, session_factory, publisher)
    consumer = build_consumer(OrderSaga(unit_of_work, clock), source, publisher, settings.group)
    timeouts = SagaTimeouts(unit_of_work, timedelta(seconds=settings.saga_timeout_seconds), clock)
    logger.info("orders worker started")
    try:
        await asyncio.gather(
            relay.run(stop),
            consumer.run(stop),
            timeouts.run(stop, settings.sweep_interval_seconds),
        )
    finally:
        await source.close()
        await publisher.close()
        await engine.dispose()
        logger.info("orders worker stopped")


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
