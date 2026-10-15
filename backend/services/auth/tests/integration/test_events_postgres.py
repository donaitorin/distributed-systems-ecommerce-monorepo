import json
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from auth_testing.support import FAST_HASHING, STRONG_PASSWORD, FakeHasher
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from auth.application.errors import EmailTakenError, SelfRoleChangeError
from auth.application.registration import RegistrationService
from auth.application.roles import RoleService
from auth.domain.user import Role
from auth.infra.database import create_engine, create_session_factory
from auth.infra.unit_of_work import SqlAlchemyUnitOfWork
from auth.tools.seed import run
from auth.worker import build_relay
from ecommerce_contracts import (
    AUTH_TOPIC,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    Envelope,
    UserRegisteredV1,
    UserRoleChangedV1,
)
from ecommerce_messaging import InMemoryBroker

pytestmark = pytest.mark.integration


class Services:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessions: async_sessionmaker[AsyncSession] = create_session_factory(engine)
        self.registration = RegistrationService(self.unit_of_work, FakeHasher())
        self.roles = RoleService(self.unit_of_work)

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.sessions)

    async def outbox_for(self, user_id: UUID) -> list[dict[str, object]]:
        async with self.engine.connect() as connection:
            rows = await connection.execute(
                text("SELECT topic, key, payload FROM outbox WHERE key = :key ORDER BY id"),
                {"key": str(user_id)},
            )
            return [
                {"topic": row.topic, "key": row.key, "envelope": json.loads(row.payload)}
                for row in rows
            ]


@pytest.fixture
async def services(migrated_database_url: str) -> AsyncIterator[Services]:
    engine = create_engine(migrated_database_url)
    yield Services(engine)
    await engine.dispose()


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}@example.com"


async def test_registration_commits_the_user_and_its_event_together(services: Services) -> None:
    correlation_id = uuid4()

    user = await services.registration.register(
        unique_email("reg"), STRONG_PASSWORD, correlation_id
    )

    (row,) = await services.outbox_for(user.id)
    assert row["topic"] == AUTH_TOPIC
    envelope = Envelope[UserRegisteredV1].model_validate(row["envelope"])
    assert envelope.event_type == USER_REGISTERED
    assert envelope.producer == "auth-service"
    assert envelope.correlation_id == correlation_id
    assert envelope.payload.user_id == user.id
    assert envelope.payload.email == user.email
    assert "password" not in json.dumps(row["envelope"])


async def test_a_failed_registration_leaves_no_event_behind(services: Services) -> None:
    email = unique_email("dup")
    first = await services.registration.register(email, STRONG_PASSWORD, uuid4())

    with pytest.raises(EmailTakenError):
        await services.registration.register(email, STRONG_PASSWORD, uuid4())

    assert len(await services.outbox_for(first.id)) == 1


async def test_a_role_change_commits_the_new_role_and_its_event_together(
    services: Services,
) -> None:
    admin = await services.registration.register(
        unique_email("admin"), STRONG_PASSWORD, uuid4(), Role.ADMIN
    )
    user = await services.registration.register(unique_email("user"), STRONG_PASSWORD, uuid4())

    updated = await services.roles.change_role(admin.id, user.id, Role.ADMIN, uuid4())

    assert updated.role is Role.ADMIN
    async with services.unit_of_work() as uow:
        stored = await uow.users.get(user.id)
    assert stored is not None
    assert stored.role is Role.ADMIN
    registered, changed = await services.outbox_for(user.id)
    envelope = Envelope[UserRoleChangedV1].model_validate(changed["envelope"])
    assert envelope.event_type == USER_ROLE_CHANGED
    assert envelope.payload.changed_by == admin.id
    assert (envelope.payload.old_role, envelope.payload.new_role) == ("customer", "admin")
    first_envelope = Envelope[UserRegisteredV1].model_validate(registered["envelope"])
    assert first_envelope.event_type == USER_REGISTERED


async def test_a_rejected_role_change_writes_nothing(services: Services) -> None:
    admin = await services.registration.register(
        unique_email("self"), STRONG_PASSWORD, uuid4(), Role.ADMIN
    )

    with pytest.raises(SelfRoleChangeError):
        await services.roles.change_role(admin.id, admin.id, Role.CUSTOMER, uuid4())

    assert len(await services.outbox_for(admin.id)) == 1


async def test_the_relay_publishes_user_events_keyed_by_user_id(services: Services) -> None:
    admin = await services.registration.register(
        unique_email("relay-admin"), STRONG_PASSWORD, uuid4(), Role.ADMIN
    )
    user = await services.registration.register(unique_email("relay"), STRONG_PASSWORD, uuid4())
    await services.roles.change_role(admin.id, user.id, Role.ADMIN, uuid4())
    broker = InMemoryBroker()

    await build_relay(services.sessions, broker).drain_once()

    mine = [message for message in broker.published if message.key == str(user.id)]
    assert [json.loads(message.value)["event_type"] for message in mine] == [
        USER_REGISTERED,
        USER_ROLE_CHANGED,
    ]
    assert {message.topic for message in mine} == {AUTH_TOPIC}


async def test_events_wait_in_the_outbox_while_the_broker_is_down_and_go_out_after(
    services: Services,
) -> None:
    broker = InMemoryBroker()
    broker.available = False
    user = await services.registration.register(unique_email("later"), STRONG_PASSWORD, uuid4())
    relay = build_relay(services.sessions, broker)

    with pytest.raises(Exception, match="unavailable"):
        await relay.drain_once()
    assert broker.published == []

    broker.available = True
    await relay.drain_once()

    assert str(user.id) in {message.key for message in broker.published}


async def test_the_seed_publishes_user_registered_for_the_admin(migrated_database_url: str) -> None:
    url = make_url(migrated_database_url)
    email = unique_email("seed")
    environ = {
        "AUTH_DB_HOST": url.host or "",
        "AUTH_DB_PORT": str(url.port),
        "AUTH_DB_NAME": url.database or "",
        "AUTH_DB_USER": url.username or "",
        "AUTH_DB_PASSWORD": url.password or "",
        "AUTH_ADMIN_EMAIL": email,
        "AUTH_ADMIN_PASSWORD": STRONG_PASSWORD,
        "AUTH_ARGON2_MEMORY_KIB": str(FAST_HASHING.memory_cost_kib),
        "AUTH_ARGON2_TIME_COST": str(FAST_HASHING.time_cost),
    }

    assert await run(environ) is True
    assert await run(environ) is False

    engine = create_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            payloads = [
                json.loads(row.payload)
                for row in await connection.execute(
                    text("SELECT payload FROM outbox WHERE payload LIKE :pattern"),
                    {"pattern": f"%{email}%"},
                )
            ]
    finally:
        await engine.dispose()
    assert len(payloads) == 1
    assert payloads[0]["payload"]["role"] == "admin"
