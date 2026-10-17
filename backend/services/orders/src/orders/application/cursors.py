import base64
import binascii
import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from orders.application.errors import ApplicationError
from orders.domain.listing import OrderFilters, Position

CURSOR_VERSION = 1
INVALID_CURSOR = "invalid_cursor"
CURSOR_MISMATCH = "cursor_mismatch"


class InvalidCursorError(ApplicationError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def fingerprint_of(filters: OrderFilters) -> str:
    raw = json.dumps(
        [
            filters.status.value if filters.status else None,
            filters.created_from.isoformat() if filters.created_from else None,
            filters.created_to.isoformat() if filters.created_to else None,
        ],
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def encode_cursor(fingerprint: str, position: Position) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "h": fingerprint,
        "k": [position.created_at.isoformat(), str(position.order_id)],
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(raw: str, fingerprint: str) -> Position:
    payload = _parse_payload(raw)
    if payload["h"] != fingerprint:
        raise InvalidCursorError(CURSOR_MISMATCH, "cursor was issued for different filters")
    try:
        moment, identifier = payload["k"]
        if not isinstance(moment, str) or not isinstance(identifier, str):
            raise TypeError
        created_at = datetime.fromisoformat(moment)
        if created_at.tzinfo is None:
            raise ValueError
        return Position(created_at, UUID(identifier))
    except (ValueError, TypeError) as error:
        raise _malformed() from error


def _parse_payload(raw: str) -> dict[str, Any]:
    try:
        padded = raw + "=" * (-len(raw) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded))
    except (binascii.Error, ValueError) as error:
        raise _malformed() from error
    if not isinstance(decoded, dict) or set(decoded) != {"v", "h", "k"}:
        raise _malformed()
    if decoded["v"] != CURSOR_VERSION:
        raise _malformed()
    if not isinstance(decoded["k"], list) or len(decoded["k"]) != 2:
        raise _malformed()
    return decoded


def _malformed() -> InvalidCursorError:
    return InvalidCursorError(INVALID_CURSOR, "cursor is malformed or no longer supported")
