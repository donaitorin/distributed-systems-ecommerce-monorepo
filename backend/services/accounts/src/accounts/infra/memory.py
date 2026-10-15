from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from accounts.application.errors import ProfileNotFoundError
from accounts.domain.listing import Position, ProfileFilters
from accounts.domain.profile import Address, NewAddress, Profile, ProfileChanges, is_newer


@dataclass(slots=True)
class InMemoryStore:
    profiles: dict[UUID, Profile] = field(default_factory=dict)
    addresses: dict[UUID, Address] = field(default_factory=dict)


class InMemoryProfileRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def get_or_create(
        self,
        user_id: UUID,
        email: str | None,
        role: str,
        role_updated_at: datetime | None,
        now: datetime,
    ) -> Profile:
        if user_id not in self._store.profiles:
            self._store.profiles[user_id] = Profile(
                user_id, email, role, role_updated_at, None, None, now, now
            )
        return self._store.profiles[user_id]

    async def apply_registered(
        self, user_id: UUID, email: str | None, role: str, registered_at: datetime, now: datetime
    ) -> None:
        current = self._store.profiles.get(user_id)
        if current is None:
            self._store.profiles[user_id] = Profile(
                user_id, email, role, registered_at, None, None, now, now
            )
            return
        fills_email = current.email is None and email is not None
        wins = is_newer(registered_at, current.role_updated_at)
        if not (fills_email or wins):
            return
        self._store.profiles[user_id] = replace(
            current,
            email=current.email or email,
            role=role if wins else current.role,
            role_updated_at=registered_at if wins else current.role_updated_at,
            updated_at=now,
        )

    async def apply_role_change(
        self, user_id: UUID, role: str, changed_at: datetime, now: datetime
    ) -> None:
        current = self._store.profiles.get(user_id)
        if current is None:
            self._store.profiles[user_id] = Profile(
                user_id, None, role, changed_at, None, None, now, now
            )
        elif is_newer(changed_at, current.role_updated_at):
            self._store.profiles[user_id] = replace(
                current, role=role, role_updated_at=changed_at, updated_at=now
            )

    async def get(self, user_id: UUID) -> Profile | None:
        return self._store.profiles.get(user_id)

    async def get_for_update(self, user_id: UUID) -> Profile | None:
        return self._store.profiles.get(user_id)

    async def update(self, user_id: UUID, changes: ProfileChanges, now: datetime) -> Profile:
        current = self._store.profiles.get(user_id)
        if current is None:
            raise ProfileNotFoundError(user_id)
        updated = replace(
            current,
            name=changes.name if changes.name is not None else current.name,
            phone=changes.phone if changes.change_phone else current.phone,
            updated_at=now,
        )
        self._store.profiles[user_id] = updated
        return updated

    async def list_page(
        self, filters: ProfileFilters, after: Position | None, limit: int
    ) -> list[Profile]:
        rows = [
            profile
            for profile in self._store.profiles.values()
            if _matches(profile, filters) and _comes_after(profile, after)
        ]
        rows.sort(key=lambda profile: (profile.created_at, profile.user_id), reverse=True)
        return rows[:limit]


def _matches(profile: Profile, filters: ProfileFilters) -> bool:
    if filters.email_prefix is not None and not (profile.email or "").startswith(
        filters.email_prefix
    ):
        return False
    return filters.role is None or profile.role == filters.role


def _comes_after(profile: Profile, after: Position | None) -> bool:
    if after is None:
        return True
    return (profile.created_at, profile.user_id) < (after.created_at, after.user_id)


class InMemoryAddressRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, user_id: UUID, address: NewAddress, now: datetime) -> Address:
        created = Address(
            uuid4(),
            user_id,
            address.recipient_name,
            address.line1,
            address.line2,
            address.city,
            address.region,
            address.postal_code,
            address.country,
            address.phone,
            now,
        )
        self._store.addresses[created.id] = created
        return created

    async def list_for(self, user_id: UUID) -> list[Address]:
        owned = [item for item in self._store.addresses.values() if item.user_id == user_id]
        return sorted(owned, key=lambda item: (item.created_at, item.id))

    async def count_for(self, user_id: UUID) -> int:
        return sum(1 for item in self._store.addresses.values() if item.user_id == user_id)

    async def delete(self, user_id: UUID, address_id: UUID) -> bool:
        address = self._store.addresses.get(address_id)
        if address is None or address.user_id != user_id:
            return False
        del self._store.addresses[address_id]
        return True


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.profiles = InMemoryProfileRepository(store)
        self.addresses = InMemoryAddressRepository(store)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        return None
