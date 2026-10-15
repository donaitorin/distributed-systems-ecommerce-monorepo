import asyncio
import random
from collections.abc import AsyncIterator, Coroutine
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from accounts_testing.data import START, SteppingClock
from accounts_testing.events import incoming, registered_event, role_changed_event
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from accounts.application.accounts import AccountService, Identity
from accounts.application.ports import ProfileRepository
from accounts.domain.profile import NewAddress, Profile, ProfileChanges
from accounts.infra.database import create_engine, create_session_factory
from accounts.infra.repositories import SqlProfileRepository
from accounts.infra.unit_of_work import SqlAlchemyUnitOfWork
from accounts.worker import CONSUMER_GROUP, build_consumer
from ecommerce_contracts import AUTH_TOPIC, Envelope
from ecommerce_messaging import EventConsumer, InMemoryBroker, Outcome, RetryPolicy

pytestmark = pytest.mark.integration

T1 = START + timedelta(minutes=1)
T2 = START + timedelta(minutes=2)
T3 = START + timedelta(minutes=3)
DEAD_LETTER_TOPIC = AUTH_TOPIC + ".dlq"


class FailingAfterWriting(SqlProfileRepository):
    async def apply_registered(
        self, user_id: UUID, email: str | None, role: str, registered_at: datetime, now: datetime
    ) -> None:
        await super().apply_registered(user_id, email, role, registered_at, now)
        raise RuntimeError("boom after the write")


def failing_repository(session: AsyncSession) -> ProfileRepository:
    return FailingAfterWriting(session)


@dataclass(slots=True)
class Harness:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    broker: InMemoryBroker
    clock: SteppingClock
    group: str
    consumer: EventConsumer
    service: AccountService

    async def deliver(self, envelope: Envelope[Any], offset: int = 0) -> Outcome:
        return await self.consumer.handle(incoming(envelope, offset))

    async def profile(self, user_id: UUID) -> Profile:
        async with SqlAlchemyUnitOfWork(self.sessions) as uow:
            profile = await uow.profiles.get(user_id)
        assert profile is not None
        return profile

    async def has_profile(self, user_id: UUID) -> bool:
        async with SqlAlchemyUnitOfWork(self.sessions) as uow:
            return await uow.profiles.get(user_id) is not None

    async def processed(self) -> int:
        async with self.engine.connect() as connection:
            result = await connection.execute(
                text("SELECT count(*) FROM processed_events WHERE consumer_group = :group"),
                {"group": self.group},
            )
            return int(result.scalar_one())


def build_harness(url: str, repository_for: Any = None) -> tuple[Harness, AsyncEngine]:
    engine = create_engine(url)
    sessions = create_session_factory(engine)
    broker = InMemoryBroker()
    clock = SteppingClock()
    group = f"{CONSUMER_GROUP}-{uuid4().hex}"
    options: dict[str, Any] = {"repository_for": repository_for} if repository_for else {}
    consumer = build_consumer(
        broker.source([AUTH_TOPIC]),
        broker,
        sessions,
        group=group,
        clock=clock,
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0),
        **options,
    )
    service = AccountService(lambda: SqlAlchemyUnitOfWork(sessions), clock)
    return Harness(engine, sessions, broker, clock, group, consumer, service), engine


@pytest.fixture
async def harness(migrated_database_url: str) -> AsyncIterator[Harness]:
    prepared, engine = build_harness(migrated_database_url)
    yield prepared
    await engine.dispose()


@pytest.fixture
async def failing_harness(migrated_database_url: str) -> AsyncIterator[Harness]:
    prepared, engine = build_harness(migrated_database_url, failing_repository)
    yield prepared
    await engine.dispose()


async def test_a_registration_event_creates_the_profile(harness: Harness) -> None:
    user_id = uuid4()

    outcome = await harness.deliver(registered_event(user_id, START))

    assert outcome is Outcome.PROCESSED
    profile = await harness.profile(user_id)
    assert (profile.email, profile.role, profile.role_updated_at) == (
        "ada@example.com",
        "customer",
        START,
    )
    assert await harness.processed() == 1


async def test_a_replayed_event_is_a_no_op(harness: Harness) -> None:
    user_id = uuid4()
    event = registered_event(user_id, START)
    await harness.deliver(event)
    before = await harness.profile(user_id)
    harness.clock.advance(seconds=600)

    outcome = await harness.deliver(event, offset=1)

    assert outcome is Outcome.DUPLICATE
    assert await harness.profile(user_id) == before
    assert await harness.processed() == 1


async def test_the_same_event_republished_to_another_offset_changes_nothing(
    harness: Harness,
) -> None:
    user_id = uuid4()
    event = role_changed_event(user_id, T2, new_role="admin")
    await harness.deliver(event, offset=3)
    before = await harness.profile(user_id)

    outcomes = [await harness.deliver(event, offset=offset) for offset in (9, 10)]

    assert outcomes == [Outcome.DUPLICATE, Outcome.DUPLICATE]
    assert await harness.profile(user_id) == before
    assert await harness.processed() == 1


