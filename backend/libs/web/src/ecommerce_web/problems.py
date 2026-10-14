import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ecommerce_auth import AuthError
from ecommerce_observability import REQUEST_ID_HEADER, get_request_id

PROBLEM_MEDIA_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


def _request_id_of(request: Request) -> str | None:
    request_id: str | None = getattr(request.state, "request_id", None)
    return request_id or get_request_id()


def problem_response(
    request: Request,
    status: int,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    request_id = _request_id_of(request)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    if request_id is not None:
        body["request_id"] = request_id
    body.update(extensions)

    response_headers = dict(headers or {})
    if request_id is not None:
        response_headers[REQUEST_ID_HEADER] = request_id
    return JSONResponse(
        body, status_code=status, headers=response_headers, media_type=PROBLEM_MEDIA_TYPE
    )


def register_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def handle_auth_error(request: Request, error: AuthError) -> JSONResponse:
        return problem_response(
            request, int(error.status), error.title, error.detail, headers=error.headers
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        title = HTTPStatus(error.status_code).phrase
        return problem_response(
            request,
            error.status_code,
            title,
            str(error.detail),
            headers=dict(error.headers or {}),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in error.errors()
        ]
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "The request contains invalid data",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.exception(
            "unhandled error",
            extra={"path": request.url.path, "request_id": _request_id_of(request)},
        )
        return problem_response(request, HTTPStatus.INTERNAL_SERVER_ERROR, "Internal server error")
