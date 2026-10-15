import base64
import binascii
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from catalog.domain.errors import DomainError
from catalog.domain.listing import Direction, Position, Sort, SortKey, TextMode

CURSOR_VERSION = 1
INVALID_CURSOR = "invalid_cursor"
CURSOR_MISMATCH = "cursor_mismatch"


class InvalidCursorError(DomainError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class DecodedCursor:
    direction: Direction
    position: Position
    mode: TextMode | None


def encode_cursor(
    direction: Direction,
    sort: Sort,
    fingerprint: str,
    position: Position,
    mode: TextMode | None,
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "d": direction.value,
        "s": sort.value,
        "h": fingerprint,
        "m": mode.value if mode is not None else None,
        "k": [_encode_key(position.key), str(position.id)],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(raw: str, sort: Sort, fingerprint: str) -> DecodedCursor:
    payload = _parse_payload(raw)
    if payload["s"] != sort.value or payload["h"] != fingerprint:
        raise InvalidCursorError(
            CURSOR_MISMATCH, "cursor was issued for a different search, sort or filters"
        )
    try:
        direction = Direction(payload["d"])
        mode = TextMode(payload["m"]) if payload["m"] is not None else None
        key, identifier = payload["k"]
        if not isinstance(identifier, str):
            raise TypeError
        position = Position(_decode_key(sort, key), UUID(identifier))
        return DecodedCursor(direction, position, mode)
    except (ValueError, TypeError, InvalidOperation, KeyError) as error:
        raise _malformed() from error


def _parse_payload(raw: str) -> dict[str, Any]:
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded), parse_constant=_reject_constant)
    except (binascii.Error, ValueError) as error:
        raise _malformed() from error
    required = {"v", "d", "s", "h", "m", "k"}
    if not isinstance(decoded, dict) or set(decoded) != required:
        raise _malformed()
    if decoded["v"] != CURSOR_VERSION:
        raise _malformed()
    if not isinstance(decoded["k"], list) or len(decoded["k"]) != 2:
        raise _malformed()
    try:
        Sort(decoded["s"])
    except ValueError as error:
        raise _malformed() from error
    return decoded


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def _malformed() -> InvalidCursorError:
    return InvalidCursorError(INVALID_CURSOR, "cursor is malformed or no longer supported")


def _encode_key(key: SortKey) -> str | float:
    if isinstance(key, datetime):
        return key.isoformat()
    if isinstance(key, Decimal):
        return str(key)
    return key


def _decode_key(sort: Sort, value: object) -> SortKey:
    match sort:
        case Sort.NEWEST:
            if not isinstance(value, str):
                raise TypeError
            moment = datetime.fromisoformat(value)
            if moment.tzinfo is None:
                raise ValueError
            return moment
        case Sort.PRICE_ASC | Sort.PRICE_DESC:
            if not isinstance(value, str):
                raise TypeError
            price = Decimal(value)
            if not price.is_finite() or price < 0:
                raise ValueError
            return price
        case Sort.RELEVANCE:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError
            score = float(value)
            if not math.isfinite(score):
                raise ValueError
            return score
