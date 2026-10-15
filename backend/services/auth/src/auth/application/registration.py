from collections.abc import Callable
from datetime import datetime

from auth.application.clock import utc_now
from auth.application.ports import PasswordHasher, UnitOfWorkFactory
from auth.domain.user import Role, User, build_credentials


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

    async def register(self, raw_email: str, raw_password: str, role: Role = Role.CUSTOMER) -> User:
        credentials = build_credentials(raw_email, raw_password)
        password_hash = await self._hasher.hash(credentials.password)
        async with self._unit_of_work() as uow:
            user = await uow.users.add(credentials.email, password_hash, role, self._clock())
            await uow.commit()
        return user
