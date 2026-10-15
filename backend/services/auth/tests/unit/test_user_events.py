from uuid import UUID, uuid4

import pytest
from auth_testing.support import STRONG_PASSWORD, FakeHasher, SteppingClock

from auth.application.errors import EmailTakenError, SelfRoleChangeError, UserNotFoundError
from auth.application.registration import RegistrationService
from auth.application.roles import RoleService
from auth.domain.errors import ValidationFailedError
from auth.domain.user import Role, User
from auth.infra.memory import InMemoryStore, InMemoryUnitOfWork
from ecommerce_contracts import (
    AUTH_TOPIC,
    USER_REGISTERED,
    USER_ROLE_CHANGED,
    UserRegisteredV1,
    UserRoleChangedV1,
)

EMAIL = "ada@example.com"


class Harness:
    def __init__(self) -> None:
        self.store = InMemoryStore()
        self.clock = SteppingClock()
        self.registration = RegistrationService(self.unit_of_work, FakeHasher(), self.clock)
        self.roles = RoleService(self.unit_of_work, self.clock)

    def unit_of_work(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store)

    async def register(
        self, email: str = EMAIL, role: Role = Role.CUSTOMER, correlation_id: UUID | None = None
    ) -> User:
        return await self.registration.register(
            email, STRONG_PASSWORD, correlation_id or uuid4(), role
        )


@pytest.fixture
def harness() -> Harness:
    return Harness()


async def test_registration_publishes_user_registered_in_the_same_unit_of_work(
    harness: Harness,
) -> None:
    correlation_id = uuid4()

    user = await harness.register(correlation_id=correlation_id)

    (entry,) = harness.store.outbox
    assert entry.topic == AUTH_TOPIC == "auth.events"
    assert entry.key == str(user.id)
    assert entry.event_type == USER_REGISTERED
    assert entry.correlation_id == correlation_id
    assert entry.payload == UserRegisteredV1(
        user_id=user.id, email=EMAIL, role="customer", registered_at=harness.clock()
    )


async def test_the_event_never_carries_the_password_or_its_hash(harness: Harness) -> None:
    await harness.register()

    (entry,) = harness.store.outbox
    dumped = entry.payload.model_dump_json()
    assert STRONG_PASSWORD not in dumped
    assert "fake$" not in dumped


async def test_an_admin_registration_publishes_the_admin_role(harness: Harness) -> None:
    await harness.register(role=Role.ADMIN)

    (entry,) = harness.store.outbox
    assert isinstance(entry.payload, UserRegisteredV1)
    assert entry.payload.role == "admin"


async def test_a_taken_email_publishes_nothing(harness: Harness) -> None:
    await harness.register()

    with pytest.raises(EmailTakenError):
        await harness.register("ADA@example.com")

    assert len(harness.store.outbox) == 1


async def test_an_invalid_registration_publishes_nothing(harness: Harness) -> None:
    with pytest.raises(ValidationFailedError):
        await harness.registration.register("nope", "short", uuid4())

    assert harness.store.outbox == []


async def test_changing_a_role_updates_the_user_and_publishes_user_role_changed(
    harness: Harness,
) -> None:
    admin = await harness.register("admin@example.com", Role.ADMIN)
    user = await harness.register()
    harness.clock.advance(seconds=30)
    correlation_id = uuid4()

    updated = await harness.roles.change_role(admin.id, user.id, Role.ADMIN, correlation_id)

    assert updated.role is Role.ADMIN
    assert harness.store.users[user.id].role is Role.ADMIN
    entry = harness.store.outbox[-1]
    assert entry.topic == AUTH_TOPIC
    assert entry.key == str(user.id)
    assert entry.event_type == USER_ROLE_CHANGED
    assert entry.correlation_id == correlation_id
    assert entry.payload == UserRoleChangedV1(
        user_id=user.id,
        old_role="customer",
        new_role="admin",
        changed_by=admin.id,
        changed_at=harness.clock(),
    )


async def test_demoting_an_admin_publishes_the_old_and_new_roles(harness: Harness) -> None:
    admin = await harness.register("admin@example.com", Role.ADMIN)
    other = await harness.register("other@example.com", Role.ADMIN)

    await harness.roles.change_role(admin.id, other.id, Role.CUSTOMER, uuid4())

    payload = harness.store.outbox[-1].payload
    assert isinstance(payload, UserRoleChangedV1)
    assert (payload.old_role, payload.new_role) == ("admin", "customer")


async def test_setting_the_role_a_user_already_has_changes_and_publishes_nothing(
    harness: Harness,
) -> None:
    admin = await harness.register("admin@example.com", Role.ADMIN)
    user = await harness.register()
    events_before = len(harness.store.outbox)

    unchanged = await harness.roles.change_role(admin.id, user.id, Role.CUSTOMER, uuid4())

    assert unchanged.role is Role.CUSTOMER
    assert len(harness.store.outbox) == events_before


async def test_an_admin_cannot_change_their_own_role(harness: Harness) -> None:
    admin = await harness.register("admin@example.com", Role.ADMIN)
    events_before = len(harness.store.outbox)

    with pytest.raises(SelfRoleChangeError):
        await harness.roles.change_role(admin.id, admin.id, Role.CUSTOMER, uuid4())

    assert harness.store.users[admin.id].role is Role.ADMIN
    assert len(harness.store.outbox) == events_before


async def test_changing_the_role_of_an_unknown_user_fails(harness: Harness) -> None:
    admin = await harness.register("admin@example.com", Role.ADMIN)

    with pytest.raises(UserNotFoundError):
        await harness.roles.change_role(admin.id, uuid4(), Role.ADMIN, uuid4())
