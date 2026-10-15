from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)
REFRESH_FAMILY_TTL = timedelta(days=30)
REUSE_GRACE = timedelta(seconds=10)


@dataclass(frozen=True, slots=True)
class RefreshTokenRecord:
    id: UUID
    family_id: UUID
    user_id: UUID
    expires_at: datetime
    family_expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None


class RefreshOutcome(StrEnum):
    ROTATE = "rotate"
    REJECT = "reject"
    REPLAY_WITHIN_GRACE = "replay_within_grace"
    REUSE_DETECTED = "reuse_detected"


def decide_refresh(record: RefreshTokenRecord, now: datetime, grace: timedelta) -> RefreshOutcome:
    if record.revoked_at is not None:
        return RefreshOutcome.REJECT
    if record.used_at is not None:
        if now - record.used_at <= grace:
            return RefreshOutcome.REPLAY_WITHIN_GRACE
        return RefreshOutcome.REUSE_DETECTED
    if now >= record.expires_at or now >= record.family_expires_at:
        return RefreshOutcome.REJECT
    return RefreshOutcome.ROTATE


def next_expiry(now: datetime, ttl: timedelta, family_expires_at: datetime) -> datetime:
    return min(now + ttl, family_expires_at)
