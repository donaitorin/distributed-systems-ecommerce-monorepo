from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from auth.domain.tokens import (
    REUSE_GRACE,
    RefreshOutcome,
    RefreshTokenRecord,
    decide_refresh,
    next_expiry,
)

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def record(
    expires_at: datetime = NOW + timedelta(days=7),
    family_expires_at: datetime = NOW + timedelta(days=30),
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> RefreshTokenRecord:
    return RefreshTokenRecord(
        uuid4(), uuid4(), uuid4(), expires_at, family_expires_at, used_at, revoked_at
    )


def decide(item: RefreshTokenRecord, at: datetime = NOW) -> RefreshOutcome:
    return decide_refresh(item, at, REUSE_GRACE)


def test_a_fresh_token_rotates() -> None:
    assert decide(record()) is RefreshOutcome.ROTATE


def test_a_revoked_token_is_rejected() -> None:
    assert decide(record(revoked_at=NOW - timedelta(seconds=1))) is RefreshOutcome.REJECT


def test_a_revoked_token_is_rejected_even_if_it_was_also_used() -> None:
    item = record(revoked_at=NOW, used_at=NOW - timedelta(hours=1))

    assert decide(item) is RefreshOutcome.REJECT


def test_an_expired_token_is_rejected() -> None:
    assert decide(record(expires_at=NOW)) is RefreshOutcome.REJECT


def test_a_token_past_its_family_lifetime_is_rejected() -> None:
    assert decide(record(family_expires_at=NOW)) is RefreshOutcome.REJECT


def test_the_last_instant_before_expiry_still_rotates() -> None:
    item = record(expires_at=NOW + timedelta(microseconds=1))

    assert decide(item) is RefreshOutcome.ROTATE


def test_reusing_a_token_just_after_rotation_is_a_replay_within_grace() -> None:
    item = record(used_at=NOW - timedelta(seconds=3))

    assert decide(item) is RefreshOutcome.REPLAY_WITHIN_GRACE


def test_the_grace_window_includes_its_boundary() -> None:
    assert decide(record(used_at=NOW - REUSE_GRACE)) is RefreshOutcome.REPLAY_WITHIN_GRACE


def test_reuse_after_the_grace_window_is_detected() -> None:
    item = record(used_at=NOW - REUSE_GRACE - timedelta(microseconds=1))

    assert decide(item) is RefreshOutcome.REUSE_DETECTED


@pytest.mark.parametrize("grace_seconds", [0, 30])
def test_the_grace_window_is_configurable(grace_seconds: int) -> None:
    item = record(used_at=NOW - timedelta(seconds=5))

    outcome = decide_refresh(item, NOW, timedelta(seconds=grace_seconds))

    expected = (
        RefreshOutcome.REPLAY_WITHIN_GRACE if grace_seconds else RefreshOutcome.REUSE_DETECTED
    )
    assert outcome is expected


def test_next_expiry_never_outlives_the_family() -> None:
    family_end = NOW + timedelta(days=2)

    assert next_expiry(NOW, timedelta(days=7), family_end) == family_end


def test_next_expiry_uses_the_token_lifetime_when_the_family_lasts_longer() -> None:
    assert next_expiry(NOW, timedelta(days=7), NOW + timedelta(days=30)) == NOW + timedelta(days=7)
