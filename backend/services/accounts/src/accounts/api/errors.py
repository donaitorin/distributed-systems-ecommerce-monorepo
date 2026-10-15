from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from accounts.application.cursors import InvalidCursorError
from accounts.application.errors import AddressLimitReachedError, AddressNotFoundError
from ecommerce_web import problem_response


def register_accounts_errors(app: FastAPI) -> None:
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

    @app.exception_handler(AddressLimitReachedError)
    async def handle_address_limit(
        request: Request, error: AddressLimitReachedError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Address limit reached",
            f"An account can keep at most {error.limit} addresses; delete one first",
        )

    @app.exception_handler(AddressNotFoundError)
    async def handle_address_not_found(
        request: Request, error: AddressNotFoundError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Address not found",
            f"No address with id {error.address_id} on this account",
        )