async def test_an_older_role_change_after_a_newer_one_does_not_overwrite(
    harness: Harness,
) -> None:
    user_id = uuid4()
    await harness.deliver(registered_event(user_id, START))

    first = await harness.deliver(role_changed_event(user_id, T2, new_role="admin"), 1)
    second = await harness.deliver(
        role_changed_event(user_id, T1, new_role="customer", old_role="admin"), 2
    )

    assert (first, second) == (Outcome.PROCESSED, Outcome.PROCESSED)
    profile = await harness.profile(user_id)
    assert (profile.role, profile.role_updated_at) == ("admin", T2)
    assert await harness.processed() == 3


async def test_a_role_change_before_the_registration_creates_the_profile(
    harness: Harness,
) -> None:
    user_id = uuid4()

    await harness.deliver(role_changed_event(user_id, T2, new_role="admin"))
    created = await harness.profile(user_id)
    await harness.deliver(registered_event(user_id, START, role="customer"), offset=1)
    completed = await harness.profile(user_id)

    assert (created.email, created.role) == (None, "admin")
    assert (completed.email, completed.role, completed.role_updated_at) == (
        "ada@example.com",
        "admin",
        T2,
    )
    assert completed.created_at == created.created_at


async def test_the_registration_does_not_touch_what_the_user_edited(harness: Harness) -> None:
    user_id = uuid4()
    identity = Identity(user_id, None, "customer", START)
    await harness.service.me(identity)
    async with SqlAlchemyUnitOfWork(harness.sessions) as uow:
        await uow.profiles.update(
            user_id, ProfileChanges(name="Ada", phone="+34600111222", change_phone=True), START
        )
        await uow.addresses.add(
            user_id, NewAddress("Ada", "1 St", None, "Madrid", None, "28001", "ES", None), START
        )
        await uow.commit()

    await harness.deliver(registered_event(user_id, START))

    profile = await harness.profile(user_id)
    assert (profile.email, profile.name, profile.phone) == (
        "ada@example.com",
        "Ada",
        "+34600111222",
    )
    assert len(await harness.service.list_addresses(identity)) == 1


async def test_a_token_without_an_issue_time_loses_to_any_later_event(harness: Harness) -> None:
    user_id = uuid4()
    await harness.service.me(Identity(user_id, "ada@example.com", "customer", None))

    await harness.deliver(role_changed_event(user_id, START - timedelta(days=1), new_role="admin"))

    assert (await harness.profile(user_id)).role == "admin"


@pytest.mark.parametrize(
    ("token_role", "issued_at"), [("customer", T1), ("admin", T3), ("admin", None)]
)
async def test_the_lazy_path_racing_the_events_always_converges(
    harness: Harness, token_role: str, issued_at: datetime | None
) -> None:
    shuffler = random.Random(7)
    users = [uuid4() for _ in range(20)]
    work: list[Coroutine[Any, Any, object]] = []
    for user_id in users:
        work.append(harness.deliver(registered_event(user_id, START, role="customer"), 0))
        work.append(harness.deliver(role_changed_event(user_id, T2, new_role="admin"), 1))
        work.append(harness.service.me(Identity(user_id, "ada@example.com", token_role, issued_at)))
    shuffler.shuffle(work)

    await asyncio.gather(*work)

    for user_id in users:
        profile = await harness.profile(user_id)
        assert (profile.email, profile.role) == ("ada@example.com", "admin")
    assert await harness.processed() == 40


async def test_an_unsupported_version_is_dead_lettered_and_changes_nothing(
    harness: Harness,
) -> None:
    user_id = uuid4()
    future = registered_event(user_id, START).model_copy(update={"event_version": 2})

    outcome = await harness.deliver(future)

    assert outcome is Outcome.DEAD_LETTERED
    assert len(harness.broker.messages(DEAD_LETTER_TOPIC)) == 1
    assert not await harness.has_profile(user_id)
    assert await harness.processed() == 0


async def test_an_unknown_event_type_is_ignored(harness: Harness) -> None:
    unrelated = registered_event(uuid4(), START).model_copy(update={"event_type": "user.deleted"})

    outcome = await harness.deliver(unrelated)

    assert outcome is Outcome.IGNORED
    assert harness.broker.messages(DEAD_LETTER_TOPIC) == []
    assert await harness.processed() == 0


async def test_a_failing_handler_rolls_back_the_profile_and_the_claim(
    failing_harness: Harness,
) -> None:
    user_id = uuid4()

    outcome = await failing_harness.deliver(registered_event(user_id, START))

    assert outcome is Outcome.DEAD_LETTERED
    assert not await failing_harness.has_profile(user_id)
    assert await failing_harness.processed() == 0
    [letter] = failing_harness.broker.messages(DEAD_LETTER_TOPIC)
    assert letter.headers["x-attempts"] == b"2"
