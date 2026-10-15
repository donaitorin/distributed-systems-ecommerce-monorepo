import asyncio
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Table, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ecommerce_contracts import Envelope
from ecommerce_messaging.ports import IncomingMessage, MessageSource, OutgoingMessage, Publisher

logger = logging.getLogger(__name__)

DEAD_LETTER_SUFFIX: Final = ".dlq"
DEFAULT_POLL_TIMEOUT_SECONDS: Final = 1.0
MAX_LOOP_BACKOFF_SECONDS: Final = 10.0
HEADER_ERROR: Final = "x-error"
HEADER_ERROR_TYPE: Final = "x-error-type"
HEADER_ATTEMPTS: Final = "x-attempts"
HEADER_ORIGINAL_TOPIC: Final = "x-original-topic"
HEADER_ORIGINAL_PARTITION: Final = "x-original-partition"
HEADER_ORIGINAL_OFFSET: Final = "x-original-offset"
HEADER_GROUP: Final = "x-consumer-group"
ERROR_LIMIT: Final = 500

type Callback = Callable[[Envelope[Any], AsyncSession | None], Awaitable[None]]
type DeadLetterHook = Callable[["DeadLetter"], Awaitable[None]]
type Sleeper = Callable[[float], Awaitable[None]]


class ClaimMode(StrEnum):
    WITH_HANDLER = "with_handler"
    AFTER_HANDLER = "after_handler"


