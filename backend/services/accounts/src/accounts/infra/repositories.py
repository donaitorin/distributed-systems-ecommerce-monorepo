from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import and_, case, delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from accounts.application.errors import ProfileNotFoundError
from accounts.domain.listing import Position, ProfileFilters
from accounts.domain.profile import Address, NewAddress, Profile, ProfileChanges
from accounts.infra.models import AddressModel, ProfileModel


def to_profile(model: ProfileModel) -> Profile:
    return Profile(
        user_id=model.user_id,
        email=model.email,
        role=model.role,
        role_updated_at=model.role_updated_at,
        name=model.name,
        phone=model.phone,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def to_address(model: AddressModel) -> Address:
    return Address(
        id=model.id,
        user_id=model.user_id,
        recipient_name=model.recipient_name,
        line1=model.line1,
        line2=model.line2,
        city=model.city,
        region=model.region,
        postal_code=model.postal_code,
        country=model.country,
        phone=model.phone,
        created_at=model.created_at,
    )


class SqlProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        user_id: UUID,
        email: str | None,
        role: str,
        role_updated_at: datetime | None,
        now: datetime,
    ) -> Profile:
        await self._session.execute(
            insert(ProfileModel)
            .values(
                user_id=user_id,
                email=email,
                role=role,
                role_updated_at=role_updated_at,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(index_elements=[ProfileModel.user_id])
        )
        profile = await self.get(user_id)
        if profile is None:
            raise ProfileNotFoundError(user_id)
        return profile

    async def apply_registered(
        self, user_id: UUID, email: str | None, role: str, registered_at: datetime, now: datetime
    ) -> None:
        statement = insert(ProfileModel).values(
            user_id=user_id,
            email=email,
            role=role,
            role_updated_at=registered_at,
            created_at=now,
            updated_at=now,
        )
        incoming = statement.excluded
        is_newer = or_(
            ProfileModel.role_updated_at.is_(None),
            incoming.role_updated_at > ProfileModel.role_updated_at,
        )
        fills_email = and_(ProfileModel.email.is_(None), incoming.email.is_not(None))
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ProfileModel.user_id],
                set_={
                    "email": func.coalesce(ProfileModel.email, incoming.email),
                    "role": case((is_newer, incoming.role), else_=ProfileModel.role),
                    "role_updated_at": case(
                        (is_newer, incoming.role_updated_at),
                        else_=ProfileModel.role_updated_at,
                    ),
                    "updated_at": incoming.updated_at,
                },
                where=or_(fills_email, is_newer),
            )
        )

    async def apply_role_change(
        self, user_id: UUID, role: str, changed_at: datetime, now: datetime
    ) -> None:
        statement = insert(ProfileModel).values(
            user_id=user_id,
            email=None,
            role=role,
            role_updated_at=changed_at,
            created_at=now,
            updated_at=now,
        )
        incoming = statement.excluded
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ProfileModel.user_id],
                set_={
                    "role": incoming.role,
                    "role_updated_at": incoming.role_updated_at,
                    "updated_at": incoming.updated_at,
                },
                where=or_(
                    ProfileModel.role_updated_at.is_(None),
                    incoming.role_updated_at > ProfileModel.role_updated_at,
                ),
            )
        )

    async def get(self, user_id: UUID) -> Profile | None:
        model = await self._session.scalar(
            select(ProfileModel)
            .where(ProfileModel.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return to_profile(model) if model is not None else None

    async def get_for_update(self, user_id: UUID) -> Profile | None:
        model = await self._session.scalar(
            select(ProfileModel)
            .where(ProfileModel.user_id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return to_profile(model) if model is not None else None

    async def update(self, user_id: UUID, changes: ProfileChanges, now: datetime) -> Profile:
        model = await self._session.get(ProfileModel, user_id)
        if model is None:
            raise ProfileNotFoundError(user_id)
        if changes.name is not None:
            model.name = changes.name
        if changes.change_phone:
            model.phone = changes.phone
        model.updated_at = now
        await self._session.flush()
        return to_profile(model)

    async def list_page(
        self, filters: ProfileFilters, after: Position | None, limit: int
    ) -> list[Profile]:
        statement = select(ProfileModel)
        if filters.email_prefix is not None:
            statement = statement.where(
                ProfileModel.email.startswith(filters.email_prefix, autoescape=True)
            )
        if filters.role is not None:
            statement = statement.where(ProfileModel.role == filters.role)
        if after is not None:
            statement = statement.where(
                tuple_(ProfileModel.created_at, ProfileModel.user_id)
                < tuple_(after.created_at, after.user_id)
            )
        statement = statement.order_by(
            ProfileModel.created_at.desc(), ProfileModel.user_id.desc()
        ).limit(limit)
        rows = await self._session.scalars(statement)
        return [to_profile(model) for model in rows]


class SqlAddressRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user_id: UUID, address: NewAddress, now: datetime) -> Address:
        model = AddressModel(
            id=uuid4(),
            user_id=user_id,
            recipient_name=address.recipient_name,
            line1=address.line1,
            line2=address.line2,
            city=address.city,
            region=address.region,
            postal_code=address.postal_code,
            country=address.country,
            phone=address.phone,
            created_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return to_address(model)

    async def list_for(self, user_id: UUID) -> list[Address]:
        rows = await self._session.scalars(
            select(AddressModel)
            .where(AddressModel.user_id == user_id)
            .order_by(AddressModel.created_at, AddressModel.id)
        )
        return [to_address(model) for model in rows]

    async def count_for(self, user_id: UUID) -> int:
        count = await self._session.scalar(
            select(func.count()).select_from(AddressModel).where(AddressModel.user_id == user_id)
        )
        return count or 0

    async def delete(self, user_id: UUID, address_id: UUID) -> bool:
        result = await self._session.execute(
            delete(AddressModel)
            .where(AddressModel.id == address_id, AddressModel.user_id == user_id)
            .returning(AddressModel.id)
        )
        return result.first() is not None
