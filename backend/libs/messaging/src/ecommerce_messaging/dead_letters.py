import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from ecommerce_contracts.envelope import EVENT_TYPE_PATTERN
from ecommerce_messaging.consumer import (
    DEAD_LETTER_SUFFIX,
    HEADER_ATTEMPTS,
    HEADER_ERROR,
    HEADER_ERROR_TYPE,
    HEADER_GROUP,
    HEADER_ORIGINAL_OFFSET,
    HEADER_ORIGINAL_PARTITION,
    HEADER_ORIGINAL_TOPIC,
)
from ecommerce_messaging.ports import IncomingMessage, OutgoingMessage, Publisher

HEADER_REPLAYED_FROM: Final = "x-replayed-from"
DIAGNOSTIC_HEADERS: Final = frozenset(
    {
        HEADER_ERROR,
        HEADER_ERROR_TYPE,
        HEADER_ATTEMPTS,
        HEADER_ORIGINAL_TOPIC,
        HEADER_ORIGINAL_PARTITION,
        HEADER_ORIGINAL_OFFSET,
        HEADER_GROUP,
        HEADER_REPLAYED_FROM,
    }
)
_EVENT_TYPE: Final = re.compile(EVENT_TYPE_PATTERN)

type Location = tuple[int, int]


class ReplayRefusedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeadLetterEntry:
    message: IncomingMessage
    original_topic: str | None
    original_partition: int | None
    original_offset: int | None
    group: str | None
    error_type: str | None
    error: str | None
    attempts: int | None
    event_id: str | None
    event_type: str | None

    @property
    def location(self) -> Location:
        return (self.message.partition, self.message.offset)

    def summary(self) -> dict[str, Any]:
        return {
            "partition": self.message.partition,
            "offset": self.message.offset,
            "key": self.message.key,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "original_topic": self.original_topic,
            "original_partition": self.original_partition,
            "original_offset": self.original_offset,
            "group": self.group,
            "error_type": self.error_type,
            "error": self.error,
            "attempts": self.attempts,
        }


@dataclass(frozen=True, slots=True)
class ReplayReport:
    replayed: tuple[Location, ...]
    missing: tuple[Location, ...]


def require_dead_letter_topic(topic: str) -> str:
    if not topic.endswith(DEAD_LETTER_SUFFIX) or topic == DEAD_LETTER_SUFFIX:
        raise ReplayRefusedError(
            f"{topic} is not a dead letter topic (expected *{DEAD_LETTER_SUFFIX})"
        )
    return topic


def parse_location(raw: str) -> Location:
    partition, separator, offset = raw.partition(":")
    if not separator or not partition.isdigit() or not offset.isdigit():
        raise ValueError(f"expected PARTITION:OFFSET, got {raw!r}")
    return int(partition), int(offset)


def describe(message: IncomingMessage) -> DeadLetterEntry:
    event_id, event_type = _identity(message.value)
    return DeadLetterEntry(
        message=message,
        original_topic=_text(message.headers, HEADER_ORIGINAL_TOPIC),
        original_partition=_number(message.headers, HEADER_ORIGINAL_PARTITION),
        original_offset=_number(message.headers, HEADER_ORIGINAL_OFFSET),
        group=_text(message.headers, HEADER_GROUP),
        error_type=_text(message.headers, HEADER_ERROR_TYPE),
        error=_text(message.headers, HEADER_ERROR),
        attempts=_number(message.headers, HEADER_ATTEMPTS),
        event_id=event_id,
        event_type=event_type,
    )


def replay_message(entry: DeadLetterEntry) -> OutgoingMessage:
    message = entry.message
    expected = message.topic.removesuffix(DEAD_LETTER_SUFFIX)
    if entry.original_topic is None:
        raise ReplayRefusedError(f"{_where(entry)} has no {HEADER_ORIGINAL_TOPIC} header")
    if entry.original_topic != expected:
        raise ReplayRefusedError(
            f"{_where(entry)} names {entry.original_topic} but belongs to {expected}"
        )
    headers = {
        name: value for name, value in message.headers.items() if name not in DIAGNOSTIC_HEADERS
    }
    headers[HEADER_REPLAYED_FROM] = f"{message.topic}:{message.partition}:{message.offset}".encode()
    return OutgoingMessage(expected, message.key or "", message.value, headers)


async def replay(
    entries: Iterable[DeadLetterEntry],
    publisher: Publisher,
    selected: set[Location] | None,
    dry_run: bool = False,
) -> ReplayReport:
    available = {entry.location: entry for entry in entries}
    wanted = sorted(available) if selected is None else sorted(selected)
    outgoing = [
        (location, replay_message(available[location]))
        for location in wanted
        if location in available
    ]
    if not dry_run:
        for _, message in outgoing:
            await publisher.publish(message)
    return ReplayReport(
        replayed=tuple(location for location, _ in outgoing),
        missing=tuple(location for location in wanted if location not in available),
    )


def _where(entry: DeadLetterEntry) -> str:
    return f"{entry.message.topic}[{entry.message.partition}]@{entry.message.offset}"


def _text(headers: Mapping[str, bytes], name: str) -> str | None:
    raw = headers.get(name)
    return raw.decode(errors="replace") if raw is not None else None


def _number(headers: Mapping[str, bytes], name: str) -> int | None:
    text = _text(headers, name)
    return int(text) if text is not None and text.isdigit() else None


def _identity(value: bytes) -> tuple[str | None, str | None]:
    try:
        document = json.loads(value)
    except ValueError:
        return None, None
    if not isinstance(document, dict):
        return None, None
    return _event_id(document.get("event_id")), _event_type(document.get("event_type"))


def _event_id(candidate: object) -> str | None:
    if not isinstance(candidate, str):
        return None
    try:
        return str(UUID(candidate))
    except ValueError:
        return None


def _event_type(candidate: object) -> str | None:
    if isinstance(candidate, str) and _EVENT_TYPE.match(candidate):
        return candidate
    return None
