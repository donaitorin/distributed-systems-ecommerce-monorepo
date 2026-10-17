from decimal import Decimal
from typing import Final

from redis.asyncio import Redis

from cart.domain.product import ProductState

RESERVE: Final = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return 0
end
redis.call('HSET', KEYS[1], 'version', 0)
redis.call('EXPIRE', KEYS[1], ARGV[1])
return 1
"""

APPLY_IF_NEWER: Final = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return 0
end
local current = tonumber(redis.call('HGET', KEYS[1], 'version') or '0')
if tonumber(ARGV[1]) <= current then
  return 0
end
redis.call('HSET', KEYS[1], 'version', ARGV[1])
for index = 3, #ARGV, 2 do
  redis.call('HSET', KEYS[1], ARGV[index], ARGV[index + 1])
end
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

PENDING_SECONDS: Final = 300


def product_key(sku: str) -> str:
    return f"product:{sku}"


def decode_state(sku: str, fields: dict[str, str]) -> ProductState | None:
    version = int(fields.get("version", "0"))
    deleted = fields.get("deleted") == "1"
    if version == 0 or ("price" not in fields and not deleted):
        return None
    return ProductState(
        sku=sku,
        name=fields.get("name", ""),
        price=Decimal(fields.get("price", "0")),
        stock=int(fields.get("stock", "0")),
        version=version,
        deleted=deleted,
        image_key=fields.get("image_key") or None,
    )


class RedisProductProjection:
    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._reserve = redis.register_script(RESERVE)
        self._apply = redis.register_script(APPLY_IF_NEWER)

    async def reserve(self, sku: str) -> None:
        await self._reserve(keys=[product_key(sku)], args=[PENDING_SECONDS])

    async def apply_state(self, state: ProductState) -> bool:
        fields = [
            "name",
            state.name,
            "price",
            str(state.price),
            "stock",
            str(state.stock),
            "image_key",
            state.image_key or "",
            "deleted",
            "1" if state.deleted else "0",
        ]
        return await self._apply_fields(state.sku, state.version, fields)

    async def apply_deletion(self, sku: str, version: int) -> bool:
        return await self._apply_fields(sku, version, ["deleted", "1"])

    async def read_many(self, skus: list[str]) -> dict[str, ProductState]:
        pipeline = self._redis.pipeline(transaction=False)
        for sku in skus:
            pipeline.hgetall(product_key(sku))
            pipeline.expire(product_key(sku), self._ttl, xx=True)
        results = await pipeline.execute()
        states: dict[str, ProductState] = {}
        for sku, fields in zip(skus, results[::2], strict=True):
            state = decode_state(sku, fields)
            if state is not None:
                states[sku] = state
        return states

    async def _apply_fields(self, sku: str, version: int, fields: list[str]) -> bool:
        applied = await self._apply(keys=[product_key(sku)], args=[version, self._ttl, *fields])
        return bool(applied)
