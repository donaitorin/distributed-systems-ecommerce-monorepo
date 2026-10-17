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

from ecommerce_contracts import (
    ORDER_CANCELLED,
    ORDER_PAYMENT_REQUESTED,
    ORDERS_TOPIC,
    Envelope,
    OrderCancelledV1,
    OrderPaymentRequestedV1,
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
from payments.application.clock import utc_now
from payments.application.ports import PaymentProvider
from payments.application.processor import PaymentProcessor
from payments.infra.database import create_engine, create_session_factory
from payments.infra.models import OUTBOX
from payments.infra.simulated import SimulatedPaymentProvider
from payments.infra.unit_of_work import SqlAlchemyUnitOfWork
from payments.settings import (
    DEFAULT_LATE_APPROVAL_DELAY_SECONDS,
    DEFAULT_SETTLE_INTERVAL_SECONDS,
    database_url_from_env,
    positive_seconds_from_env,
)

logger = logging.getLogger(__name__)

SERVICE_NAME = "payments-worker"
CONSUMER_GROUP = "payments-order-events"


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    database_url: URL
    kafka: KafkaSettings
    late_approval_delay_seconds: float = DEFAULT_LATE_APPROVAL_DELAY_SECONDS
    settle_interval_seconds: float = DEFAULT_SETTLE_INTERVAL_SECONDS
    log_level: str = "INFO"
    topic: str = ORDERS_TOPIC
    group: str = CONSUMER_GROUP

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Self:
        return cls(
            database_url=database_url_from_env(environ),
            kafka=KafkaSettings.from_env(environ, SERVICE_NAME),
            late_approval_delay_seconds=positive_seconds_from_env(
                environ,
                "PAYMENT_LATE_APPROVAL_DELAY_SECONDS",
                DEFAULT_LATE_APPROVAL_DELAY_SECONDS,
            ),
            settle_interval_seconds=positive_seconds_from_env(
                environ, "PAYMENTS_SETTLE_INTERVAL_SECONDS", DEFAULT_SETTLE_INTERVAL_SECONDS
            ),
            log_level=environ.get("LOG_LEVEL", "INFO"),
        )


def order_handlers(processor: PaymentProcessor) -> Sequence[Handler]:
    async def on_payment_requested(envelope: Envelope[OrderPaymentRequestedV1]) -> None:
        await processor.charge_requested(envelope.payload, envelope.correlation_id)

    async def on_cancelled(envelope: Envelope[OrderCancelledV1]) -> None:
        await processor.order_cancelled(envelope.payload.order_id)

    return [
        idempotent_handler(
            ORDER_PAYMENT_REQUESTED, 1, OrderPaymentRequestedV1, on_payment_requested
        ),
        idempotent_handler(ORDER_CANCELLED, 1, OrderCancelledV1, on_cancelled),
    ]


async def log_dead_letter(letter: DeadLetter) -> None:
    logger.warning(
        "order event dead-lettered",
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
    processor: PaymentProcessor,
    source: MessageSource,
    dead_letters: Publisher,
    group: str = CONSUMER_GROUP,
    retry: RetryPolicy = DEFAULT_RETRY,
) -> EventConsumer:
    return EventConsumer(
        group=group,
        source=source,
        dead_letters=dead_letters,
        handlers=order_handlers(processor),
        retry=retry,
        on_dead_letter=log_dead_letter,
    )


async def run_settlement(
    processor: PaymentProcessor, stop: asyncio.Event, interval_seconds: float
) -> None:
    while not stop.is_set():
        try:
            await processor.settle_due()
            await processor.refund_due()
        except Exception:
            logger.exception("payment settlement pass failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), interval_seconds)


async def run_worker(
    settings: WorkerSettings,
    stop: asyncio.Event,
    clock: Callable[[], datetime] = utc_now,
    provider: PaymentProvider | None = None,
) -> None:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    chosen = provider or SimulatedPaymentProvider(
        timedelta(seconds=settings.late_approval_delay_seconds), clock
    )
    processor = PaymentProcessor(lambda: SqlAlchemyUnitOfWork(session_factory), chosen, clock)
    publisher = KafkaPublisher(settings.kafka)
    source = KafkaSource(settings.kafka, [settings.topic], settings.group)
    relay = OutboxRelay(OUTBOX, session_factory, publisher)
    consumer = build_consumer(processor, source, publisher, settings.group)
    logger.info("payments worker started")
    try:
        await asyncio.gather(
            relay.run(stop),
            consumer.run(stop),
            run_settlement(processor, stop, settings.settle_interval_seconds),
        )
    finally:
        await source.close()
        await publisher.close()
        await engine.dispose()
        logger.info("payments worker stopped")


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
