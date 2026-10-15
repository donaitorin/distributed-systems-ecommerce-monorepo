import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from auth.application.clock import utc_now
from auth.application.errors import InvalidCredentialsError, InvalidRefreshTokenError
from auth.application.ports import (
    AccessToken,
    AccessTokenIssuer,
    PasswordHasher,
    UnitOfWork,
    UnitOfWorkFactory,
)
from auth.domain.email import normalize_email
from auth.domain.password import normalize_password
from auth.domain.tokens import (
    REFRESH_FAMILY_TTL,
    REFRESH_TOKEN_TTL,
    REUSE_GRACE,
    RefreshOutcome,
    decide_refresh,
    next_expiry,
)
from auth.domain.user import User

logger = logging.getLogger(__name__)

REFRESH_TOKEN_BYTES = 32


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: AccessToken
    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshPolicy:
    token_ttl: timedelta = REFRESH_TOKEN_TTL
    family_ttl: timedelta = REFRESH_FAMILY_TTL
    reuse_grace: timedelta = REUSE_GRACE


class AuthService:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        hasher: PasswordHasher,
        issuer: AccessTokenIssuer,
        clock: Callable[[], datetime] = utc_now,
        policy: RefreshPolicy | None = None,
        token_factory: Callable[[], str] = new_refresh_token,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._hasher = hasher
        self._issuer = issuer
        self._clock = clock
        self._policy = policy or RefreshPolicy()
        self._token_factory = token_factory

    async def login(self, raw_email: str, raw_password: str) -> TokenPair:
        email = normalize_email(raw_email)
        password = normalize_password(raw_password)
        async with self._unit_of_work() as uow:
            user = await uow.users.get_by_email(email)
            if user is None:
                await self._hasher.verify_decoy(password)
                raise InvalidCredentialsError
            if not await self._hasher.verify(user.password_hash, password):
                raise InvalidCredentialsError
            now = self._clock()
            if self._hasher.needs_rehash(user.password_hash):
                upgraded = await self._hasher.hash(password)
                await uow.users.update_password_hash(user.id, upgraded, now)
            family_id = uuid4()
            pair = await self._issue_pair(uow, user, family_id, now, now + self._policy.family_ttl)
            await uow.commit()
        return pair

    async def refresh(self, refresh_token: str) -> TokenPair:
        async with self._unit_of_work() as uow:
            record = await uow.refresh_tokens.get_for_update(hash_refresh_token(refresh_token))
            if record is None:
                raise InvalidRefreshTokenError
            now = self._clock()
            outcome = decide_refresh(record, now, self._policy.reuse_grace)
            if outcome is RefreshOutcome.REUSE_DETECTED:
                await uow.refresh_tokens.revoke_family(record.family_id, now)
                await uow.commit()
                logger.warning(
                    "refresh token reuse detected, family revoked",
                    extra={"user_id": str(record.user_id), "family_id": str(record.family_id)},
                )
                raise InvalidRefreshTokenError
            if outcome is not RefreshOutcome.ROTATE:
                raise InvalidRefreshTokenError
            user = await uow.users.get(record.user_id)
            if user is None:
                raise InvalidRefreshTokenError
            await uow.refresh_tokens.mark_used(record.id, now)
            pair = await self._issue_pair(
                uow, user, record.family_id, now, record.family_expires_at
            )
            await uow.commit()
        return pair

    async def logout(self, refresh_token: str) -> None:
        async with self._unit_of_work() as uow:
            record = await uow.refresh_tokens.get_for_update(hash_refresh_token(refresh_token))
            if record is None:
                return
            await uow.refresh_tokens.revoke_family(record.family_id, self._clock())
            await uow.commit()

    async def _issue_pair(
        self,
        uow: UnitOfWork,
        user: User,
        family_id: UUID,
        now: datetime,
        family_expires_at: datetime,
    ) -> TokenPair:
        refresh_token = self._token_factory()
        await uow.refresh_tokens.add(
            token_hash=hash_refresh_token(refresh_token),
            family_id=family_id,
            user_id=user.id,
            expires_at=next_expiry(now, self._policy.token_ttl, family_expires_at),
            family_expires_at=family_expires_at,
            now=now,
        )
        return TokenPair(self._issuer.issue(user.id, user.role, now), refresh_token)
