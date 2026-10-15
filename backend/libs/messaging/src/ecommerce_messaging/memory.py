import asyncio
from collections import defaultdict
from collections.abc import Sequence

from ecommerce_messaging.errors import PublishError
from ecommerce_messaging.ports import IncomingMessage, OutgoingMessage

IDLE_POLL_SECONDS = 0.01


class InMemoryBroker:
    def __init__(self) -> None:
        self.available = True
        self._topics: dict[str, list[IncomingMessage]] = defaultdict(list)
        self.published: list[OutgoingMessage] = []

    async def publish(self, message: OutgoingMessage) -> None:
        if not self.available:
            raise PublishError("broker is unavailable")
        log = self._topics[message.topic]
        log.append(
            IncomingMessage(message.topic, 0, len(log), message.key, message.value, message.headers)
        )
        self.published.append(message)

    async def close(self) -> None:
        return None

    def messages(self, topic: str) -> list[IncomingMessage]:
        return list(self._topics[topic])

    def source(self, topics: Sequence[str]) -> "InMemorySource":
        return InMemorySource(self, topics)


class InMemorySource:
    def __init__(self, broker: InMemoryBroker, topics: Sequence[str]) -> None:
        self._broker = broker
        self._topics = list(topics)
        self._position: dict[str, int] = dict.fromkeys(self._topics, 0)
        self._committed: dict[str, int] = dict.fromkeys(self._topics, 0)
        self.commits: list[IncomingMessage] = []

    async def poll(self, timeout_seconds: float) -> IncomingMessage | None:
        for topic in self._topics:
            log = self._broker.messages(topic)
            if self._position[topic] < len(log):
                message = log[self._position[topic]]
                self._position[topic] += 1
                return message
        await asyncio.sleep(min(timeout_seconds, IDLE_POLL_SECONDS))
        return None

    async def commit(self, message: IncomingMessage) -> None:
        self._committed[message.topic] = max(self._committed[message.topic], message.offset + 1)
        self.commits.append(message)

    async def close(self) -> None:
        return None

    def restart(self) -> None:
        self._position = dict(self._committed)
