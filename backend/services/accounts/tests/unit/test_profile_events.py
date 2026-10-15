import logging
from datetime import timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from accounts_testing.data import START, SteppingClock
from accounts_testing.events import registered_event, role_changed_event
from sqlalchemy.ext.asyncio import AsyncSession

from accounts.application.profile_events import ProfileEvents
from accounts.domain.profile import ProfileChanges
from accounts.infra.memory import InMemoryProfileRepository, InMemoryStore
from accounts.worker import profile_handlers
from ecommerce_contracts import USER_REGISTERED, USER_ROLE_CHANGED

LATER = START + timedelta(minutes=5)
EVEN_LATER = START + timedelta(minutes=10)


@pytest.fixture
def profiles(store: InMemoryStore) -> InMemoryProfileRepository:
    return InMemoryProfileRepository(store)


@pytest.fixture
def events(clock: SteppingClock) -> ProfileEvents:
    return ProfileEvents(clock)


async def test_a_registration_creates_the_profile(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    user_id = uuid4()

    await events.registered(registered_event(user_id, START, email="  Ada@Example.com "), profiles)

    profile = await profiles.get(user_id)
    assert profile is not None
    assert (profile.email, profile.role, profile.role_updated_at) == (
        "ada@example.com",
        "customer",
        START,
    )
    assert (profile.name, profile.phone) == (None, None)


async def test_a_registration_fills_the_email_of_a_lazily_created_profile(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    user_id = uuid4()
    await profiles.get_or_create(user_id, None, "customer", None, START)
    await profiles.update(user_id, ProfileChanges(name="Ada"), START)

    await events.registered(registered_event(user_id, START), profiles)

    profile = await profiles.get(user_id)
    assert profile is not None
    assert (profile.email, profile.name) == ("ada@example.com", "Ada")


async def test_a_role_change_for_an_unknown_user_creates_the_profile_without_email(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    user_id = uuid4()

    await events.role_changed(role_changed_event(user_id, LATER, new_role="admin"), profiles)

    profile = await profiles.get(user_id)
    assert profile is not None
    assert (profile.email, profile.role, profile.role_updated_at) == (None, "admin", LATER)


async def test_an_older_role_change_does_not_overwrite_a_newer_one(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    user_id = uuid4()
    await events.role_changed(role_changed_event(user_id, EVEN_LATER, new_role="admin"), profiles)

    await events.role_changed(
        role_changed_event(user_id, LATER, new_role="customer", old_role="admin"), profiles
    )

    profile = await profiles.get(user_id)
    assert profile is not None
    assert profile.role == "admin"


async def test_a_late_registration_keeps_the_newer_role_and_adds_the_email(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    user_id = uuid4()
    await events.role_changed(role_changed_event(user_id, LATER), profiles)

    await events.registered(registered_event(user_id, START), profiles)

    profile = await profiles.get(user_id)
    assert profile is not None
    assert (profile.email, profile.role) == ("ada@example.com", "admin")


async def test_handlers_log_the_ids_but_never_the_email(
    events: ProfileEvents, profiles: InMemoryProfileRepository, caplog: pytest.LogCaptureFixture
) -> None:
    user_id = uuid4()
    registered = registered_event(user_id, START, email="secret.person@example.com")
    changed = role_changed_event(user_id, LATER)

    with caplog.at_level(logging.INFO, logger="accounts.application.profile_events"):
        await events.registered(registered, profiles)
        await events.role_changed(changed, profiles)

    records = [r for r in caplog.records if r.name == "accounts.application.profile_events"]
    assert len(records) == 2
    assert [r.__dict__["event_id"] for r in records] == [
        str(registered.event_id),
        str(changed.event_id),
    ]
    assert [r.__dict__["correlation_id"] for r in records] == [
        str(registered.correlation_id),
        str(changed.correlation_id),
    ]
    assert {r.__dict__["user_id"] for r in records} == {str(user_id)}
    assert "secret.person" not in caplog.text


async def test_the_registered_handlers_route_each_event_type_to_the_repository(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    handlers = {
        item.event_type: item for item in profile_handlers(events, lambda session: profiles)
    }
    session = MagicMock(spec=AsyncSession)
    user_id = uuid4()

    await handlers[USER_REGISTERED].callback(registered_event(user_id, START), session)
    await handlers[USER_ROLE_CHANGED].callback(role_changed_event(user_id, LATER), session)

    profile = await profiles.get(user_id)
    assert profile is not None
    assert (profile.email, profile.role) == ("ada@example.com", "admin")


def test_the_worker_handles_exactly_the_two_supported_versions(
    events: ProfileEvents, profiles: InMemoryProfileRepository
) -> None:
    handlers = profile_handlers(events, lambda session: profiles)

    assert {(item.event_type, item.version) for item in handlers} == {
        (USER_REGISTERED, 1),
        (USER_ROLE_CHANGED, 1),
    }
    assert {item.claim.value for item in handlers} == {"with_handler"}
