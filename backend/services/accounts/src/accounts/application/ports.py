from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from accounts.domain.listing import Position, ProfileFilters
from accounts.domain.profile import Address, NewAddress, Profile, ProfileChanges


class ProfileRepository(Protocol):
    async def get_or_create(
        self,
        user_id: UUID,
        email: str | None,
        role: str,
        role_updated_at: datetime | None,
        now: datetime,
    ) -> Profile: ...

    async def apply_registered(
        self, user_id: UUID, email: str | None, role: str, registered_at: datetime, now: datetime
    ) -> None: ...

    async def apply_role_change(
        self, user_id: UUID, role: str, changed_at: datetime, now: datetime
    ) -> None: ...

    async def get(self, user_id: UUID) -> Profile | None: ...

    async def get_for_update(self, user_id: UUID) -> Profile | None: ...

    async def update(self, user_id: UUID, changes: ProfileChanges, now: datetime) -> Profile: ...

    async def list_page(
        self, filters: ProfileFilters, after: Position | None, limit: int
    ) -> list[Profile]: ...


class AddressRepository(Protocol):
    async def add(self, user_id: UUID, address: NewAddress, now: datetime) -> Address: ...

    async def list_for(self, user_id: UUID) -> list[Address]: ...

    async def count_for(self, user_id: UUID) -> int: ...

    async def delete(self, user_id: UUID, address_id: UUID) -> bool: ...


class UnitOfWork(Protocol):
    @property
    def profiles(self) -> ProfileRepository: ...

    @property
    def addresses(self) -> AddressRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
