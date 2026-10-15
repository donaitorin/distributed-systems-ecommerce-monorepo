from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from auth.application.clock import utc_now
from auth.application.errors import SelfRoleChangeError, UserNotFoundError
from auth.application.ports import UnitOfWorkFactory
from auth.domain.user import Role, User
from ecommerce_contracts import AUTH_TOPIC, USER_ROLE_CHANGED, UserRoleChangedV1


class RoleService:
    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def change_role(
        self, actor_id: UUID, user_id: UUID, new_role: Role, correlation_id: UUID
    ) -> User:
        if actor_id == user_id:
            raise SelfRoleChangeError
        async with self._unit_of_work() as uow:
            user = await uow.users.get_for_update(user_id)
            if user is None:
                raise UserNotFoundError(user_id)
            if user.role is new_role:
                return user
            now = self._clock()
            updated = await uow.users.update_role(user_id, new_role, now)
            await uow.events.add(
                topic=AUTH_TOPIC,
                key=str(user_id),
                event_type=USER_ROLE_CHANGED,
                payload=UserRoleChangedV1(
                    user_id=user_id,
                    old_role=user.role.value,
                    new_role=new_role.value,
                    changed_by=actor_id,
                    changed_at=now,
                ),
                correlation_id=correlation_id,
            )
            await uow.commit()
        return updated
