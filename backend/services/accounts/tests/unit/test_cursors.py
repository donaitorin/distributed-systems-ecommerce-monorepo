import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from accounts.application.cursors import (
    CURSOR_MISMATCH,
    INVALID_CURSOR,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
    fingerprint_of,
)
from accounts.domain.listing import Position, ProfileFilters

POSITION = Position(datetime(2026, 10, 15, 12, 0, tzinfo=UTC), uuid4())
FINGERPRINT = fingerprint_of(ProfileFilters("ada", "admin"))


def forge(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def valid_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "v": 1,
        "h": FINGERPRINT,
        "k": [POSITION.created_at.isoformat(), str(POSITION.user_id)],
    }
    return base | overrides


def test_a_cursor_round_trips_its_position() -> None:
    cursor = encode_cursor(FINGERPRINT, POSITION)

    assert decode_cursor(cursor, FINGERPRINT) == POSITION


def test_the_cursor_is_url_safe_without_padding() -> None:
    cursor = encode_cursor(FINGERPRINT, POSITION)

    assert "=" not in cursor
    assert cursor == base64.urlsafe_b64encode(
        base64.urlsafe_b64decode(cursor + "==")
    ).decode().rstrip("=")


def test_different_filters_have_different_fingerprints() -> None:
    assert fingerprint_of(ProfileFilters("ada")) != fingerprint_of(ProfileFilters("grace"))
    assert fingerprint_of(ProfileFilters(role="admin")) != fingerprint_of(ProfileFilters())
    assert fingerprint_of(ProfileFilters("ada")) == fingerprint_of(ProfileFilters("ada"))


def test_a_cursor_for_other_filters_is_a_mismatch() -> None:
    cursor = encode_cursor(FINGERPRINT, POSITION)

    with pytest.raises(InvalidCursorError) as error:
        decode_cursor(cursor, fingerprint_of(ProfileFilters()))

    assert error.value.code == CURSOR_MISMATCH


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "!!!not base64!!!",
        forge("a string"),
        forge([1, 2]),
        forge({"v": 1}),
        forge(valid_payload(v=2)),
        forge(valid_payload(k="nope")),
        forge(valid_payload(k=["only one"])),
        forge(valid_payload(k=[1, str(uuid4())])),
        forge(valid_payload(k=["2026-10-15T12:00:00", str(uuid4())])),
        forge(valid_payload(k=["not a date", str(uuid4())])),
        forge(valid_payload(k=[POSITION.created_at.isoformat(), "not-a-uuid"])),
        forge(valid_payload(extra=True)),
        base64.urlsafe_b64encode(b"\xff\xfe").decode(),
    ],
)
def test_malformed_cursors_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidCursorError) as error:
        decode_cursor(raw, FINGERPRINT)

    assert error.value.code == INVALID_CURSOR
