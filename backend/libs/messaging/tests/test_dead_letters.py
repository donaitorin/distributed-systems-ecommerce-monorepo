import io
import json
import re
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel

from ecommerce_messaging import (
    EventConsumer,
    InMemoryBroker,
    OutgoingMessage,
    RetryPolicy,
    idempotent_handler,
)
from ecommerce_messaging.dead_letters import (
    ReplayRefusedError,
    describe,
    parse_location,
    replay,
    replay_message,
    require_dead_letter_topic,
)
from ecommerce_messaging.dlq_cli import run
from ecommerce_messaging.ports import IncomingMessage

TOPIC = "orders.events"
DEAD = TOPIC + ".dlq"
EVENT_ID = str(uuid4())


class Sample(BaseModel):
    number: int


def event(event_id: str = EVENT_ID, number: object = 1) -> bytes:
    return json.dumps(
        {
            "event_id": event_id,
            "event_type": "sample.created",
            "event_version": 1,
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "correlation_id": str(uuid4()),
            "producer": "test",
            "payload": {"number": number},
        }
    ).encode()


def dead_headers(
    topic: str = TOPIC, origin_offset: int = 41, group: str = "payments-orders"
) -> dict[str, bytes]:
    return {
        "x-error": b"1 validation errors: payload.number: int_parsing",
        "x-error-type": b"ValidationError",
        "x-attempts": b"0",
        "x-original-topic": topic.encode(),
        "x-original-partition": b"2",
        "x-original-offset": str(origin_offset).encode(),
        "x-consumer-group": group.encode(),
        "trace": b"abc",
    }


async def seed(
    broker: InMemoryBroker, value: bytes, headers: dict[str, bytes] | None = None
) -> None:
    await broker.publish(OutgoingMessage(DEAD, "order-1", value, headers or dead_headers()))


class StaticReader:
    def __init__(self, broker: InMemoryBroker) -> None:
        self.broker = broker

    async def read_all(self, topic: str) -> list[IncomingMessage]:
        return self.broker.messages(topic)


