import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from orders.domain.order import MONEY_STEP, OrderRequest

IDEMPOTENCY_TTL = timedelta(hours=24)
KEY_MIN_LENGTH = 8
KEY_MAX_LENGTH = 128
KEY_ALLOWED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_:.")


def is_valid_key(key: str) -> bool:
    return KEY_MIN_LENGTH <= len(key) <= KEY_MAX_LENGTH and all(
        character in KEY_ALLOWED for character in key
    )


def fingerprint_of(request: OrderRequest) -> str:
    canonical: dict[str, Any] = {
        "lines": sorted(
            (
                [line.sku, line.quantity, str(line.unit_price.quantize(MONEY_STEP))]
                for line in request.lines
            ),
            key=lambda item: item[0],
        ),
        "address": [
            request.shipping_address.recipient_name,
            request.shipping_address.line1,
            request.shipping_address.line2,
            request.shipping_address.city,
            request.shipping_address.region,
            request.shipping_address.postal_code,
            request.shipping_address.country,
            request.shipping_address.phone,
        ],
        "card_last4": request.card_last4,
    }
    raw = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    user_id: UUID
    key: str
    fingerprint: str
    order_id: UUID
    response_status: int
    response_body: dict[str, Any]
    created_at: datetime
    expires_at: datetime
