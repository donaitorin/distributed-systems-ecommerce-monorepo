import json
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ecommerce_contracts import Envelope
from ecommerce_messaging import (
    DeadLetter,
    EventConsumer,
    InMemoryBroker,
    InMemorySource,
    Outcome,
    OutgoingMessage,
    RetryPolicy,
    idempotent_handler,
)
from ecommerce_messaging.safe_errors import describe_error

TOPIC = "sample.events"
CORRELATION = UUID("0c5a9d86-2c8e-4d7e-a0a3-5b6c1b8f2d44")
SECRET_EMAIL = "grace.hopper@example.com"
SECRET_CARD = "4111111111111111"
SECRETS = (SECRET_EMAIL, SECRET_CARD, "grace.hopper")


class Sample(BaseModel):
    number: int


def valid_event(**payload: Any) -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "event_type": "sample.created",
        "event_version": 1,
        "occurred_at": "2026-01-01T00:00:00+00:00",
        "correlation_id": str(CORRELATION),
        "producer": "test",
        "payload": {"number": 1, **payload},
    }


def encode(document: dict[str, Any]) -> bytes:
    return json.dumps(document).encode()


class Harness:
    def __init__(self, handler_error: Exception | None = None) -> None:
        self.broker = InMemoryBroker()
        self.source: InMemorySource = self.broker.source([TOPIC])
        self.handler_error = handler_error
        self.hook_error: Exception | None = None
        self.letters: list[DeadLetter] = []

    async def handle_sample(self, item: Envelope[Sample]) -> None:
        if self.handler_error is not None:
            raise self.handler_error

    async def sleep(self, seconds: float) -> None:
        return None

    async def hook(self, letter: DeadLetter) -> None:
        self.letters.append(letter)
        if self.hook_error is not None:
            raise self.hook_error

    def consumer(self) -> EventConsumer:
        return EventConsumer(
            group="group-a",
            source=self.source,
            dead_letters=self.broker,
            handlers=[idempotent_handler("sample.created", 1, Sample, self.handle_sample)],
            retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.1, max_delay_seconds=0.1),
            on_dead_letter=self.hook,
            sleep=self.sleep,
        )

    async def deliver(self, value: bytes) -> Outcome:
        await self.broker.publish(OutgoingMessage(TOPIC, "key", value))
        message = await self.source.poll(0)
        assert message is not None
        return await self.consumer().handle(message)


def everything_logged(records: list[logging.LogRecord]) -> str:
    formatter = logging.Formatter()
    parts: list[str] = []
    for record in records:
        parts.append(formatter.format(record))
        parts.append(json.dumps(record.__dict__, default=str))
    return "\n".join(parts)


def everything_dead_lettered(harness: Harness) -> str:
    parts: list[str] = []
    for message in harness.broker.messages(TOPIC + ".dlq"):
        parts.extend(value.decode(errors="replace") for value in message.headers.values())
    for letter in harness.letters:
        parts.extend([letter.error, letter.error_type])
    return "\n".join(parts)


MALFORMED: dict[str, Callable[[], bytes]] = {
    "not-json": lambda: f'{{"email": "{SECRET_EMAIL}", "card": "{SECRET_CARD}", '.encode(),
    "bad-envelope-fields": lambda: encode(
        valid_event() | {"event_id": SECRET_EMAIL, "event_version": SECRET_CARD}
    ),
    "bad-payload": lambda: encode(valid_event(number=SECRET_EMAIL, card=SECRET_CARD)),
    "unsupported-version": lambda: encode(
        valid_event(email=SECRET_EMAIL, card=SECRET_CARD) | {"event_version": 9}
    ),
    "payload-as-string": lambda: encode(
        valid_event() | {"payload": f"{SECRET_EMAIL} {SECRET_CARD}"}
    ),
}


@pytest.mark.parametrize("name", MALFORMED)
async def test_a_malformed_payload_leaks_nothing_into_logs_or_dead_letter_headers(
    name: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = Harness()

    outcome = await harness.deliver(MALFORMED[name]())

    assert outcome is Outcome.DEAD_LETTERED
    logged = everything_logged(caplog.records)
    headers = everything_dead_lettered(harness)
    for secret in SECRETS:
        assert secret not in logged
        assert secret not in headers


async def test_a_handler_error_that_quotes_the_payload_leaks_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = Harness(ValueError(f"cannot charge {SECRET_CARD} for {SECRET_EMAIL}"))

    outcome = await harness.deliver(encode(valid_event(email=SECRET_EMAIL)))

    assert outcome is Outcome.DEAD_LETTERED
    for secret in SECRETS:
        assert secret not in everything_logged(caplog.records)
        assert secret not in everything_dead_lettered(harness)


async def test_a_failing_dead_letter_hook_leaks_nothing(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    harness = Harness()
    harness.hook_error = RuntimeError(f"hook saw {SECRET_EMAIL} {SECRET_CARD}")

    await harness.deliver(MALFORMED["bad-payload"]())

    assert harness.letters
    for secret in SECRETS:
        assert secret not in everything_logged(caplog.records)


async def test_the_dead_letter_log_keeps_the_identifying_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    harness = Harness(ValueError(SECRET_EMAIL))
    document = valid_event()

    await harness.deliver(encode(document))

    [record] = [r for r in caplog.records if r.getMessage().startswith("event moved")]
    fields = {
        "event_id": document["event_id"],
        "event_type": "sample.created",
        "error_type": "ValueError",
        "topic": TOPIC,
        "partition": 0,
        "offset": 0,
        "attempts": 2,
        "dead_letter_topic": TOPIC + ".dlq",
    }
    assert {name: record.__dict__[name] for name in fields} == fields


async def test_the_error_summary_of_a_validation_error_names_fields_and_types_only() -> None:
    with pytest.raises(ValidationError) as caught:
        Sample.model_validate({"number": SECRET_EMAIL})

    summary = describe_error(caught.value)

    assert summary == "1 validation errors: number: int_parsing"


async def test_a_long_validation_error_is_truncated() -> None:
    class Wide(BaseModel):
        a: int
        b: int
        c: int
        d: int
        e: int
        f: int
        g: int

    with pytest.raises(ValidationError) as caught:
        Wide.model_validate(dict.fromkeys("abcdefg", "x"))

    assert describe_error(caught.value).endswith("(+2 more)")


async def test_an_error_without_a_safe_summary_is_reduced_to_its_type() -> None:
    assert describe_error(KeyError(SECRET_EMAIL)) == "KeyError raised while handling the event"
