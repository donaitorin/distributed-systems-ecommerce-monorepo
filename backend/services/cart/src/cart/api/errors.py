from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from cart.application.errors import (
    CartFullError,
    CatalogCircuitOpenError,
    CatalogUnavailableError,
    PriceChangedError,
    ProductNotFoundError,
)
from ecommerce_web import problem_response

RETRY_AFTER_SECONDS = "2"


def register_cart_errors(app: FastAPI) -> None:
    @app.exception_handler(ProductNotFoundError)
    async def handle_not_found(request: Request, error: ProductNotFoundError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Product not found",
            f"No product with SKU {error.sku}",
        )

    @app.exception_handler(CartFullError)
    async def handle_cart_full(request: Request, error: CartFullError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Cart is full",
            f"A cart can hold at most {error.limit} different products; remove one first",
            code="cart_full",
            limit=error.limit,
        )

    @app.exception_handler(PriceChangedError)
    async def handle_price_changed(request: Request, error: PriceChangedError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Price has changed",
            f"The current price of {error.sku} is {error.current_price}",
            code="price_changed",
            current_price=str(error.current_price),
        )

    @app.exception_handler(CatalogCircuitOpenError)
    async def handle_catalog_circuit_open(
        request: Request, error: CatalogCircuitOpenError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Catalog unavailable",
            "The catalog is not answering; products cannot be added right now, try again shortly",
            code="catalog_unavailable",
            headers={"Retry-After": str(error.retry_after_seconds)},
        )

    @app.exception_handler(CatalogUnavailableError)
    async def handle_catalog_unavailable(
        request: Request, error: CatalogUnavailableError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Catalog unavailable",
            "The product could not be checked right now; try again shortly",
            code="catalog_unavailable",
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )

    @app.exception_handler(RedisError)
    async def handle_store_unavailable(request: Request, error: RedisError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Cart unavailable",
            "The cart could not be reached right now; try again shortly",
            headers={"Retry-After": RETRY_AFTER_SECONDS},
        )
