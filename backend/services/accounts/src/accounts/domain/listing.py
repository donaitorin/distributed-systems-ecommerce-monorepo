from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ProfileFilters:
    email_prefix: str | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class Position:
    created_at: datetime
    user_id: UUID
