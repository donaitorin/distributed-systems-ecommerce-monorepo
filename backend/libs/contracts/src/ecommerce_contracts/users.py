from typing import Final
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AUTH_TOPIC: Final = "auth.events"
USER_REGISTERED: Final = "user.registered"
USER_ROLE_CHANGED: Final = "user.role_changed"


class UserRegisteredV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    email: str = Field(min_length=3)
    role: str = Field(min_length=1)
    registered_at: AwareDatetime


class UserRoleChangedV1(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    old_role: str = Field(min_length=1)
    new_role: str = Field(min_length=1)
    changed_by: UUID
    changed_at: AwareDatetime
