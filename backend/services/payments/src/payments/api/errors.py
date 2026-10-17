from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ecommerce_web import problem_response
from payments.application.errors import PaymentNotFoundError


def register_payments_errors(app: FastAPI) -> None:
    @app.exception_handler(PaymentNotFoundError)
    async def handle_not_found(request: Request, error: PaymentNotFoundError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Payment not found",
            f"No payment for order {error.order_id}",
        )