class Outcome(StrEnum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"
    DEAD_LETTERED = "dead_lettered"


class InvalidEventError(ValueError):
    pass


class AnyPayload(BaseModel):
    model_config = ConfigDict(extra="allow")


@dataclass(frozen=True, slots=True)
class Handler:
    event_type: str
    version: int
    payload: type[BaseModel]
    callback: Callback
    claim: ClaimMode


def transactional_handler[PayloadT: BaseModel](
    event_type: str,
    version: int,
    payload: type[PayloadT],
    callback: Callable[[Envelope[PayloadT], AsyncSession], Awaitable[None]],
) -> Handler:
    async def run(envelope: Envelope[Any], session: AsyncSession | None) -> None:
        assert session is not None
        await callback(envelope, session)

    return Handler(event_type, version, payload, run, ClaimMode.WITH_HANDLER)


def standalone_handler[PayloadT: BaseModel](
    event_type: str,
    version: int,
    payload: type[PayloadT],
    callback: Callable[[Envelope[PayloadT]], Awaitable[None]],
) -> Handler:
    async def run(envelope: Envelope[Any], session: AsyncSession | None) -> None:
        await callback(envelope)

    return Handler(event_type, version, payload, run, ClaimMode.AFTER_HANDLER)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def delay(self, attempt: int) -> float:
        return float(min(self.base_delay_seconds * 2 ** (attempt - 1), self.max_delay_seconds))


@dataclass(frozen=True, slots=True)
class DeadLetter:
    message: IncomingMessage
    envelope: Envelope[Any] | None
    error: str
    error_type: str
    attempts: int
    group: str


DEFAULT_RETRY: Final = RetryPolicy()


class EventConsumer:
    def __init__(
        self,
        *,
        group: str,
        source: MessageSource,
        dead_letters: Publisher,
        session_factory: async_sessionmaker[AsyncSession],
        processed_events: Table,
        handlers: Sequence[Handler],
        retry: RetryPolicy = DEFAULT_RETRY,
        on_dead_letter: DeadLetterHook | None = None,
        sleep: Sleeper = asyncio.sleep,
        poll_timeout_seconds: float = DEFAULT_POLL_TIMEOUT_SECONDS,
    ) -> None:
        self._group = group
        self._source = source
        self._dead_letters = dead_letters
        self._sessions = session_factory
        self._processed = processed_events
        self._retry = retry
        self._on_dead_letter = on_dead_letter
        self._sleep = sleep
        self._poll_timeout = poll_timeout_seconds
        self._handlers: dict[tuple[str, int], Handler] = {}
        for handler in handlers:
            identity = (handler.event_type, handler.version)
            if identity in self._handlers:
                raise ValueError(f"handler registered twice for {identity}")
            self._handlers[identity] = handler
        self._types = {event_type for event_type, _ in self._handlers}

    async def run(self, stop: asyncio.Event) -> None:
        backoff = 0.5
        while not stop.is_set():
            try:
                message = await self._source.poll(self._poll_timeout)
                if message is None:
                    continue
                await self.handle(message, stop)
                backoff = 0.5
            except Exception as error:
                logger.warning(
                    "event consumer will retry after an error",
                    extra={"group": self._group, "error": repr(error), "retry_in": backoff},
                )
                await self._sleep(backoff)
                backoff = min(backoff * 2, MAX_LOOP_BACKOFF_SECONDS)

    async def handle(self, message: IncomingMessage, stop: asyncio.Event | None = None) -> Outcome:
        outcome = await self._process(message, stop or asyncio.Event())
        await self._source.commit(message)
        return outcome

    async def _process(self, message: IncomingMessage, stop: asyncio.Event) -> Outcome:
        try:
            head, handler = self._route(message)
        except InvalidEventError as error:
            await self._dead_letter(message, None, error, 0, stop)
            return Outcome.DEAD_LETTERED
        if handler is None or head is None:
            return Outcome.IGNORED
        try:
            envelope = self._typed(head, handler)
        except (ValidationError, ValueError) as error:
            await self._dead_letter(message, head, error, 0, stop)
            return Outcome.DEAD_LETTERED
        last_error: Exception | None = None
        for attempt in range(1, self._retry.max_attempts + 1):
            try:
                return await self._run_handler(handler, envelope)
            except Exception as error:
                last_error = error
                logger.warning(
                    "event handler failed",
                    extra={
                        "group": self._group,
                        "event_type": envelope.event_type,
                        "event_id": str(envelope.event_id),
                        "attempt": attempt,
                        "error": repr(error),
                    },
                )
                if attempt < self._retry.max_attempts:
                    await self._sleep(self._retry.delay(attempt))
        assert last_error is not None
        await self._dead_letter(message, envelope, last_error, self._retry.max_attempts, stop)
        return Outcome.DEAD_LETTERED

    def _route(self, message: IncomingMessage) -> tuple[Envelope[Any] | None, Handler | None]:
        try:
            head = Envelope[AnyPayload].model_validate_json(message.value)
        except (ValidationError, json.JSONDecodeError, ValueError) as error:
            raise InvalidEventError(f"not a valid event envelope: {error}") from error
        handler = self._handlers.get((head.event_type, head.event_version))
        if handler is not None:
            return head, handler
        if head.event_type in self._types:
            raise InvalidEventError(
                f"unsupported version {head.event_version} of {head.event_type}"
            )
        return None, None

    @staticmethod
    def _typed(head: Envelope[Any], handler: Handler) -> Envelope[Any]:
        payload = handler.payload.model_validate(head.payload.model_dump())
        typed: Envelope[Any] = head.model_copy(update={"payload": payload})
        return typed

    async def _run_handler(self, handler: Handler, envelope: Envelope[Any]) -> Outcome:
        if handler.claim is ClaimMode.WITH_HANDLER:
            async with self._sessions() as session, session.begin():
                if not await self._claim(session, envelope.event_id):
                    return Outcome.DUPLICATE
                await handler.callback(envelope, session)
            return Outcome.PROCESSED
        async with self._sessions() as session:
            if await self._already_processed(session, envelope.event_id):
                return Outcome.DUPLICATE
        await handler.callback(envelope, None)
        async with self._sessions() as session, session.begin():
            await self._claim(session, envelope.event_id)
        return Outcome.PROCESSED

    async def _claim(self, session: AsyncSession, event_id: UUID) -> bool:
        statement = (
            pg_insert(self._processed)
            .values(consumer_group=self._group, event_id=event_id)
            .on_conflict_do_nothing()
            .returning(self._processed.c.event_id)
        )
        return (await session.execute(statement)).scalar_one_or_none() is not None

    async def _already_processed(self, session: AsyncSession, event_id: UUID) -> bool:
        statement = select(self._processed.c.event_id).where(
            self._processed.c.consumer_group == self._group,
            self._processed.c.event_id == event_id,
        )
        return (await session.execute(statement)).first() is not None

    async def _dead_letter(
        self,
        message: IncomingMessage,
        envelope: Envelope[Any] | None,
        error: Exception,
        attempts: int,
        stop: asyncio.Event,
    ) -> None:
        description = str(error)[:ERROR_LIMIT]
        headers = dict(message.headers) | {
            HEADER_ERROR: description.encode(),
            HEADER_ERROR_TYPE: type(error).__name__.encode(),
            HEADER_ATTEMPTS: str(attempts).encode(),
            HEADER_ORIGINAL_TOPIC: message.topic.encode(),
            HEADER_ORIGINAL_PARTITION: str(message.partition).encode(),
            HEADER_ORIGINAL_OFFSET: str(message.offset).encode(),
            HEADER_GROUP: self._group.encode(),
        }
        outgoing = OutgoingMessage(
            message.topic + DEAD_LETTER_SUFFIX, message.key or "", message.value, headers
        )
        delay = 0.5
        while True:
            try:
                await self._dead_letters.publish(outgoing)
                break
            except Exception as failure:
                if stop.is_set():
                    raise
                logger.warning(
                    "could not write to the dead letter topic, will retry",
                    extra={"topic": outgoing.topic, "error": repr(failure)},
                )
                await self._sleep(delay)
                delay = min(delay * 2, MAX_LOOP_BACKOFF_SECONDS)
        logger.error(
            "event moved to the dead letter topic",
            extra={
                "group": self._group,
                "topic": outgoing.topic,
                "original_offset": message.offset,
                "error": description,
            },
        )
        if self._on_dead_letter is not None:
            hook = DeadLetter(
                message, envelope, description, type(error).__name__, attempts, self._group
            )
            try:
                await self._on_dead_letter(hook)
            except Exception:
                logger.exception("dead letter hook failed")
