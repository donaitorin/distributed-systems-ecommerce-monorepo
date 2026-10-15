from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator

from catalog.api.errors import PreconditionRequiredError
from catalog.api.media import MediaUrls
from catalog.application.categories import CategoryService
from catalog.application.images import ImageService
from catalog.application.imports import ImportService
from catalog.application.products import ProductService
from catalog.domain.imports import PROBLEMS_PAGE_SIZES
from catalog.domain.listing import (
    CATEGORY_MAX_LENGTH,
    DEFAULT_PAGE_SIZE,
    PAGE_SIZES,
    QUERY_MAX_LENGTH,
    ProductFilters,
    Sort,
    build_filters,
)
from catalog.domain.preconditions import VersionPrecondition


def get_product_service(request: Request) -> ProductService:
    service: ProductService = request.app.state.product_service
    return service


def get_image_service(request: Request) -> ImageService:
    service: ImageService = request.app.state.image_service
    return service


def get_media_urls(request: Request) -> MediaUrls:
    media: MediaUrls = request.app.state.media_urls
    return media


def get_import_service(request: Request) -> ImportService:
    service: ImportService = request.app.state.import_service
    return service


def get_category_service(request: Request) -> CategoryService:
    service: CategoryService = request.app.state.category_service
    return service


def require_if_match(
    if_match: Annotated[
        str | None,
        Header(description="ETag of the version being changed, or * to match any version"),
    ] = None,
) -> VersionPrecondition:
    if if_match is None:
        raise PreconditionRequiredError
    return VersionPrecondition.parse(if_match)


@dataclass(frozen=True, slots=True)
class ListParams:
    filters: ProductFilters
    sort: Sort | None
    limit: int
    cursor: str | None


def require_problem_page_size(
    limit: Annotated[int, Query(description="Page size: 25, 50, 100 or 500")] = 100,
) -> int:
    if limit not in PROBLEMS_PAGE_SIZES:
        allowed = ", ".join(str(size) for size in PROBLEMS_PAGE_SIZES)
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "limit"),
                    "msg": f"must be one of {allowed}",
                    "input": str(limit),
                }
            ]
        )
    return limit


def require_page_size(value: int) -> int:
    if value not in PAGE_SIZES:
        allowed = ", ".join(str(size) for size in PAGE_SIZES)
        raise ValueError(f"must be one of {allowed}")
    return value


PageSize = Annotated[int, AfterValidator(require_page_size)]
Price = Annotated[Decimal | None, Query(ge=0, max_digits=12, decimal_places=2)]


def list_params(
    q: Annotated[
        str | None,
        Query(max_length=QUERY_MAX_LENGTH, description="Free text; typos are tolerated"),
    ] = None,
    category: Annotated[
        str | None, Query(max_length=CATEGORY_MAX_LENGTH, description="Category slug")
    ] = None,
    min_price: Annotated[Price, Query(description="Minimum price, inclusive")] = None,
    max_price: Annotated[Price, Query(description="Maximum price, inclusive")] = None,
    in_stock: Annotated[
        bool | None,
        Query(description="true hides sold-out products; false is the same as omitting it"),
    ] = None,
    sort: Annotated[
        Sort | None,
        Query(description="Defaults to relevance when q is present, otherwise newest"),
    ] = None,
    limit: Annotated[PageSize, Query(description="Page size: 12, 24 or 48")] = DEFAULT_PAGE_SIZE,
    cursor: Annotated[
        str | None, Query(max_length=512, description="Opaque cursor from a previous page")
    ] = None,
) -> ListParams:
    if min_price is not None and max_price is not None and min_price > max_price:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "min_price"),
                    "msg": "must not be greater than max_price",
                    "input": str(min_price),
                }
            ]
        )
    filters = build_filters(q, category, min_price, max_price, in_stock)
    return ListParams(filters, sort, limit, cursor)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
ImportServiceDep = Annotated[ImportService, Depends(get_import_service)]
ImageServiceDep = Annotated[ImageService, Depends(get_image_service)]
MediaUrlsDep = Annotated[MediaUrls, Depends(get_media_urls)]
CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
IfMatch = Annotated[VersionPrecondition, Depends(require_if_match)]
