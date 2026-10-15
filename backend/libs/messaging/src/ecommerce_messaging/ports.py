from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    topic: str
    key: str
    value: bytes
    headers: Mapping[str, bytes] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    topic: str
    partition: int
    offset: int
    key: str | None
    value: bytes
    headers: Mapping[str, bytes] = field(default_factory=dict)


class Publisher(Protocol):
    async def publish(self, message: OutgoingMessage) -> None: ...

    async def close(self) -> None: ...


class MessageSource(Protocol):
    async def poll(self, timeout_seconds: float) -> IncomingMessage | None: ...

    async def commit(self, message: IncomingMessage) -> None: ...

    async def close(self) -> None: ...
