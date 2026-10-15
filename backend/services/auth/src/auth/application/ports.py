from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from auth.domain.tokens import RefreshTokenRecord
from auth.domain.user import Role, User


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_in: int


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool: ...

    async def verify_decoy(self, password: str) -> None: ...

    def needs_rehash(self, password_hash: str) -> bool: ...


class AccessTokenIssuer(Protocol):
    def issue(self, user_id: UUID, role: Role, now: datetime) -> AccessToken: ...


class UserRepository(Protocol):
    async def add(self, email: str, password_hash: str, role: Role, now: datetime) -> User: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def update_password_hash(
        self, user_id: UUID, password_hash: str, now: datetime
    ) -> None: ...


class RefreshTokenRepository(Protocol):
    async def add(
        self,
        *,
        token_hash: str,
        family_id: UUID,
        user_id: UUID,
        expires_at: datetime,
        family_expires_at: datetime,
        now: datetime,
    ) -> None: ...

    async def get_for_update(self, token_hash: str) -> RefreshTokenRecord | None: ...

    async def mark_used(self, token_id: UUID, now: datetime) -> None: ...

    async def revoke_family(self, family_id: UUID, now: datetime) -> None: ...


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def refresh_tokens(self) -> RefreshTokenRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


type UnitOfWorkFactory = Callable[[], UnitOfWork]
