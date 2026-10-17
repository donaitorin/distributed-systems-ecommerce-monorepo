from datetime import datetime
from decimal import Decimal

from cart.domain.cart import CartLine
from cart.domain.product import ProductState


class InMemoryCartStore:
    def __init__(self) -> None:
        self.carts: dict[str, dict[str, CartLine]] = {}

    async def lines(self, user_id: str) -> list[CartLine]:
        lines = self.carts.get(user_id, {}).values()
        return sorted(lines, key=lambda line: (line.added_at, line.sku))

    async def get_line(self, user_id: str, sku: str) -> CartLine | None:
        return self.carts.get(user_id, {}).get(sku)

    async def put_line(self, user_id: str, line: CartLine, max_lines: int) -> bool:
        cart = self.carts.setdefault(user_id, {})
        if line.sku not in cart and len(cart) >= max_lines:
            return False
        cart[line.sku] = line
        return True

    async def remove_line(self, user_id: str, sku: str) -> None:
        cart = self.carts.get(user_id, {})
        cart.pop(sku, None)
        if not cart:
            self.carts.pop(user_id, None)

    async def remove_line_added_before(self, user_id: str, sku: str, cutoff: datetime) -> bool:
        line = self.carts.get(user_id, {}).get(sku)
        if line is None or line.added_at > cutoff:
            return False
        await self.remove_line(user_id, sku)
        return True

    async def clear(self, user_id: str) -> None:
        self.carts.pop(user_id, None)


class InMemoryProductProjection:
    def __init__(self) -> None:
        self.entries: dict[str, ProductState | None] = {}

    async def reserve(self, sku: str) -> None:
        self.entries.setdefault(sku, None)

    async def apply_state(self, state: ProductState) -> bool:
        if state.sku not in self.entries:
            return False
        current = self.entries[state.sku]
        if current is not None and state.version <= current.version:
            return False
        self.entries[state.sku] = state
        return True

    async def apply_deletion(self, sku: str, version: int) -> bool:
        if sku not in self.entries:
            return False
        current = self.entries[sku]
        if current is None:
            self.entries[sku] = ProductState(sku, "", Decimal("0"), 0, version, True, None)
            return True
        if version <= current.version:
            return False
        self.entries[sku] = ProductState(
            sku, current.name, current.price, current.stock, version, True, current.image_key
        )
        return True

    async def read_many(self, skus: list[str]) -> dict[str, ProductState]:
        return {sku: state for sku in skus if (state := self.entries.get(sku)) is not None}
