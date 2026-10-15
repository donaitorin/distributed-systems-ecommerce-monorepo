from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from accounts_testing.data import ADDRESS, START, SteppingClock

from accounts.application.accounts import AccountService, Identity
from accounts.application.errors import AddressLimitReachedError, AddressNotFoundError
from accounts.domain.listing import ProfileFilters
from accounts.domain.profile import MAX_ADDRESSES, NewAddress, ProfileChanges
from accounts.infra.memory import InMemoryStore, InMemoryUnitOfWork


@pytest.fixture
def service(store: InMemoryStore, clock: SteppingClock) -> AccountService:
    return AccountService(lambda: InMemoryUnitOfWork(store), clock)


def identity(
    user_id: UUID | None = None,
    email: str | None = "ada@example.com",
    role: str = "customer",
    issued_at: datetime | None = START - timedelta(minutes=3),
) -> Identity:
    return Identity(user_id or uuid4(), email, role, issued_at)


async def test_me_creates_the_profile_from_the_token_claims(service: AccountService) -> None:
    who = identity(role="admin")

    profile = await service.me(who)

    assert (profile.user_id, profile.email, profile.role) == (who.user_id, who.email, "admin")
    assert profile.role_updated_at == who.issued_at
    assert (profile.name, profile.phone) == (None, None)
    assert profile.created_at == START


async def test_me_normalizes_the_email_claim(service: AccountService) -> None:
    profile = await service.me(identity(email="  Ada@Example.COM "))

    assert profile.email == "ada@example.com"


async def test_me_without_issue_time_leaves_the_role_time_empty(service: AccountService) -> None:
    profile = await service.me(identity(issued_at=None))

    assert profile.role_updated_at is None


async def test_me_without_email_leaves_it_empty(service: AccountService) -> None:
    assert (await service.me(identity(email=None))).email is None


async def test_me_never_updates_an_existing_profile(
    service: AccountService, clock: SteppingClock
) -> None:
    who = identity()
    first = await service.me(who)
    clock.advance(seconds=60)

    again = await service.me(identity(user_id=who.user_id, email="other@example.com", role="admin"))

    assert again == first


async def test_update_me_changes_only_the_given_fields(service: AccountService) -> None:
    who = identity()

    named = await service.update_me(who, ProfileChanges(name="Ada"))
    phoned = await service.update_me(who, ProfileChanges(phone="+34600111222", change_phone=True))

    assert named.name == "Ada"
    assert (phoned.name, phoned.phone) == ("Ada", "+34600111222")


async def test_an_empty_update_keeps_the_profile_untouched(
    service: AccountService, clock: SteppingClock
) -> None:
    who = identity()
    before = await service.me(who)
    clock.advance(seconds=30)

    assert await service.update_me(who, ProfileChanges()) == before


async def test_addresses_are_limited_per_user(service: AccountService) -> None:
    who = identity()
    for _ in range(MAX_ADDRESSES):
        await service.add_address(who, NewAddress(**ADDRESS))

    with pytest.raises(AddressLimitReachedError):
        await service.add_address(who, NewAddress(**ADDRESS))

    assert len(await service.list_addresses(who)) == MAX_ADDRESSES
    await service.add_address(identity(), NewAddress(**ADDRESS))


async def test_deleting_an_address_frees_a_slot(service: AccountService) -> None:
    who = identity()
    created = [await service.add_address(who, NewAddress(**ADDRESS)) for _ in range(MAX_ADDRESSES)]

    await service.delete_address(who, created[0].id)

    await service.add_address(who, NewAddress(**ADDRESS))
    assert len(await service.list_addresses(who)) == MAX_ADDRESSES


async def test_deleting_an_unknown_or_foreign_address_is_not_found(
    service: AccountService,
) -> None:
    owner, stranger = identity(), identity()
    address = await service.add_address(owner, NewAddress(**ADDRESS))

    with pytest.raises(AddressNotFoundError):
        await service.delete_address(stranger, address.id)
    with pytest.raises(AddressNotFoundError):
        await service.delete_address(owner, uuid4())

    assert len(await service.list_addresses(owner)) == 1


async def test_list_profiles_pages_with_a_cursor(
    service: AccountService, clock: SteppingClock
) -> None:
    for number in range(5):
        await service.me(identity(email=f"user{number}@example.com"))
        clock.advance(seconds=1)
    filters = ProfileFilters(email_prefix="USER")

    first = await service.list_profiles(filters, 2, None)
    second = await service.list_profiles(filters, 2, first.next_cursor)
    third = await service.list_profiles(filters, 2, second.next_cursor)

    emails = [item.email for page in (first, second, third) for item in page.items]
    assert emails == [f"user{n}@example.com" for n in (4, 3, 2, 1, 0)]
    assert first.next_cursor is not None
    assert third.next_cursor is None


async def test_list_profiles_without_more_rows_has_no_cursor(service: AccountService) -> None:
    await service.me(identity())

    page = await service.list_profiles(ProfileFilters(), 25, None)

    assert len(page.items) == 1
    assert page.next_cursor is None
