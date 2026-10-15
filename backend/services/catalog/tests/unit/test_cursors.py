import base64
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from catalog.application.cursors import (
    CURSOR_MISMATCH,
    INVALID_CURSOR,
    DecodedCursor,
    InvalidCursorError,
    decode_cursor,
    encode_cursor,
)
from catalog.domain.listing import Direction, Position, Sort, TextMode

FINGERPRINT = "0123456789abcdef"
MOMENT = datetime(2026, 10, 14, 12, 30, 15, 123456, tzinfo=UTC)


def forge(**overrides: object) -> str:
    payload: dict[str, object] = {
        "v": 1,
        "d": "after",
        "s": "price_asc",
        "h": FINGERPRINT,
        "m": None,
        "k": ["10.50", str(uuid4())],
    }
    raw = json.dumps(payload | overrides).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.mark.parametrize(
    ("sort", "key"),
    [
        (Sort.NEWEST, MOMENT),
        (Sort.PRICE_ASC, Decimal("10.50")),
        (Sort.PRICE_DESC, Decimal("0.00")),
        (Sort.RELEVANCE, 0.30000000000000004),
        (Sort.RELEVANCE, 1.4285714149475098),
    ],
)
@pytest.mark.parametrize("direction", list(Direction))
def test_a_cursor_round_trips_every_key_exactly(
    sort: Sort, key: object, direction: Direction
) -> None:
    position = Position(key, uuid4())  # type: ignore[arg-type]

    cursor = encode_cursor(direction, sort, FINGERPRINT, position, None)

    assert decode_cursor(cursor, sort, FINGERPRINT) == DecodedCursor(direction, position, None)


@pytest.mark.parametrize("mode", [None, *TextMode])
def test_a_cursor_remembers_how_the_page_was_matched(mode: TextMode | None) -> None:
    position = Position(Decimal("5.00"), uuid4())

    cursor = encode_cursor(Direction.AFTER, Sort.PRICE_ASC, FINGERPRINT, position, mode)

    assert decode_cursor(cursor, Sort.PRICE_ASC, FINGERPRINT).mode is mode


def test_a_cursor_is_url_safe_and_unpadded() -> None:
    cursor = encode_cursor(
        Direction.AFTER, Sort.NEWEST, FINGERPRINT, Position(MOMENT, uuid4()), None
    )

    assert cursor.isascii()
    assert not set(cursor) & set("=+/ ")


def test_a_cursor_issued_for_other_filters_is_rejected_as_a_mismatch() -> None:
    cursor = encode_cursor(
        Direction.AFTER, Sort.PRICE_ASC, FINGERPRINT, Position(Decimal(1), uuid4()), None
    )

    with pytest.raises(InvalidCursorError) as raised:
        decode_cursor(cursor, Sort.PRICE_ASC, "ffffffffffffffff")

    assert raised.value.code == CURSOR_MISMATCH


def test_a_cursor_issued_for_another_sort_is_rejected_as_a_mismatch() -> None:
    cursor = encode_cursor(
        Direction.AFTER, Sort.PRICE_ASC, FINGERPRINT, Position(Decimal(1), uuid4()), None
    )

    with pytest.raises(InvalidCursorError) as raised:
        decode_cursor(cursor, Sort.PRICE_DESC, FINGERPRINT)

    assert raised.value.code == CURSOR_MISMATCH


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-base64!!",
        base64.urlsafe_b64encode(b"not json").decode(),
        base64.urlsafe_b64encode(b"[1, 2]").decode(),
        base64.urlsafe_b64encode(b'{"v": 1}').decode(),
        forge(v=2),
        forge(s="alphabetical"),
        forge(d="sideways"),
        forge(k="10.50"),
        forge(k=["10.50"]),
        forge(k=[10.5, str(uuid4())]),
        forge(k=["abc", str(uuid4())]),
        forge(k=["-1.00", str(uuid4())]),
        forge(k=["NaN", str(uuid4())]),
        forge(k=["10.50", "not-a-uuid"]),
        forge(k=["10.50", 7]),
        forge(extra=True),
        forge(m="semantic"),
        forge(m=7),
    ],
)
def test_malformed_cursors_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidCursorError) as raised:
        decode_cursor(raw, Sort.PRICE_ASC, FINGERPRINT)

    assert raised.value.code == INVALID_CURSOR


@pytest.mark.parametrize(
    ("sort", "key"),
    [
        (Sort.NEWEST, "2026-10-14T12:00:00"),
        (Sort.NEWEST, "yesterday"),
        (Sort.NEWEST, 5),
        (Sort.RELEVANCE, "1.5"),
        (Sort.RELEVANCE, True),
        (Sort.RELEVANCE, None),
    ],
)
def test_keys_of_the_wrong_shape_for_the_sort_are_rejected(sort: Sort, key: object) -> None:
    raw = forge(s=sort.value, k=[key, str(uuid4())])

    with pytest.raises(InvalidCursorError) as raised:
        decode_cursor(raw, sort, FINGERPRINT)

    assert raised.value.code == INVALID_CURSOR


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_scores_are_rejected(constant: str) -> None:
    text = (
        f'{{"v":1,"d":"after","s":"relevance","h":"{FINGERPRINT}","m":null,'
        f'"k":[{constant},"{uuid4()}"]}}'
    )
    raw = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")

    with pytest.raises(InvalidCursorError):
        decode_cursor(raw, Sort.RELEVANCE, FINGERPRINT)
