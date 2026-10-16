import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from catalog.application.cursors import InvalidCursorError
from catalog.application.errors import (
    DuplicateCategoryError,
    DuplicateSkuError,
    ImportNotConfirmableError,
    ImportNotFoundError,
    ImportNotRevalidatableError,
    ImportTooLargeError,
    InvalidUploadError,
    PreconditionFailedError,
    ProductImageNotFoundError,
    ProductNotFoundError,
    SearchTimeoutError,
    UnsupportedMediaError,
    UploadTooLargeError,
)
from catalog.domain.errors import ValidationFailedError
from ecommerce_storage import ObjectStorageError
from ecommerce_web import problem_response

logger = logging.getLogger(__name__)

SEARCH_RETRY_AFTER_SECONDS = "1"


class PreconditionRequiredError(Exception):
    pass


def register_catalog_errors(app: FastAPI) -> None:
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

    @app.exception_handler(SearchTimeoutError)
    async def handle_search_timeout(request: Request, error: SearchTimeoutError) -> JSONResponse:
        logger.warning(
            "search timed out",
            extra={"path": request.url.path, "timeout_ms": error.timeout_ms},
        )
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Search timed out",
            f"The search did not finish within {error.timeout_ms} ms; "
            "narrow it with filters or retry shortly",
            headers={"Retry-After": SEARCH_RETRY_AFTER_SECONDS},
        )

    @app.exception_handler(UploadTooLargeError)
    async def handle_upload_too_large(request: Request, error: UploadTooLargeError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONTENT_TOO_LARGE,
            "Image too large",
            f"The image must be at most {error.limit_bytes // (1024 * 1024)} MB",
        )

    @app.exception_handler(UnsupportedMediaError)
    async def handle_unsupported_media(
        request: Request, error: UnsupportedMediaError
    ) -> JSONResponse:
        return problem_response(
            request, HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Unsupported media type", str(error)
        )

    @app.exception_handler(InvalidUploadError)
    async def handle_invalid_upload(request: Request, error: InvalidUploadError) -> JSONResponse:
        problems = [{"location": "body.file", "message": error.message, "type": error.code}]
        return problem_response(
            request,
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "Request validation failed",
            "The request contains invalid data",
            errors=problems,
        )

    @app.exception_handler(ImportTooLargeError)
    async def handle_import_too_large(request: Request, error: ImportTooLargeError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONTENT_TOO_LARGE,
            "File too large",
            f"The file must be at most {error.limit_bytes // (1024 * 1024)} MB",
        )

    @app.exception_handler(ImportNotFoundError)
    async def handle_import_not_found(request: Request, error: ImportNotFoundError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Import not found",
            f"No import with id {error.import_id}",
        )

    @app.exception_handler(ImportNotConfirmableError)
    async def handle_import_not_confirmable(
        request: Request, error: ImportNotConfirmableError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Import cannot be confirmed",
            error.reason,
            import_status=error.status,
        )

    @app.exception_handler(ImportNotRevalidatableError)
    async def handle_import_not_revalidatable(
        request: Request, error: ImportNotRevalidatableError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Import cannot be validated again",
            error.reason,
            import_status=error.status,
        )

    @app.exception_handler(ProductImageNotFoundError)
    async def handle_image_not_found(
        request: Request, error: ProductImageNotFoundError
    ) -> JSONResponse:
        return problem_response(
            request, HTTPStatus.NOT_FOUND, "Image not found", f"Product {error.sku} has no image"
        )

    @app.exception_handler(ObjectStorageError)
    async def handle_storage_unavailable(
        request: Request, error: ObjectStorageError
    ) -> JSONResponse:
        logger.warning(
            "object storage unavailable",
            extra={"path": request.url.path, "error": str(error)},
        )
        return problem_response(
            request,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "Image storage unavailable",
            "The image could not be stored or removed right now; retry shortly",
            headers={"Retry-After": SEARCH_RETRY_AFTER_SECONDS},
        )

    @app.exception_handler(ProductNotFoundError)
    async def handle_product_not_found(
        request: Request, error: ProductNotFoundError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.NOT_FOUND,
            "Product not found",
            f"No product with SKU {error.sku}",
        )

    @app.exception_handler(DuplicateSkuError)
    async def handle_duplicate_sku(request: Request, error: DuplicateSkuError) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "SKU already exists",
            f"SKU {error.sku} is already in use, possibly by a retired product",
        )

    @app.exception_handler(DuplicateCategoryError)
    async def handle_duplicate_category(
        request: Request, error: DuplicateCategoryError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.CONFLICT,
            "Category already exists",
            f"A category named {error.name!r} or with the same slug already exists",
        )

    @app.exception_handler(PreconditionFailedError)
    async def handle_precondition_failed(
        request: Request, error: PreconditionFailedError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.PRECONDITION_FAILED,
            "Precondition failed",
            f"Product {error.sku} was modified; fetch its current version and retry",
        )

    @app.exception_handler(PreconditionRequiredError)
    async def handle_precondition_required(
        request: Request, error: PreconditionRequiredError
    ) -> JSONResponse:
        return problem_response(
            request,
            HTTPStatus.PRECONDITION_REQUIRED,
            "Precondition required",
            "Send the product ETag in the If-Match header",
        )
