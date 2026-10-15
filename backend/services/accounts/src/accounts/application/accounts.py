from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from accounts.application.clock import utc_now
from accounts.application.cursors import decode_cursor, encode_cursor, fingerprint_of
from accounts.application.errors import AddressLimitReachedError, AddressNotFoundError
from accounts.application.ports import UnitOfWork, UnitOfWorkFactory
from accounts.domain.listing import Position, ProfileFilters
from accounts.domain.profile import (
    MAX_ADDRESSES,
    Address,
    NewAddress,
    Profile,
    ProfileChanges,
    normalize_email,
)


@dataclass(frozen=True, slots=True)
class Identity:
    user_id: UUID
    email: str | None
    role: str
    issued_at: datetime | None


@dataclass(frozen=True, slots=True)
class ProfilePage:
    items: list[Profile]
    next_cursor: str | None


class AccountService:
    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def me(self, identity: Identity) -> Profile:
        async with self._unit_of_work() as uow:
            profile = await self._ensure_profile(uow, identity)
            await uow.commit()
        return profile

    async def update_me(self, identity: Identity, changes: ProfileChanges) -> Profile:
        async with self._unit_of_work() as uow:
            profile = await self._ensure_profile(uow, identity)
            if not changes.is_empty:
                profile = await uow.profiles.update(identity.user_id, changes, self._clock())
            await uow.commit()
        return profile

    async def list_addresses(self, identity: Identity) -> list[Address]:
        async with self._unit_of_work() as uow:
            await self._ensure_profile(uow, identity)
            addresses = await uow.addresses.list_for(identity.user_id)
            await uow.commit()
        return addresses

    async def add_address(self, identity: Identity, address: NewAddress) -> Address:
        async with self._unit_of_work() as uow:
            await self._ensure_profile(uow, identity)
            await uow.profiles.get_for_update(identity.user_id)
            if await uow.addresses.count_for(identity.user_id) >= MAX_ADDRESSES:
                raise AddressLimitReachedError(MAX_ADDRESSES)
            created = await uow.addresses.add(identity.user_id, address, self._clock())
            await uow.commit()
        return created

    async def delete_address(self, identity: Identity, address_id: UUID) -> None:
        async with self._unit_of_work() as uow:
            await self._ensure_profile(uow, identity)
            if not await uow.addresses.delete(identity.user_id, address_id):
                raise AddressNotFoundError(address_id)
            await uow.commit()

    async def list_profiles(
        self, filters: ProfileFilters, limit: int, cursor: str | None
    ) -> ProfilePage:
        normalized = ProfileFilters(normalize_email(filters.email_prefix), filters.role)
        fingerprint = fingerprint_of(normalized)
        after = decode_cursor(cursor, fingerprint) if cursor is not None else None
        async with self._unit_of_work() as uow:
            rows = await uow.profiles.list_page(normalized, after, limit + 1)
        items = rows[:limit]
        if len(rows) <= limit:
            return ProfilePage(items, None)
        last = items[-1]
        return ProfilePage(
            items, encode_cursor(fingerprint, Position(last.created_at, last.user_id))
        )

    async def _ensure_profile(self, uow: UnitOfWork, identity: Identity) -> Profile:
        now = self._clock()
        return await uow.profiles.get_or_create(
            identity.user_id,
            normalize_email(identity.email),
            identity.role,
            identity.issued_at,
            now,
        )
