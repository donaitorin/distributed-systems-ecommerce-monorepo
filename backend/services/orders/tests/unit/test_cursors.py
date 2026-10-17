import base64
import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from orders.application.cursors import (
    CURSOR_MISMATCH,
    INVALID_CURSOR,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
    fingerprint_of,
)
from orders.domain.listing import OrderFilters, Position
from orders.domain.status import OrderStatus

POSITION = Position(datetime(2026, 10, 17, 12, tzinfo=UTC), UUID(int=5))


def test_a_cursor_round_trips() -> None:
    fingerprint = fingerprint_of(OrderFilters())

    assert decode_cursor(encode_cursor(fingerprint, POSITION), fingerprint) == POSITION


def test_a_cursor_only_works_with_the_filters_it_was_issued_for() -> None:
    cursor = encode_cursor(fingerprint_of(OrderFilters()), POSITION)

    with pytest.raises(InvalidCursorError) as caught:
        decode_cursor(cursor, fingerprint_of(OrderFilters(status=OrderStatus.CANCELLED)))

    assert caught.value.code == CURSOR_MISMATCH


def encode(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "raw",
    [
        "!!!",
        encode([1, 2]),
        encode({"v": 2, "h": "x", "k": ["2026-10-17T12:00:00+00:00", str(UUID(int=1))]}),
        encode({"v": 1, "h": "x", "k": ["only-one"]}),
        encode({"v": 1, "h": "x", "k": [1, 2]}),
        encode({"v": 1, "h": "x", "k": ["2026-10-17T12:00:00", str(UUID(int=1))]}),
        encode({"v": 1, "h": "x", "k": ["2026-10-17T12:00:00+00:00", "not-a-uuid"]}),
    ],
)
def test_malformed_cursors_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidCursorError) as caught:
        decode_cursor(raw, "x")

    assert caught.value.code == INVALID_CURSOR
