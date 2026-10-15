import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from accounts_testing.data import ADDRESS

from accounts.application.errors import ProfileNotFoundError
from accounts.application.ports import UnitOfWorkFactory
from accounts.domain.listing import Position, ProfileFilters
from accounts.domain.profile import NewAddress, Profile, ProfileChanges

T0 = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
LATER = T0 + timedelta(minutes=5)
EARLIER = T0 - timedelta(minutes=5)
NOW = T0 + timedelta(hours=1)
NEXT_NOW = NOW + timedelta(hours=1)

NEW_ADDRESS = NewAddress(**ADDRESS)


async def fetch(unit_of_work: UnitOfWorkFactory, user_id: UUID) -> Profile:
    async with unit_of_work() as uow:
        profile = await uow.profiles.get(user_id)
    assert profile is not None
    return profile


async def create(
    unit_of_work: UnitOfWorkFactory,
    user_id: UUID | None = None,
    email: str | None = "ada@example.com",
    role: str = "customer",
    at: datetime | None = T0,
    now: datetime = NOW,
) -> UUID:
    identifier = user_id or uuid4()
    async with unit_of_work() as uow:
        await uow.profiles.get_or_create(identifier, email, role, at, now)
        await uow.commit()
    return identifier


async def registered(
    unit_of_work: UnitOfWorkFactory,
    user_id: UUID,
    email: str | None = "ada@example.com",
    role: str = "customer",
    at: datetime = T0,
    now: datetime = NEXT_NOW,
) -> None:
    async with unit_of_work() as uow:
        await uow.profiles.apply_registered(user_id, email, role, at, now)
        await uow.commit()


async def role_changed(
    unit_of_work: UnitOfWorkFactory,
    user_id: UUID,
    role: str,
    at: datetime,
    now: datetime = NEXT_NOW,
) -> None:
    async with unit_of_work() as uow:
        await uow.profiles.apply_role_change(user_id, role, at, now)
        await uow.commit()


