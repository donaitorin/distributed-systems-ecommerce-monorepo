from decimal import Decimal


class CartError(Exception):
    pass


class ProductNotFoundError(CartError):
    def __init__(self, sku: str) -> None:
        super().__init__(f"no product with SKU {sku}")
        self.sku = sku


class CartFullError(CartError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"the cart already has {limit} different products")
        self.limit = limit


class PriceChangedError(CartError):
    def __init__(self, sku: str, current_price: Decimal) -> None:
        super().__init__(f"the price of {sku} is {current_price}")
        self.sku = sku
        self.current_price = current_price


class CatalogUnavailableError(CartError):
    pass


class CatalogCircuitOpenError(CatalogUnavailableError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("the catalog circuit breaker is open")
        self.retry_after_seconds = retry_after_seconds
