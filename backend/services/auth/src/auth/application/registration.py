from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from auth.application.clock import utc_now
from auth.application.ports import PasswordHasher, UnitOfWorkFactory
from auth.domain.user import Role, User, build_credentials
from ecommerce_contracts import AUTH_TOPIC, USER_REGISTERED, UserRegisteredV1


class RegistrationService:
    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        hasher: PasswordHasher,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._hasher = hasher
        self._clock = clock

    async def register(
        self,
        raw_email: str,
        raw_password: str,
        correlation_id: UUID,
        role: Role = Role.CUSTOMER,
    ) -> User:
        credentials = build_credentials(raw_email, raw_password)
        password_hash = await self._hasher.hash(credentials.password)
        async with self._unit_of_work() as uow:
            user = await uow.users.add(credentials.email, password_hash, role, self._clock())
            await uow.events.add(
                topic=AUTH_TOPIC,
                key=str(user.id),
                event_type=USER_REGISTERED,
                payload=UserRegisteredV1(
                    user_id=user.id,
                    email=user.email,
                    role=user.role.value,
                    registered_at=user.created_at,
                ),
                correlation_id=correlation_id,
            )
            await uow.commit()
        return user