async def test_get_or_create_inserts_the_profile_from_the_claims(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = uuid4()

    async with unit_of_work() as uow:
        profile = await uow.profiles.get_or_create(user_id, "ada@example.com", "admin", T0, NOW)
        await uow.commit()

    assert profile == Profile(user_id, "ada@example.com", "admin", T0, None, None, NOW, NOW)
    assert await fetch(unit_of_work, user_id) == profile


async def test_get_or_create_never_updates_an_existing_profile(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email=None, role="customer", at=T0)

    async with unit_of_work() as uow:
        profile = await uow.profiles.get_or_create(
            user_id, "new@example.com", "admin", LATER, NEXT_NOW
        )
        await uow.commit()

    assert profile.email is None
    assert profile.role == "customer"
    assert profile.role_updated_at == T0
    assert profile.updated_at == NOW


async def test_get_or_create_accepts_a_token_without_an_email(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email=None)

    assert (await fetch(unit_of_work, user_id)).email is None


async def test_concurrent_get_or_create_calls_leave_one_profile(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = uuid4()

    results = await asyncio.gather(*(create(unit_of_work, user_id) for _ in range(12)))

    assert set(results) == {user_id}
    assert (await fetch(unit_of_work, user_id)).created_at == NOW


async def test_registered_creates_a_missing_profile(unit_of_work: UnitOfWorkFactory) -> None:
    user_id = uuid4()

    await registered(unit_of_work, user_id, "ada@example.com", "customer", T0, NOW)

    assert await fetch(unit_of_work, user_id) == Profile(
        user_id, "ada@example.com", "customer", T0, None, None, NOW, NOW
    )


async def test_registered_fills_an_empty_email_and_keeps_the_rest(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email=None, role="customer", at=LATER)
    async with unit_of_work() as uow:
        await uow.profiles.update(
            user_id, ProfileChanges(name="Ada", phone="+34600111222", change_phone=True), NOW
        )
        await uow.commit()

    await registered(unit_of_work, user_id, "ada@example.com", "customer", T0)

    profile = await fetch(unit_of_work, user_id)
    assert profile.email == "ada@example.com"
    assert profile.role_updated_at == LATER
    assert (profile.name, profile.phone) == ("Ada", "+34600111222")
    assert profile.updated_at == NEXT_NOW


async def test_registered_never_replaces_an_existing_email(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email="first@example.com")

    await registered(unit_of_work, user_id, "second@example.com", at=EARLIER)

    assert (await fetch(unit_of_work, user_id)).email == "first@example.com"


async def test_registered_applies_the_role_only_when_newer(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, role="customer", at=T0)

    await registered(unit_of_work, user_id, role="admin", at=T0)
    assert (await fetch(unit_of_work, user_id)).role == "customer"

    await registered(unit_of_work, user_id, role="admin", at=EARLIER)
    assert (await fetch(unit_of_work, user_id)).role == "customer"

    await registered(unit_of_work, user_id, role="admin", at=LATER)
    profile = await fetch(unit_of_work, user_id)
    assert (profile.role, profile.role_updated_at) == ("admin", LATER)


async def test_registered_that_changes_nothing_does_not_touch_the_row(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email="ada@example.com", at=LATER)
    before = await fetch(unit_of_work, user_id)

    await registered(unit_of_work, user_id, "ada@example.com", "customer", T0)
    await registered(unit_of_work, user_id, None, "customer", T0)

    assert await fetch(unit_of_work, user_id) == before


async def test_registered_replayed_twice_equals_once(unit_of_work: UnitOfWorkFactory) -> None:
    user_id = uuid4()

    await registered(unit_of_work, user_id, at=T0, now=NOW)
    once = await fetch(unit_of_work, user_id)
    await registered(unit_of_work, user_id, at=T0, now=NEXT_NOW)

    assert await fetch(unit_of_work, user_id) == once


async def test_role_change_creates_a_missing_profile_without_email(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = uuid4()

    await role_changed(unit_of_work, user_id, "admin", LATER, NOW)

    assert await fetch(unit_of_work, user_id) == Profile(
        user_id, None, "admin", LATER, None, None, NOW, NOW
    )


@pytest.mark.parametrize(
    ("changed_at", "expected"), [(LATER, "admin"), (T0, "customer"), (EARLIER, "customer")]
)
async def test_role_change_applies_only_when_strictly_newer(
    unit_of_work: UnitOfWorkFactory, changed_at: datetime, expected: str
) -> None:
    user_id = await create(unit_of_work, role="customer", at=T0)

    await role_changed(unit_of_work, user_id, "admin", changed_at)

    assert (await fetch(unit_of_work, user_id)).role == expected


async def test_an_older_role_change_after_a_newer_one_does_not_overwrite(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, role="customer", at=T0)

    await role_changed(unit_of_work, user_id, "admin", LATER + timedelta(minutes=1))
    await role_changed(unit_of_work, user_id, "customer", LATER)

    profile = await fetch(unit_of_work, user_id)
    assert (profile.role, profile.role_updated_at) == ("admin", LATER + timedelta(minutes=1))


async def test_a_role_change_before_registration_keeps_its_role_and_gains_the_email(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = uuid4()

    await role_changed(unit_of_work, user_id, "admin", LATER, NOW)
    await registered(unit_of_work, user_id, "ada@example.com", "customer", T0, NEXT_NOW)

    profile = await fetch(unit_of_work, user_id)
    assert (profile.email, profile.role, profile.role_updated_at) == (
        "ada@example.com",
        "admin",
        LATER,
    )


async def test_update_changes_the_name_and_sets_or_clears_the_phone(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work)

    async with unit_of_work() as uow:
        named = await uow.profiles.update(user_id, ProfileChanges(name="Ada"), NEXT_NOW)
        phoned = await uow.profiles.update(
            user_id, ProfileChanges(phone="+34600111222", change_phone=True), NEXT_NOW
        )
        cleared = await uow.profiles.update(user_id, ProfileChanges(change_phone=True), NEXT_NOW)
        await uow.commit()

    assert (named.name, named.phone) == ("Ada", None)
    assert (phoned.name, phoned.phone) == ("Ada", "+34600111222")
    assert (cleared.name, cleared.phone) == ("Ada", None)
    assert cleared.updated_at == NEXT_NOW


async def test_update_of_a_missing_profile_fails(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        with pytest.raises(ProfileNotFoundError):
            await uow.profiles.update(uuid4(), ProfileChanges(name="Ada"), NOW)


async def test_get_of_a_missing_profile_is_none(unit_of_work: UnitOfWorkFactory) -> None:
    async with unit_of_work() as uow:
        assert await uow.profiles.get(uuid4()) is None
        assert await uow.profiles.get_for_update(uuid4()) is None


async def test_get_for_update_returns_the_profile(unit_of_work: UnitOfWorkFactory) -> None:
    user_id = await create(unit_of_work)

    async with unit_of_work() as uow:
        assert await uow.profiles.get_for_update(user_id) == await fetch(unit_of_work, user_id)


async def test_addresses_are_added_listed_in_order_and_counted(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work)
    other = await create(unit_of_work)

    async with unit_of_work() as uow:
        first = await uow.addresses.add(user_id, NEW_ADDRESS, NOW)
        second = await uow.addresses.add(user_id, NEW_ADDRESS, NEXT_NOW)
        await uow.addresses.add(other, NEW_ADDRESS, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        listed = await uow.addresses.list_for(user_id)
        count = await uow.addresses.count_for(user_id)

    assert [item.id for item in listed] == [first.id, second.id]
    assert count == 2
    assert listed[0].country == "GB"
    assert listed[0].line2 == "Floor 2"
    assert listed[0].user_id == user_id


async def test_an_address_keeps_its_optional_fields_empty(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work)
    minimal = NewAddress("Ada", "1 Main St", None, "Madrid", None, "28001", "ES", None)

    async with unit_of_work() as uow:
        created = await uow.addresses.add(user_id, minimal, NOW)
        await uow.commit()

    assert (created.line2, created.region, created.phone) == (None, None, None)


async def test_delete_removes_only_the_owners_address(unit_of_work: UnitOfWorkFactory) -> None:
    owner = await create(unit_of_work)
    stranger = await create(unit_of_work)
    async with unit_of_work() as uow:
        address = await uow.addresses.add(owner, NEW_ADDRESS, NOW)
        await uow.commit()

    async with unit_of_work() as uow:
        assert await uow.addresses.delete(stranger, address.id) is False
        assert await uow.addresses.delete(owner, uuid4()) is False
        assert await uow.addresses.delete(owner, address.id) is True
        assert await uow.addresses.delete(owner, address.id) is False
        await uow.commit()

    async with unit_of_work() as uow:
        assert await uow.addresses.list_for(owner) == []


async def seed_directory(unit_of_work: UnitOfWorkFactory) -> tuple[str, list[UUID]]:
    tag = uuid4().hex[:10]
    rows = [
        (f"{tag}ada@example.com", "customer"),
        (f"{tag}adam@example.com", "admin"),
        (f"{tag}grace@example.com", "customer"),
        (f"{tag}a_c@example.com", "customer"),
        (f"{tag}100%@example.com", "customer"),
    ]
    identifiers = [
        await create(
            unit_of_work, email=email, role=role, at=T0, now=NOW + timedelta(minutes=index)
        )
        for index, (email, role) in enumerate(rows)
    ]
    return tag, identifiers


async def page(
    unit_of_work: UnitOfWorkFactory,
    filters: ProfileFilters | None = None,
    after: Position | None = None,
    limit: int = 50,
) -> list[Profile]:
    async with unit_of_work() as uow:
        return await uow.profiles.list_page(filters or ProfileFilters(), after, limit)


async def test_list_page_orders_newest_first(unit_of_work: UnitOfWorkFactory) -> None:
    tag, identifiers = await seed_directory(unit_of_work)

    rows = await page(unit_of_work, ProfileFilters(email_prefix=tag))

    assert [row.user_id for row in rows] == identifiers[::-1]


async def test_list_page_filters_by_email_prefix_and_role(unit_of_work: UnitOfWorkFactory) -> None:
    tag, _ = await seed_directory(unit_of_work)

    by_prefix = await page(unit_of_work, ProfileFilters(email_prefix=f"{tag}ada"))
    by_role = await page(unit_of_work, ProfileFilters(role="admin", email_prefix=tag))

    assert {row.email for row in by_prefix} == {f"{tag}ada@example.com", f"{tag}adam@example.com"}
    assert [row.email for row in by_role] == [f"{tag}adam@example.com"]


@pytest.mark.parametrize(("prefix", "local"), [("a_", "a_c"), ("100%", "100%")])
async def test_list_page_treats_wildcards_in_the_prefix_literally(
    unit_of_work: UnitOfWorkFactory, prefix: str, local: str
) -> None:
    tag, _ = await seed_directory(unit_of_work)

    rows = await page(unit_of_work, ProfileFilters(email_prefix=f"{tag}{prefix}"))

    assert [row.email for row in rows] == [f"{tag}{local}@example.com"]


async def test_list_page_walks_all_rows_with_keyset_positions(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    tag, _ = await seed_directory(unit_of_work)
    filters = ProfileFilters(email_prefix=tag)
    everything = await page(unit_of_work, filters)

    walked: list[Profile] = []
    after: Position | None = None
    while True:
        rows = await page(unit_of_work, filters, after, 2)
        walked.extend(rows)
        if len(rows) < 2:
            break
        after = Position(rows[-1].created_at, rows[-1].user_id)

    assert len(everything) == 5
    assert walked == everything


async def test_profiles_with_equal_timestamps_still_page_without_gaps(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    identifiers = [
        await create(unit_of_work, email=f"tie{n}@example.com", now=NOW) for n in range(5)
    ]
    filters = ProfileFilters(email_prefix="tie")

    walked: list[UUID] = []
    after: Position | None = None
    for _ in range(5):
        rows = await page(unit_of_work, filters, after, 2)
        walked.extend(row.user_id for row in rows)
        if len(rows) < 2:
            break
        after = Position(rows[-1].created_at, rows[-1].user_id)

    assert sorted(walked) == sorted(identifiers)
    assert len(walked) == len(set(walked))


async def test_a_profile_without_a_role_time_accepts_any_registration(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, role="customer", at=None)
    assert (await fetch(unit_of_work, user_id)).role_updated_at is None

    await registered(unit_of_work, user_id, role="admin", at=EARLIER)

    profile = await fetch(unit_of_work, user_id)
    assert (profile.role, profile.role_updated_at) == ("admin", EARLIER)


async def test_a_profile_without_a_role_time_accepts_any_role_change(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, role="customer", at=None, now=NEXT_NOW)

    await role_changed(unit_of_work, user_id, "admin", EARLIER, NEXT_NOW)

    profile = await fetch(unit_of_work, user_id)
    assert (profile.role, profile.role_updated_at) == ("admin", EARLIER)


async def test_a_registration_stamps_the_role_time_of_a_profile_that_had_none(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, email=None, role="customer", at=None)

    await registered(unit_of_work, user_id, "ada@example.com", "customer", T0)

    profile = await fetch(unit_of_work, user_id)
    assert (profile.email, profile.role_updated_at) == ("ada@example.com", T0)


async def test_once_a_role_time_is_set_older_events_are_ignored_again(
    unit_of_work: UnitOfWorkFactory,
) -> None:
    user_id = await create(unit_of_work, role="customer", at=None)
    await role_changed(unit_of_work, user_id, "admin", LATER)

    await role_changed(unit_of_work, user_id, "customer", T0)

    assert (await fetch(unit_of_work, user_id)).role == "admin"
