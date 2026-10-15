from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.application.errors import EmailTakenError, UserNotFoundError
from auth.domain.tokens import RefreshTokenRecord
from auth.domain.user import Role, User
from auth.infra.models import RefreshTokenModel, UserModel


def to_user(model: UserModel) -> User:
    return User(model.id, model.email, model.password_hash, Role(model.role), model.created_at)


def to_record(model: RefreshTokenModel) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        id=model.id,
        family_id=model.family_id,
        user_id=model.user_id,
        expires_at=model.expires_at,
        family_expires_at=model.family_expires_at,
        used_at=model.used_at,
        revoked_at=model.revoked_at,
    )


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, email: str, password_hash: str, role: Role, now: datetime) -> User:
        model = UserModel(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            role=role.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        try:
            await self._session.flush()
        except IntegrityError as error:
            raise EmailTakenError(email) from error
        return to_user(model)

    async def get_by_email(self, email: str) -> User | None:
        model = await self._session.scalar(select(UserModel).where(UserModel.email == email))
        return to_user(model) if model is not None else None

    async def get(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return to_user(model) if model is not None else None

    async def get_for_update(self, user_id: UUID) -> User | None:
        model = await self._session.scalar(
            select(UserModel).where(UserModel.id == user_id).with_for_update()
        )
        return to_user(model) if model is not None else None

    async def update_role(self, user_id: UUID, role: Role, now: datetime) -> User:
        model = await self._session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError(user_id)
        model.role = role.value
        model.updated_at = now
        await self._session.flush()
        return to_user(model)

    async def update_password_hash(self, user_id: UUID, password_hash: str, now: datetime) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(password_hash=password_hash, updated_at=now)
        )


class SqlRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
        self._session.add(
            RefreshTokenModel(
                id=uuid4(),
                family_id=family_id,
                user_id=user_id,
                token_hash=token_hash,
                created_at=now,
                expires_at=expires_at,
                family_expires_at=family_expires_at,
            )
        )
        await self._session.flush()

    async def get_for_update(self, token_hash: str) -> RefreshTokenRecord | None:
        model = await self._session.scalar(
            select(RefreshTokenModel)
            .where(RefreshTokenModel.token_hash == token_hash)
            .with_for_update()
        )
        return to_record(model) if model is not None else None

    async def mark_used(self, token_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshTokenModel).where(RefreshTokenModel.id == token_id).values(used_at=now)
        )

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(RefreshTokenModel)
            .where(RefreshTokenModel.family_id == family_id, RefreshTokenModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )
