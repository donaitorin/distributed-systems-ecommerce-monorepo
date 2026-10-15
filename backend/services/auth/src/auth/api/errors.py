from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from auth.application.errors import (
    EmailTakenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    SelfRoleChangeError,
    UserNotFoundError,
)
from auth.domain.errors import ValidationFailedError
from ecommerce_web import problem_response


def register_auth_errors(app: FastAPI) -> None:
    @app.exception_handler(ValidationFailedError)
    async def handle_validation(request: Request, error: ValidationFailedError) -> JSONResponse:
        problems = [
            {"location": f"body.{item.location}", "message": item.message, "type": item.code}
            for item in error.violations
        ]
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "The request contains invalid data",
            errors=problems,
        )

    @app.exception_handler(EmailTakenError)
    async def handle_email_taken(request: Request, error: EmailTakenError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Email already registered",
            "An account with this email already exists",
        )

    @app.exception_handler(InvalidCredentialsError)
    async def handle_invalid_credentials(
        request: Request, error: InvalidCredentialsError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.UNAUTHORIZED,
            "Invalid credentials",
            "The email or password is incorrect",
        )

    @app.exception_handler(InvalidRefreshTokenError)
    async def handle_invalid_refresh_token(
        request: Request, error: InvalidRefreshTokenError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.UNAUTHORIZED,
            "Invalid refresh token",
            "The refresh token is invalid, expired or already used; log in again",
        )

    @app.exception_handler(UserNotFoundError)
    async def handle_user_not_found(request: Request, error: UserNotFoundError) -> JSONResponse:
        return problem_response(
            request, HTTPStatus.NOT_FOUND, "User not found", f"No user with id {error.user_id}"
        )

    @app.exception_handler(SelfRoleChangeError)
    async def handle_self_role_change(request: Request, error: SelfRoleChangeError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Cannot change your own role",
            "Ask another admin to change this account's role",
        )
