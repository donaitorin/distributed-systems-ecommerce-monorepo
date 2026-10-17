from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ecommerce_web import problem_response
from orders.application.cursors import InvalidCursorError
from orders.application.errors import (
    IdempotencyKeyReusedError,
    InvalidDateRangeError,
    InvalidIdempotencyKeyError,
    OrderNotFoundError,
)

IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
IDEMPOTENCY_KEY_INVALID = "idempotency_key_invalid"


def register_orders_errors(app: FastAPI) -> None:
    @app.exception_handler(InvalidCursorError)
    async def handle_invalid_cursor(request: Request, error: InvalidCursorError) -> JSONResponse:
        problems = [{"location": "query.cursor", "message": error.message, "type": error.code}]
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "The request contains invalid data",
            errors=problems,
        )

    @app.exception_handler(InvalidDateRangeError)
    async def handle_invalid_range(request: Request, error: InvalidDateRangeError) -> JSONResponse:
        problems = [
            {"location": "query.created_from", "message": str(error), "type": "invalid_range"}
        ]
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "The request contains invalid data",
            errors=problems,
        )

    @app.exception_handler(OrderNotFoundError)
    async def handle_order_not_found(request: Request, error: OrderNotFoundError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Order not found",
            f"No order with id {error.order_id}",
        )

    @app.exception_handler(InvalidIdempotencyKeyError)
    async def handle_invalid_key(
        request: Request, error: InvalidIdempotencyKeyError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.BAD_REQUEST,
            "Invalid Idempotency-Key",
            str(error),
            code=IDEMPOTENCY_KEY_INVALID,
        )

    @app.exception_handler(IdempotencyKeyReusedError)
    async def handle_key_reused(request: Request, error: IdempotencyKeyReusedError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Idempotency key reused",
            "This Idempotency-Key was already used with a different request body. "
            "Send the same body to get the original response back, or use a new key "
            "for a different order.",
            code=IDEMPOTENCY_KEY_REUSED,
        )
