from dataclasses import dataclass, field, replace
from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from auth.application.errors import EmailTakenError
from auth.domain.tokens import RefreshTokenRecord
from auth.domain.user import Role, User


@dataclass(slots=True)
class StoredRefreshToken:
    token_hash: str
    record: RefreshTokenRecord


@dataclass(slots=True)
class InMemoryStore:
    users: dict[UUID, User] = field(default_factory=dict)
    refresh_tokens: dict[str, StoredRefreshToken] = field(default_factory=dict)


class InMemoryUserRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, email: str, password_hash: str, role: Role, now: datetime) -> User:
        if any(user.email == email for user in self._store.users.values()):
            raise EmailTakenError(email)
        user = User(uuid4(), email, password_hash, role, now)
        self._store.users[user.id] = user
        return user

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self._store.users.values() if user.email == email), None)

    async def get(self, user_id: UUID) -> User | None:
        return self._store.users.get(user_id)

    async def update_password_hash(self, user_id: UUID, password_hash: str, now: datetime) -> None:
        self._store.users[user_id] = replace(
            self._store.users[user_id], password_hash=password_hash
        )


class InMemoryRefreshTokenRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(
        self,
        *,
        token_hash: str,
        family_id: UUID,
        user_id: UUID,
        expires_at: datetime,
        family_expires_at: datetime,
        now: datetime,
    ) -> None:
        record = RefreshTokenRecord(
            id=uuid4(),
            family_id=family_id,
            user_id=user_id,
            expires_at=expires_at,
            family_expires_at=family_expires_at,
            used_at=None,
            revoked_at=None,
        )
        self._store.refresh_tokens[token_hash] = StoredRefreshToken(token_hash, record)

    async def get_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        stored = self._store.refresh_tokens.get(token_hash)
        return stored.record if stored is not None else None

    async def mark_used(self, token_id: UUID, now: datetime) -> None:
        for stored in self._store.refresh_tokens.values():
            if stored.record.id == token_id:
                stored.record = replace(stored.record, used_at=now)

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        for stored in self._store.refresh_tokens.values():
            if stored.record.family_id == family_id and stored.record.revoked_at is None:
                stored.record = replace(stored.record, revoked_at=now)


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store
        self.users = InMemoryUserRepository(store)
        self.refresh_tokens = InMemoryRefreshTokenRepository(store)

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