async def command(broker: InMemoryBroker, *arguments: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = await run(arguments, StaticReader(broker), broker, out, err)
    return code, out.getvalue(), err.getvalue()


def test_only_dead_letter_topics_are_accepted() -> None:
    assert require_dead_letter_topic(DEAD) == DEAD
    for topic in (TOPIC, ".dlq", ""):
        with pytest.raises(ReplayRefusedError):
            require_dead_letter_topic(topic)


@pytest.mark.parametrize("raw", ["", "3", "a:1", "1:b", "-1:2", "1:2:3"])
def test_a_location_must_be_partition_and_offset(raw: str) -> None:
    with pytest.raises(ValueError, match="PARTITION:OFFSET"):
        parse_location(raw)


def test_a_location_is_parsed() -> None:
    assert parse_location("4:120") == (4, 120)


async def test_describe_reads_the_diagnostic_headers_and_the_event_identity() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    entry = describe(broker.messages(DEAD)[0])

    assert entry.summary() == {
        "partition": 0,
        "offset": 0,
        "key": "order-1",
        "event_id": EVENT_ID,
        "event_type": "sample.created",
        "original_topic": TOPIC,
        "original_partition": 2,
        "original_offset": 41,
        "group": "payments-orders",
        "error_type": "ValidationError",
        "error": "1 validation errors: payload.number: int_parsing",
        "attempts": 0,
    }


@pytest.mark.parametrize("value", [b"not json", b"[1, 2]", b'{"event_id": 7, "event_type": "x"}'])
async def test_describe_never_fails_on_a_value_that_is_not_an_event(value: bytes) -> None:
    broker = InMemoryBroker()
    await seed(broker, value)

    entry = describe(broker.messages(DEAD)[0])

    assert (entry.event_id, entry.event_type) == (None, None)


async def test_a_replayed_message_goes_to_the_original_topic_without_the_diagnostics() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    outgoing = replay_message(describe(broker.messages(DEAD)[0]))

    assert outgoing.topic == TOPIC
    assert outgoing.key == "order-1"
    assert outgoing.value == broker.messages(DEAD)[0].value
    assert dict(outgoing.headers) == {"trace": b"abc", "x-replayed-from": b"orders.events.dlq:0:0"}


async def test_a_message_without_an_original_topic_cannot_be_replayed() -> None:
    broker = InMemoryBroker()
    headers = dead_headers()
    del headers["x-original-topic"]
    await seed(broker, event(), headers)

    with pytest.raises(ReplayRefusedError, match="x-original-topic"):
        replay_message(describe(broker.messages(DEAD)[0]))


async def test_a_message_that_names_another_topic_cannot_be_replayed() -> None:
    broker = InMemoryBroker()
    await seed(broker, event(), dead_headers("payments.events"))

    with pytest.raises(ReplayRefusedError, match=re.escape("belongs to orders.events")):
        replay_message(describe(broker.messages(DEAD)[0]))


async def test_replaying_a_selection_publishes_only_what_was_chosen() -> None:
    broker = InMemoryBroker()
    for number in range(3):
        await seed(broker, event(str(uuid4()), number), dead_headers(origin_offset=number))

    code, out, _ = await command(broker, "replay", DEAD, "--offset", "0:1")

    assert code == 0
    assert out.splitlines()[0] == (
        "replayed 1 message(s) from orders.events.dlq (1 dead letters, 0 duplicates skipped)"
    )
    [replayed] = broker.messages(TOPIC)
    assert json.loads(replayed.value)["payload"] == {"number": 1}


async def test_replaying_everything_publishes_in_offset_order() -> None:
    broker = InMemoryBroker()
    for number in range(3):
        await seed(broker, event(str(uuid4()), number), dead_headers(origin_offset=number))

    code, _, _ = await command(broker, "replay", DEAD, "--all")

    assert code == 0
    numbers = [json.loads(m.value)["payload"]["number"] for m in broker.messages(TOPIC)]
    assert numbers == [0, 1, 2]


async def test_a_dry_run_publishes_nothing() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    code, out, _ = await command(broker, "replay", DEAD, "--all", "--dry-run")

    assert code == 0
    assert out.splitlines()[0] == (
        "would replay 1 message(s) from orders.events.dlq (1 dead letters, 0 duplicates skipped)"
    )
    assert broker.messages(TOPIC) == []


async def test_an_unknown_location_is_reported_and_fails() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    code, out, _ = await command(broker, "replay", DEAD, "--offset", "0:0", "--offset", "5:9")

    assert code == 1
    assert "not found: 5:9" in out
    assert len(broker.messages(TOPIC)) == 1


async def test_nothing_is_published_when_one_selected_message_cannot_be_replayed() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())
    await seed(broker, event(), dead_headers("payments.events"))

    code, _, err = await command(broker, "replay", DEAD, "--all")

    assert code == 1
    assert "belongs to orders.events" in err
    assert broker.messages(TOPIC) == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("replay", DEAD),
        ("replay", DEAD, "--all", "--offset", "0:0"),
        ("replay", TOPIC, "--all"),
        ("inspect", TOPIC),
        ("replay", DEAD, "--offset", "oops"),
    ],
)
async def test_unsafe_or_incomplete_commands_are_refused_before_reading(
    arguments: tuple[str, ...],
) -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    code, out, err = await command(broker, *arguments)

    assert code == 2
    assert out == ""
    assert err.startswith("error:")
    assert broker.messages(TOPIC) == []


async def test_an_unknown_command_exits_with_the_usage_code() -> None:
    code, _, _ = await command(InMemoryBroker(), "purge", DEAD)

    assert code == 2


async def test_inspect_lists_one_json_object_per_message_without_the_payload() -> None:
    broker = InMemoryBroker()
    await seed(broker, event(number="grace.hopper@example.com"))

    code, out, _ = await command(broker, "inspect", DEAD)

    rows: list[dict[str, Any]] = [json.loads(line) for line in out.splitlines()]
    assert code == 0
    assert len(rows) == 1
    assert rows[0]["event_type"] == "sample.created"
    assert "grace.hopper" not in out
    assert "payload_base64" not in rows[0]


