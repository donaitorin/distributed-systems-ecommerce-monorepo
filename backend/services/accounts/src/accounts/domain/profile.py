from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

MAX_ADDRESSES = 10


@dataclass(frozen=True, slots=True)
class Profile:
    user_id: UUID
    email: str | None
    role: str
    role_updated_at: datetime | None
    name: str | None
    phone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProfileChanges:
    name: str | None = None
    phone: str | None = None
    change_phone: bool = False

    @property
    def is_empty(self) -> bool:
        return self.name is None and not self.change_phone


@dataclass(frozen=True, slots=True)
class NewAddress:
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    phone: str | None


@dataclass(frozen=True, slots=True)
class Address:
    id: UUID
    user_id: UUID
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    phone: str | None
    created_at: datetime


def normalize_email(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    return normalized or None


def is_newer(candidate: datetime, current: datetime | None) -> bool:
    return current is None or candidate > current
