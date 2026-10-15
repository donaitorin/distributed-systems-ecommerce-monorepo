import asyncio
import logging
from collections.abc import Sequence

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.errors import KafkaError

from ecommerce_messaging.errors import ConsumeError, PublishError
from ecommerce_messaging.ports import IncomingMessage, OutgoingMessage
from ecommerce_messaging.settings import KafkaSettings

logger = logging.getLogger(__name__)


class KafkaPublisher:
    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None
        self._lock = asyncio.Lock()

    async def publish(self, message: OutgoingMessage) -> None:
        producer = await self._started()
        headers = [(name, value) for name, value in message.headers.items()]
        try:
            await asyncio.wait_for(
                producer.send_and_wait(
                    message.topic,
                    value=message.value,
                    key=message.key.encode(),
                    headers=headers,
                ),
                timeout=self._settings.publish_timeout_seconds,
            )
        except (KafkaError, TimeoutError, OSError) as error:
            await self._discard()
            raise PublishError(f"could not publish to {message.topic}: {error!r}") from error

    async def close(self) -> None:
        await self._discard()

    async def _started(self) -> AIOKafkaProducer:
        async with self._lock:
            if self._producer is None:
                producer = AIOKafkaProducer(
                    bootstrap_servers=self._settings.bootstrap_servers,
                    client_id=self._settings.client_id,
                    acks="all",
                    enable_idempotence=True,
                    request_timeout_ms=int(self._settings.publish_timeout_seconds * 1000),
                )
                try:
                    await asyncio.wait_for(
                        producer.start(), timeout=self._settings.publish_timeout_seconds
                    )
                except (KafkaError, TimeoutError, OSError) as error:
                    await _stop_quietly(producer)
                    raise PublishError(f"could not connect to Kafka: {error!r}") from error
                self._producer = producer
            return self._producer

    async def _discard(self) -> None:
        async with self._lock:
            producer, self._producer = self._producer, None
        if producer is not None:
            await _stop_quietly(producer)


async def _stop_quietly(producer: AIOKafkaProducer) -> None:
    try:
        await asyncio.wait_for(producer.stop(), timeout=5)
    except (KafkaError, TimeoutError, OSError, RuntimeError):
        logger.debug("kafka producer did not stop cleanly", exc_info=True)


class KafkaSource:
    def __init__(self, settings: KafkaSettings, topics: Sequence[str], group: str) -> None:
        self._settings = settings
        self._topics = list(topics)
        self._group = group
        self._consumer: AIOKafkaConsumer | None = None
        self._lock = asyncio.Lock()

    async def poll(self, timeout_seconds: float) -> IncomingMessage | None:
        consumer = await self._started()
        try:
            batches = await consumer.getmany(timeout_ms=int(timeout_seconds * 1000), max_records=1)
        except (KafkaError, OSError) as error:
            await self._discard()
            raise ConsumeError(f"could not read from Kafka: {error!r}") from error
        for records in batches.values():
            for record in records:
                headers = dict(record.headers or ())
                key = record.key.decode() if record.key is not None else None
                return IncomingMessage(
                    record.topic, record.partition, record.offset, key, record.value, headers
                )
        return None

    async def commit(self, message: IncomingMessage) -> None:
        consumer = await self._started()
        partition = TopicPartition(message.topic, message.partition)
        try:
            await consumer.commit({partition: message.offset + 1})
        except (KafkaError, OSError) as error:
            await self._discard()
            raise ConsumeError(f"could not commit offset: {error!r}") from error

    async def close(self) -> None:
        await self._discard()

    async def _started(self) -> AIOKafkaConsumer:
        async with self._lock:
            if self._consumer is None:
                consumer = AIOKafkaConsumer(
                    *self._topics,
                    bootstrap_servers=self._settings.bootstrap_servers,
                    client_id=self._settings.client_id,
                    group_id=self._group,
                    enable_auto_commit=False,
                    auto_offset_reset="earliest",
                    max_poll_interval_ms=self._settings.max_poll_interval_ms,
                )
                try:
                    await asyncio.wait_for(
                        consumer.start(), timeout=self._settings.publish_timeout_seconds
                    )
                except (KafkaError, TimeoutError, OSError) as error:
                    await _stop_consumer_quietly(consumer)
                    raise ConsumeError(f"could not connect to Kafka: {error!r}") from error
                self._consumer = consumer
            return self._consumer

    async def _discard(self) -> None:
        async with self._lock:
            consumer, self._consumer = self._consumer, None
        if consumer is not None:
            await _stop_consumer_quietly(consumer)


async def _stop_consumer_quietly(consumer: AIOKafkaConsumer) -> None:
    try:
        await asyncio.wait_for(consumer.stop(), timeout=5)
    except (KafkaError, TimeoutError, OSError, RuntimeError):
        logger.debug("kafka consumer did not stop cleanly", exc_info=True)
