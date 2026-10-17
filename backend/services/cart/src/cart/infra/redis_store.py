import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Final, cast

from redis.asyncio import Redis

from cart.domain.cart import CartLine

PUT_LINE: Final = """
local exists = redis.call('HEXISTS', KEYS[1], ARGV[1])
if exists == 0 and redis.call('HLEN', KEYS[1]) >= tonumber(ARGV[3]) then
  return 0
end
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return 1
"""

REMOVE_LINE: Final = """
redis.call('HDEL', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""


def cart_key(user_id: str) -> str:
    return f"cart:{user_id}"


def encode_line(line: CartLine) -> str:
    return json.dumps(
        {
            "name": line.name,
            "price": str(line.price),
            "quantity": line.quantity,
            "image_key": line.image_key,
            "added_at": line.added_at.isoformat(),
        }
    )


def decode_line(sku: str, raw: str) -> CartLine:
    data: dict[str, Any] = json.loads(raw)
    return CartLine(
        sku=sku,
        name=data["name"],
        price=Decimal(data["price"]),
        quantity=int(data["quantity"]),
        image_key=data["image_key"],
        added_at=datetime.fromisoformat(data["added_at"]),
    )


class RedisCartStore:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._put_line = redis.register_script(PUT_LINE)
        self._remove_line = redis.register_script(REMOVE_LINE)

    async def lines(self, user_id: str) -> list[CartLine]:
        stored = cast(dict[str, str], await self._redis.hgetall(cart_key(user_id)))
        lines = [decode_line(sku, raw) for sku, raw in stored.items()]
        return sorted(lines, key=lambda line: (line.added_at, line.sku))

    async def get_line(self, user_id: str, sku: str) -> CartLine | None:
        raw = cast(str | None, await self._redis.hget(cart_key(user_id), sku))
        return decode_line(sku, raw) if raw is not None else None

    async def put_line(self, user_id: str, line: CartLine, max_lines: int) -> bool:
        stored = await self._put_line(
            keys=[cart_key(user_id)],
            args=[line.sku, encode_line(line), max_lines, self._ttl],
        )
        return bool(stored)

    async def remove_line(self, user_id: str, sku: str) -> None:
        await self._remove_line(keys=[cart_key(user_id)], args=[sku, self._ttl])

    async def clear(self, user_id: str) -> None:
        await self._redis.delete(cart_key(user_id))
