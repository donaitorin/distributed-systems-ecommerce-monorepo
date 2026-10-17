from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from cart.application.clock import utc_now
from cart.application.errors import (
    CartFullError,
    PriceChangedError,
    ProductNotFoundError,
)
from cart.application.ports import CartStore, CatalogGateway, ProductProjection
from cart.domain.cart import MAX_LINES, CartEntry, CartLine, CartView, flags_for
from cart.domain.product import ProductState, normalize_sku


def require_sku(raw: str) -> str:
    normalized = normalize_sku(raw)
    if normalized is None:
        raise ProductNotFoundError(raw)
    return normalized


class CartService:
    def __init__(
        self,
        store: CartStore,
        projection: ProductProjection,
        catalog: CatalogGateway,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._store = store
        self._projection = projection
        self._catalog = catalog
        self._clock = clock

    async def view(self, user_id: str) -> CartView:
        lines = await self._store.lines(user_id)
        if not lines:
            return CartView(())
        products = await self._projection.read_many([line.sku for line in lines])
        return CartView(
            tuple(CartEntry(line, flags_for(line, products.get(line.sku))) for line in lines)
        )

    async def set_quantity(
        self, user_id: str, raw_sku: str, quantity: int, accepted_price: Decimal | None
    ) -> CartView:
        sku = require_sku(raw_sku)
        existing = await self._store.get_line(user_id, sku)
        if existing is None or accepted_price is not None:
            product = await self._read_catalog(sku)
            if accepted_price is not None and accepted_price != product.price:
                raise PriceChangedError(sku, product.price)
            line = (
                existing.with_snapshot_of(product).with_quantity(quantity)
                if existing is not None
                else CartLine.started(product, quantity, self._clock())
            )
        else:
            line = existing.with_quantity(quantity)
        if not await self._store.put_line(user_id, line, MAX_LINES):
            raise CartFullError(MAX_LINES)
        return await self.view(user_id)

    async def remove(self, user_id: str, raw_sku: str) -> CartView:
        await self._store.remove_line(user_id, require_sku(raw_sku))
        return await self.view(user_id)

    async def clear(self, user_id: str) -> None:
        await self._store.clear(user_id)

    async def _read_catalog(self, sku: str) -> ProductState:
        await self._projection.reserve(sku)
        product = await self._catalog.get(sku)
        if product is None:
            raise ProductNotFoundError(sku)
        await self._projection.apply_state(product)
        return product