async def test_inspect_can_include_the_payload_on_request() -> None:
    broker = InMemoryBroker()
    await seed(broker, event())

    _, out, _ = await command(broker, "inspect", DEAD, "--show-payload")

    assert "payload_base64" in json.loads(out)


async def test_a_dead_letter_replayed_twice_is_applied_once_by_an_idempotent_consumer() -> None:
    broker = InMemoryBroker()
    applied: list[str] = []
    processed: set[str] = set()

    async def apply(item: Any) -> None:
        if str(item.event_id) in processed:
            return
        processed.add(str(item.event_id))
        applied.append(str(item.event_id))

    consumer = EventConsumer(
        group="g",
        source=broker.source([TOPIC]),
        dead_letters=broker,
        handlers=[idempotent_handler("sample.created", 1, Sample, apply)],
        retry=RetryPolicy(max_attempts=1),
    )
    await seed(broker, event())
    await replay([describe(m) for m in broker.messages(DEAD)], broker, None)
    await replay([describe(m) for m in broker.messages(DEAD)], broker, None)
    source = broker.source([TOPIC])

    while (message := await source.poll(0)) is not None:
        await consumer.handle(message)

    assert len(broker.messages(TOPIC)) == 2
    assert applied == [EVENT_ID]


GROUPS = ("catalog-orders", "payments-order-events", "cart-order-events")


async def seed_failed_by_every_group(broker: InMemoryBroker, origin_offsets: list[int]) -> None:
    for origin_offset in origin_offsets:
        value = event(str(uuid4()), origin_offset)
        for group in GROUPS:
            await seed(broker, value, dead_headers(origin_offset=origin_offset, group=group))


async def test_a_message_dead_lettered_by_several_groups_is_replayed_once() -> None:
    broker = InMemoryBroker()
    await seed_failed_by_every_group(broker, [7, 9])

    code, out, _ = await command(broker, "replay", DEAD, "--all")

    assert code == 0
    assert len(broker.messages(DEAD)) == 6
    assert [json.loads(m.value)["payload"]["number"] for m in broker.messages(TOPIC)] == [7, 9]
    assert out.splitlines() == [
        "replayed 2 message(s) from orders.events.dlq (6 dead letters, 4 duplicates skipped)",
        "  orders.events[2]@7 failed in: cart-order-events, catalog-orders, payments-order-events",
        "  orders.events[2]@9 failed in: cart-order-events, catalog-orders, payments-order-events",
    ]


async def test_a_dry_run_reports_the_deduplicated_count_without_publishing() -> None:
    broker = InMemoryBroker()
    await seed_failed_by_every_group(broker, [7, 9])

    _, out, _ = await command(broker, "replay", DEAD, "--all", "--dry-run")

    assert out.splitlines()[0] == (
        "would replay 2 message(s) from orders.events.dlq (6 dead letters, 4 duplicates skipped)"
    )
    assert broker.messages(TOPIC) == []


async def test_selecting_several_copies_of_the_same_message_replays_it_once() -> None:
    broker = InMemoryBroker()
    await seed_failed_by_every_group(broker, [7, 9])

    code, out, _ = await command(
        broker, "replay", DEAD, "--offset", "0:0", "--offset", "0:1", "--offset", "0:3"
    )

    assert code == 0
    assert [json.loads(m.value)["payload"]["number"] for m in broker.messages(TOPIC)] == [7, 9]
    assert "(3 dead letters, 1 duplicates skipped)" in out.splitlines()[0]


async def test_the_same_offset_on_another_partition_is_a_different_message() -> None:
    broker = InMemoryBroker()
    for partition in (0, 1):
        headers = dead_headers(origin_offset=5) | {"x-original-partition": str(partition).encode()}
        await seed(broker, event(str(uuid4()), partition), headers)

    code, out, _ = await command(broker, "replay", DEAD, "--all")

    assert code == 0
    assert len(broker.messages(TOPIC)) == 2
    assert "0 duplicates skipped" in out
