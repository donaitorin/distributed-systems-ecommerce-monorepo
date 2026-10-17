import io
import json
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from ecommerce_messaging import KafkaPublisher, KafkaSettings, OutgoingMessage
from ecommerce_messaging.dlq_cli import run
from ecommerce_messaging.topic_reader import KafkaTopicReader
from kafka_support import KafkaBroker

pytestmark = pytest.mark.integration

COUNT = 7


@pytest.fixture
async def publisher(kafka: KafkaBroker) -> AsyncIterator[KafkaPublisher]:
    prepared = KafkaPublisher(
        KafkaSettings(kafka.bootstrap, "dlq-test", publish_timeout_seconds=10)
    )
    yield prepared
    await prepared.close()


def dead_letter(topic: str, number: int) -> OutgoingMessage:
    headers = {
        "x-error": b"1 validation errors: payload.number: int_parsing",
        "x-error-type": b"ValidationError",
        "x-attempts": b"0",
        "x-original-topic": topic.removesuffix(".dlq").encode(),
        "x-original-partition": b"0",
        "x-original-offset": str(number).encode(),
        "x-consumer-group": b"test-group",
    }
    value = json.dumps({"event_id": str(uuid4()), "event_type": "sample.created", "n": number})
    return OutgoingMessage(topic, f"key-{number}", value.encode(), headers)


async def test_the_reader_returns_every_message_of_every_partition(
    kafka: KafkaBroker, publisher: KafkaPublisher
) -> None:
    topic = f"orders.events.{uuid4().hex}.dlq"
    for number in range(COUNT):
        await publisher.publish(dead_letter(topic, number))
    reader = KafkaTopicReader(KafkaSettings(kafka.bootstrap, "dlq-test"))

    messages = await reader.read_all(topic)

    assert sorted(json.loads(m.value)["n"] for m in messages) == list(range(COUNT))
    assert {m.headers["x-error-type"] for m in messages} == {b"ValidationError"}


async def test_the_reader_returns_nothing_for_a_topic_that_does_not_exist(
    kafka: KafkaBroker,
) -> None:
    reader = KafkaTopicReader(KafkaSettings(kafka.bootstrap, "dlq-test"))

    assert await reader.read_all(f"missing.{uuid4().hex}.dlq") == []


async def test_a_selected_dead_letter_is_replayed_to_its_original_topic(
    kafka: KafkaBroker, publisher: KafkaPublisher
) -> None:
    base = f"orders.events.{uuid4().hex}"
    for number in range(COUNT):
        await publisher.publish(dead_letter(base + ".dlq", number))
    reader = KafkaTopicReader(KafkaSettings(kafka.bootstrap, "dlq-test"))
    [chosen, *_] = await reader.read_all(base + ".dlq")
    out, err = io.StringIO(), io.StringIO()

    code = await run(
        ["replay", base + ".dlq", "--offset", f"{chosen.partition}:{chosen.offset}"],
        reader,
        publisher,
        out,
        err,
    )

    assert (code, err.getvalue()) == (0, "")
    [replayed] = await reader.read_all(base)
    assert replayed.value == chosen.value
    assert replayed.headers["x-replayed-from"] == (
        f"{base}.dlq:{chosen.partition}:{chosen.offset}".encode()
    )
    assert "x-error" not in replayed.headers
