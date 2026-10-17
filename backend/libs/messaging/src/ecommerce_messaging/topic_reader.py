import asyncio

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import KafkaError

from ecommerce_messaging.errors import ConsumeError
from ecommerce_messaging.kafka import stop_consumer_quietly
from ecommerce_messaging.ports import IncomingMessage
from ecommerce_messaging.settings import KafkaSettings

READ_ALL_TIMEOUT_SECONDS = 60


class KafkaTopicReader:
    def __init__(self, settings: KafkaSettings) -> None:
        self._settings = settings

    async def read_all(self, topic: str) -> list[IncomingMessage]:
        consumer = AIOKafkaConsumer(
            bootstrap_servers=self._settings.bootstrap_servers,
            client_id=self._settings.client_id,
            group_id=None,
            enable_auto_commit=False,
        )
        try:
            await asyncio.wait_for(consumer.start(), timeout=self._settings.publish_timeout_seconds)
            async with asyncio.timeout(READ_ALL_TIMEOUT_SECONDS):
                return await self._drain(consumer, topic)
        except (KafkaError, TimeoutError, OSError) as error:
            raise ConsumeError(f"could not read {topic}: {type(error).__name__}") from error
        finally:
            await stop_consumer_quietly(consumer)

    async def _partition_numbers(self, topic: str) -> list[int]:
        admin = AIOKafkaAdminClient(
            bootstrap_servers=self._settings.bootstrap_servers, client_id=self._settings.client_id
        )
        await admin.start()
        try:
            described = await admin.describe_topics([topic])
        finally:
            await admin.close()
        return sorted(
            partition["partition"]
            for entry in described
            if entry["error_code"] == 0
            for partition in entry["partitions"]
        )

    async def _drain(self, consumer: AIOKafkaConsumer, topic: str) -> list[IncomingMessage]:
        partitions = [
            TopicPartition(topic, number) for number in await self._partition_numbers(topic)
        ]
        if not partitions:
            return []
        consumer.assign(partitions)
        await consumer.seek_to_beginning(*partitions)
        ends = await consumer.end_offsets(partitions)
        messages: list[IncomingMessage] = []
        for partition in partitions:
            while await consumer.position(partition) < ends[partition]:
                batches = await consumer.getmany(partition, timeout_ms=1000)
                for record in batches.get(partition, ()):
                    key = record.key.decode() if record.key is not None else None
                    messages.append(
                        IncomingMessage(
                            record.topic,
                            record.partition,
                            record.offset,
                            key,
                            record.value,
                            dict(record.headers or ()),
                        )
                    )
        return messages
